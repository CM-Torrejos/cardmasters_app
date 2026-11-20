"""Run with the bench Python from the bench sites directory; see companion README."""
import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import frappe


def target_branch(order):
    targets = set()
    reasons = []
    rules = [
        (order.name in {"SO-023593", "SO-023584"}, "Makati", "explicit order"),
        (order.custom_for_branch == "Makati", "Makati", "For Branch"),
        (order.customer == "CARDMASTERS CEBU", "Cebu", "customer"),
        (order.customer == "CARDMASTERS MAKATI", "Makati", "customer"),
    ]
    for matched, branch, reason in rules:
        if matched:
            targets.add(branch)
            reasons.append(reason)
    if len(targets) > 1:
        raise ValueError(f"Conflicting branch rules for {order.name}: {sorted(targets)}")
    return next(iter(targets), None), reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--output", required=True, help="New JSON audit file; never overwritten")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, help="Maximum eligible records per run")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    output = Path(args.output).resolve()
    if output.exists():
        parser.error("Output file already exists; choose a new path")
    frappe.init(site=args.site)
    frappe.connect()
    report = {"site": args.site, "created": datetime.now(timezone.utc).isoformat(),
              "status": "preview", "scope": "All dates; draft and submitted orders",
              "changes": [], "rd_checks": [], "errors": []}
    try:
        for dt, field in [("Sales Order", "custom_for_branch"),
                          ("Sales Order", "branch"), ("Sales Order Item", "branch"),
                          ("Credit Memo", "commercial_amount")]:
            if not frappe.get_meta(dt).has_field(field):
                raise ValueError(f"Missing required field: {dt}.{field}")
        for branch in ("Makati", "Cebu"):
            if not frappe.db.exists("Branch", branch):
                raise ValueError(f"Branch does not exist: {branch}")
        orders = frappe.db.sql("""
            SELECT name, customer, branch, custom_for_branch, company, docstatus,
                   status, grand_total, currency, per_billed, modified, modified_by
            FROM `tabSales Order`
            WHERE docstatus < 2 AND (
                name IN ('SO-023593', 'SO-023584') OR custom_for_branch = 'Makati'
                OR customer IN ('CARDMASTERS CEBU', 'CARDMASTERS MAKATI', 'CARDMASTERS R&D'))
            ORDER BY name
        """ + (" FOR UPDATE" if args.apply else ""), as_dict=True)
        names = {o.name for o in orders}
        for name in ("SO-023593", "SO-023584"):
            if name not in names:
                report["errors"].append(f"Explicit order missing or cancelled: {name}")
        for index, order in enumerate(orders, 1):
            if index == 1 or index % 100 == 0:
                print(f"Checking Sales Order {index}/{len(orders)}")
            if order.customer == "CARDMASTERS R&D":
                memos = frappe.get_all("Credit Memo", filters={"sales_order": order.name},
                                       fields=["name", "docstatus", "commercial_amount"])
                submitted = [m for m in memos if m.docstatus == 1]
                # Do not sum multiple replacement commercial amounts or silently choose one.
                result = "missing submitted credit memo" if not submitted else (
                    "multiple submitted credit memos" if len(submitted) > 1 else (
                        "match" if submitted[0].commercial_amount is not None and
                        Decimal(str(submitted[0].commercial_amount)) == Decimal(str(order.grand_total))
                        else "commercial amount mismatch"))
                report["rd_checks"].append({"order": order.name, "grand_total": order.grand_total,
                                             "result": result, "credit_memos": memos})
            try:
                target, reasons = target_branch(order)
            except ValueError as exc:
                report["errors"].append(str(exc))
                continue
            if not target or (args.limit and len(report["changes"]) >= args.limit):
                continue
            items = frappe.db.sql("SELECT name, branch FROM `tabSales Order Item` WHERE parent=%s ORDER BY name" +
                                  (" FOR UPDATE" if args.apply else ""), order.name, as_dict=True)
            if order.branch == target and all(i.branch == target for i in items):
                continue
            report["changes"].append({"before": dict(order), "items_before": items,
                                      "target": target, "reasons": reasons,
                                      "future_invoice_attention": float(order.per_billed or 0) < 100})
        if args.apply and report["errors"]:
            report["status"] = "blocked"
        elif args.apply:
            report["status"] = "prepared; commit not yet confirmed"
        # Durable before-image written before the first database update.
        with output.open("x") as handle:
            json.dump(report, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        if args.apply and report["errors"]:
            raise ValueError("Apply blocked; inspect errors in audit file")
        if args.apply:
            for index, change in enumerate(report["changes"], 1):
                if index == 1 or index % 100 == 0:
                    print(f"Applying order {index}/{len(report['changes'])}")
                name, target = change["before"]["name"], change["target"]
                # Deliberately bypass document hooks; only these two tables are modified.
                frappe.db.sql("UPDATE `tabSales Order` SET branch=%s WHERE name=%s", (target, name))
                frappe.db.sql("UPDATE `tabSales Order Item` SET branch=%s WHERE parent=%s", (target, name))
                if frappe.db.get_value("Sales Order", name, "branch") != target:
                    raise ValueError(f"Header verification failed: {name}")
                if frappe.db.sql("SELECT name FROM `tabSales Order Item` WHERE parent=%s AND COALESCE(branch,'') != %s", (name, target)):
                    raise ValueError(f"Item verification failed: {name}")
            frappe.db.commit()
            report["status"] = "committed"
            # If this write fails, the prepared file still contains every before-image.
            output.write_text(json.dumps(report, indent=2, default=str))
            for change in report["changes"]:
                frappe.clear_document_cache("Sales Order", change["before"]["name"])
        else:
            frappe.db.rollback()
        print(f"{report['status']}: {len(report['changes'])} orders; "
              f"{sum(r['result'] != 'match' for r in report['rd_checks'])} R&D flags; "
              f"{len(report['errors'])} errors. Audit: {output}")
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
