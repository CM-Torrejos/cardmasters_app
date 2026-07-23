from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import Any

import frappe
from frappe.utils import cint, now_datetime


COMPANY = "CARDMASTERS CDO"
TARGET_BRANCH = "Cagayan de Oro"
CUTOFF_DATE = "2026-07-22"
BRANCH_FIELD = "branch"
DEFAULT_BATCH_SIZE = 500


@dataclass
class MigrationStats:
    processed: int = 0
    migrated: int = 0
    skipped: int = 0
    failed: int = 0
    source_updates: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "migrated": self.migrated,
            "skipped": self.skipped,
            "failed": self.failed,
            "source_updates": self.source_updates,
            "failures": self.failures,
        }


def _heading(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def _validate_configuration() -> None:
    if not frappe.db.exists("Company", COMPANY):
        frappe.throw(f"Company does not exist: {COMPANY}")

    if not frappe.db.exists("Branch", TARGET_BRANCH):
        frappe.throw(f"Branch does not exist: {TARGET_BRANCH}")

    if not frappe.get_meta("Sales Order").has_field(BRANCH_FIELD):
        frappe.throw("Sales Order does not have a Branch field.")


def _source_branch_locations(doc) -> list[tuple[str, str, str | None]]:
    locations = []

    if doc.meta.has_field(BRANCH_FIELD):
        locations.append(
            (doc.doctype, doc.name, doc.get(BRANCH_FIELD))
        )

    for df in doc.meta.fields:
        if df.fieldtype != "Table":
            continue

        for row in doc.get(df.fieldname) or []:
            if row.meta.has_field(BRANCH_FIELD):
                locations.append(
                    (row.doctype, row.name, row.get(BRANCH_FIELD))
                )

    return locations


def _assert_no_conflicts(doc) -> None:
    conflicts = []

    for row_doctype, row_name, branch in _source_branch_locations(doc):
        if branch and branch != TARGET_BRANCH:
            conflicts.append(
                f"{row_doctype} {row_name}: {branch}"
            )

    if conflicts:
        frappe.throw(
            "Conflicting Branch values found; refusing to overwrite:\n"
            + "\n".join(conflicts)
        )


def _count_updates_needed(doc) -> int:
    return sum(
        1
        for _, _, branch in _source_branch_locations(doc)
        if branch != TARGET_BRANCH
    )


def _set_branch_directly(doc) -> int:
    updated = 0

    if (
        doc.meta.has_field(BRANCH_FIELD)
        and doc.get(BRANCH_FIELD) != TARGET_BRANCH
    ):
        frappe.db.set_value(
            doc.doctype,
            doc.name,
            BRANCH_FIELD,
            TARGET_BRANCH,
            update_modified=False,
        )
        updated += 1

    for df in doc.meta.fields:
        if df.fieldtype != "Table":
            continue

        for row in doc.get(df.fieldname) or []:
            if not row.meta.has_field(BRANCH_FIELD):
                continue

            if row.get(BRANCH_FIELD) == TARGET_BRANCH:
                continue

            frappe.db.set_value(
                row.doctype,
                row.name,
                BRANCH_FIELD,
                TARGET_BRANCH,
                update_modified=False,
            )
            updated += 1

    return updated


def _verify(doc) -> None:
    doc.reload()

    missing = []

    for row_doctype, row_name, branch in _source_branch_locations(doc):
        if branch != TARGET_BRANCH:
            missing.append(
                f"{row_doctype} {row_name}: {branch}"
            )

    if missing:
        frappe.throw(
            "Branch verification failed:\n"
            + "\n".join(missing)
        )


def _get_candidate_names(
    include_drafts: bool = True,
    include_cancelled: bool = False,
) -> list[str]:
    statuses = [1]

    if include_drafts:
        statuses.append(0)

    if include_cancelled:
        statuses.append(2)

    return frappe.get_all(
        "Sales Order",
        filters={
            "company": COMPANY,
            "docstatus": ["in", statuses],
            "transaction_date": ["<=", CUTOFF_DATE],
        },
        pluck="name",
        order_by="name asc",
        limit_page_length=0,
    )


def run(
    dry_run: int | bool = 1,
    batch_size: int = DEFAULT_BATCH_SIZE,
    include_drafts: int | bool = 1,
    include_cancelled: int | bool = 0,
    stop_on_error: int | bool = 0,
) -> dict[str, Any]:
    _validate_configuration()

    dry_run = bool(cint(dry_run))
    batch_size = max(cint(batch_size), 1)
    include_drafts = bool(cint(include_drafts))
    include_cancelled = bool(cint(include_cancelled))
    stop_on_error = bool(cint(stop_on_error))

    names = _get_candidate_names(
        include_drafts=include_drafts,
        include_cancelled=include_cancelled,
    )

    stats = MigrationStats()
    started_at = now_datetime()

    _heading("SALES ORDER BRANCH BACKFILL")

    print("Started:", started_at)
    print("Company:", COMPANY)
    print("Target Branch:", TARGET_BRANCH)
    print("Cutoff Date:", CUTOFF_DATE)
    print("Dry Run:", dry_run)
    print("Include Drafts:", include_drafts)
    print("Include Cancelled:", include_cancelled)
    print("Candidates:", len(names))

    for index, name in enumerate(names, start=1):
        stats.processed += 1
        savepoint = f"sales_order_branch_{index}"

        try:
            frappe.db.savepoint(savepoint)

            doc = frappe.get_doc("Sales Order", name)

            _assert_no_conflicts(doc)

            updates_needed = _count_updates_needed(doc)

            if updates_needed == 0:
                stats.skipped += 1
            else:
                if dry_run:
                    actual_updates = updates_needed
                else:
                    actual_updates = _set_branch_directly(doc)
                    _verify(doc)

                stats.migrated += 1
                stats.source_updates += actual_updates

            if index % batch_size == 0:
                if dry_run:
                    frappe.db.rollback()
                else:
                    frappe.db.commit()

                print(
                    f"Sales Order: {index}/{len(names)} | "
                    f"migrated={stats.migrated} "
                    f"skipped={stats.skipped} "
                    f"failed={stats.failed}"
                )

        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)

            stats.failed += 1
            stats.failures.append(
                {
                    "name": name,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

            print(f"ERROR Sales Order {name}: {exc}")

            if stop_on_error:
                frappe.db.rollback()
                raise

    if dry_run:
        frappe.db.rollback()
    else:
        frappe.db.commit()

    summary = {
        "started_at": started_at,
        "finished_at": now_datetime(),
        "dry_run": dry_run,
        "company": COMPANY,
        "target_branch": TARGET_BRANCH,
        "cutoff_date": CUTOFF_DATE,
        "include_drafts": include_drafts,
        "include_cancelled": include_cancelled,
        "stats": stats.as_dict(),
    }

    _heading("SALES ORDER MIGRATION SUMMARY")
    print(json.dumps(summary, indent=2, default=str))

    return summary


def audit(
    include_drafts: int | bool = 1,
    include_cancelled: int | bool = 0,
) -> dict[str, Any]:
    _validate_configuration()

    include_drafts = bool(cint(include_drafts))
    include_cancelled = bool(cint(include_cancelled))

    statuses = [1]

    if include_drafts:
        statuses.append(0)

    if include_cancelled:
        statuses.append(2)

    placeholders = ", ".join(["%s"] * len(statuses))

    blank_headers = frappe.db.sql(
        f"""
        SELECT COUNT(*)
        FROM `tabSales Order`
        WHERE company = %s
          AND docstatus IN ({placeholders})
          AND transaction_date <= %s
          AND IFNULL(branch, '') = ''
        """,
        tuple([COMPANY, *statuses, CUTOFF_DATE]),
    )[0][0]

    conflicting_headers = frappe.db.sql(
        f"""
        SELECT COUNT(*)
        FROM `tabSales Order`
        WHERE company = %s
          AND docstatus IN ({placeholders})
          AND transaction_date <= %s
          AND IFNULL(branch, '') NOT IN ('', %s)
        """,
        tuple([COMPANY, *statuses, CUTOFF_DATE, TARGET_BRANCH]),
    )[0][0]

    results = {
        "blank_headers": blank_headers,
        "conflicting_headers": conflicting_headers,
    }

    # Check Sales Order Item only if the accounting-dimension field exists there.
    if frappe.get_meta("Sales Order Item").has_field(BRANCH_FIELD):
        blank_items = frappe.db.sql(
            f"""
            SELECT COUNT(*)
            FROM `tabSales Order Item` soi
            INNER JOIN `tabSales Order` so
                ON so.name = soi.parent
            WHERE so.company = %s
              AND so.docstatus IN ({placeholders})
              AND so.transaction_date <= %s
              AND IFNULL(soi.branch, '') = ''
            """,
            tuple([COMPANY, *statuses, CUTOFF_DATE]),
        )[0][0]

        conflicting_items = frappe.db.sql(
            f"""
            SELECT COUNT(*)
            FROM `tabSales Order Item` soi
            INNER JOIN `tabSales Order` so
                ON so.name = soi.parent
            WHERE so.company = %s
              AND so.docstatus IN ({placeholders})
              AND so.transaction_date <= %s
              AND IFNULL(soi.branch, '') NOT IN ('', %s)
            """,
            tuple([COMPANY, *statuses, CUTOFF_DATE, TARGET_BRANCH]),
        )[0][0]

        results["blank_items"] = blank_items
        results["conflicting_items"] = conflicting_items
    else:
        results["blank_items"] = None
        results["conflicting_items"] = None

    _heading("SALES ORDER BRANCH AUDIT")
    print(json.dumps(results, indent=2, default=str))

    return results