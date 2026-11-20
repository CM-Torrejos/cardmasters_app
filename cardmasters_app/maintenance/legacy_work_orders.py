"""Clean up fully billed legacy orders whose draft deliveries cover all items.

Preview: bench --site SITE execute cardmasters_app.maintenance.legacy_work_orders.run
Apply:   bench --site SITE execute cardmasters_app.maintenance.legacy_work_orders.run --kwargs '{"apply": 1}'
"""

import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from time import monotonic

import frappe
from frappe.utils import cint

LEGACY_NAME = re.compile(r"^SO-[0-9]+_MFG[0-9]+$")
EPSILON = Decimal("0.000001")


def number(value):
    return Decimal(str(value or 0))


def coverage_reason(items, deliveries):
    """Compare stock units by SO row, never by item code (which can repeat)."""
    expected = {row.name: row for row in items}
    covered = defaultdict(Decimal)
    for row in deliveries:
        source = expected.get(row.so_detail)
        if not source or row.item_code != source.item_code:
            return "Delivery item has a missing or mismatched Sales Order item reference"
        if number(row.stock_qty) <= 0:
            return "Delivery item has a non-positive stock quantity"
        covered[row.so_detail] += number(row.stock_qty)
    if not expected or any(
        number(row.stock_qty) <= 0 or covered[row.name] + EPSILON < number(row.stock_qty)
        for row in items
    ):
        return "Draft Delivery Notes do not fully cover every Sales Order item"
    return None


def stock_links(work_orders, job_cards):
    """Include custom Link fields and all Stock Entry statuses, including drafts."""
    found = set()
    targets = {"Work Order": work_orders, "Job Card": job_cards}
    for doctype in ("Stock Entry", "Stock Entry Detail"):
        for field in frappe.get_meta(doctype).fields:
            names = targets.get(field.options) if field.fieldtype == "Link" else None
            if names:
                found.update(frappe.get_all(
                    doctype, filters={field.fieldname: ["in", names]},
                    pluck="parent" if doctype == "Stock Entry Detail" else "name",
                ))
    return sorted(found)


def inspect_order(name, lock=False):
    if lock:
        frappe.db.get_value("Sales Order", name, "name", for_update=True)
    so = frappe.get_doc("Sales Order", name)
    plan = {"sales_order": name, "work_orders": [], "job_cards": [], "delivery_notes": []}

    def reject(reason):
        plan["reason"] = reason
        return plan

    if so.docstatus != 1 or number(so.per_billed) < 100:
        return reject("Sales Order is not submitted and fully invoiced")
    orders = frappe.get_all("Work Order", filters={"sales_order": name},
                            fields=["name", "docstatus"], order_by="name")
    if not orders or any(not LEGACY_NAME.fullmatch(row.name) for row in orders):
        return reject("Sales Order has non-legacy Work Orders or no Work Orders")
    if any(row.name.split("_MFG")[0] != name for row in orders):
        return reject("Legacy Work Order name does not match its linked Sales Order")
    plan["work_orders"] = [row.name for row in orders]
    plan["job_cards"] = frappe.get_all("Job Card", filters={"work_order": ["in", plan["work_orders"]]},
                                         pluck="name", order_by="name")
    if lock:
        for doctype, names in (("Work Order", plan["work_orders"]), ("Job Card", plan["job_cards"])):
            for docname in names:
                frappe.db.get_value(doctype, docname, "name", for_update=True)
    entries = stock_links(plan["work_orders"], plan["job_cards"])
    if entries:
        plan["stock_entries"] = entries
        return reject("Linked Stock Entries exist")
    linked = frappe.get_all("Delivery Note Item", filters={"against_sales_order": name}, pluck="parent")
    if not linked:
        return reject("No linked draft Delivery Notes")
    deliveries = []
    for dn_name in sorted(set(linked)):
        if lock:
            frappe.db.get_value("Delivery Note", dn_name, "name", for_update=True)
        dn = frappe.get_doc("Delivery Note", dn_name)
        if dn.docstatus != 0 or dn.is_return:
            return reject("A linked Delivery Note is not a draft or is a return")
        if any(row.against_sales_order != name for row in dn.items):
            return reject("A Delivery Note contains items outside this Sales Order")
        deliveries.extend(dn.items)
        plan["delivery_notes"].append(dn_name)
    reason = coverage_reason(so.items, deliveries)
    if reason:
        return reject(reason)
    plan["eligible"] = True
    return plan


def _cancel(doctype, name, log):
    doc = frappe.get_doc(doctype, name)
    if doc.docstatus == 1:
        log(f"Cancelling {doctype} {name}")
        if doctype == "Work Order":
            # This cleanup closes the Sales Order after removing the entire legacy group.
            doc.flags.legacy_work_order_cleanup = True
        doc.cancel()


def _apply(plan, log=lambda message: None):
    # Job Cards must be removed first: even draft cards can block WO deletion.
    for name in plan["job_cards"]:
        _cancel("Job Card", name, log)
    for name in plan["work_orders"]:
        _cancel("Work Order", name, log)
    for name in plan["job_cards"]:
        log(f"Deleting Job Card {name}")
        frappe.delete_doc("Job Card", name)
    # Delete original drafts first, then cancelled Work Orders.
    orders = sorted(plan["work_orders"], key=lambda name: frappe.db.get_value("Work Order", name, "docstatus"))
    for name in orders:
        log(f"Deleting Work Order {name}")
        frappe.delete_doc("Work Order", name)
    for name in plan["delivery_notes"]:
        log(f"Deleting Delivery Note {name}")
        frappe.delete_doc("Delivery Note", name)
    # Use ERPNext's controller so reserved quantities and status stay consistent.
    log(f"Closing Sales Order {plan['sales_order']}")
    frappe.get_doc("Sales Order", plan["sales_order"]).update_status("Closed")


def run(apply=False, sales_order=None, limit=None, progress=True):
    """Preview by default; commit each eligible Sales Order atomically when apply=true.

    sales_order optionally limits the command to one order. limit bounds the
    number of eligible orders processed, not the number scanned. No force deletes.
    Progress is flushed to stderr; stdout remains the final JSON report.
    """
    apply = bool(cint(apply))
    if limit is not None and cint(limit) <= 0:
        raise ValueError("limit must be a positive integer")
    if frappe.session.user != "Administrator":
        frappe.only_for("System Manager")
    started = monotonic()
    show_progress = bool(cint(progress))

    def log(message):
        if show_progress:
            print(f"[legacy-cleanup +{monotonic() - started:.1f}s] {message}", file=sys.stderr, flush=True)

    log(f"Starting {'APPLY' if apply else 'PREVIEW'}; finding legacy Sales Orders")
    names = frappe.get_all("Work Order", filters={"name": ["like", "SO-%"], **(
        {"sales_order": sales_order} if sales_order else {}
    )}, fields=["name", "sales_order"], order_by="sales_order, name")
    candidates = sorted({row.sales_order for row in names if row.sales_order and LEGACY_NAME.fullmatch(row.name)})
    log(f"Found {len(candidates)} Sales Orders to check")
    report = {"mode": "apply" if apply else "preview", "eligible": [], "completed": [], "skipped": [], "failed": []}
    attempted = 0
    try:
        for index, name in enumerate(candidates, 1):
            log(f"[{index}/{len(candidates)}] Checking {name}")
            frappe.db.savepoint("legacy_cleanup_order")
            try:
                plan = inspect_order(name, lock=apply)
                if not plan.get("eligible"):
                    report["skipped"].append(plan)
                    log(f"SKIPPED {name}: {plan['reason']}")
                    if apply:
                        frappe.db.rollback()
                    continue
                attempted += 1
                if apply:
                    _apply(plan, log=log)
                    frappe.db.commit()
                    report["completed"].append(plan)
                    log(f"COMMITTED {name}; completed={len(report['completed'])}, "
                        f"skipped={len(report['skipped'])}, failed={len(report['failed'])}")
                else:
                    report["eligible"].append(plan)
                    log(f"ELIGIBLE {name}; eligible={len(report['eligible'])}, "
                        f"skipped={len(report['skipped'])}, failed={len(report['failed'])}")
            except Exception as exc:
                if apply:
                    # Full rollback also clears after-commit callbacks queued by deletes.
                    frappe.db.rollback()
                else:
                    frappe.db.rollback(save_point="legacy_cleanup_order")
                report["failed"].append({"sales_order": name, "error": str(exc), "type": type(exc).__name__})
                log(f"FAILED {name} ({'rolled back' if apply else 'preview'}): {type(exc).__name__}: {exc}")
            if limit and attempted >= cint(limit):
                break
    finally:
        # Release locks acquired for skipped orders; never leave pending changes.
        if apply:
            frappe.db.rollback()
    report["counts"] = {key: len(report[key]) for key in ("eligible", "completed", "skipped", "failed")}
    report["skip_reasons"] = dict(Counter(row["reason"] for row in report["skipped"]))
    log("Finished: " + ", ".join(f"{key}={value}" for key, value in report["counts"].items()))
    return report
