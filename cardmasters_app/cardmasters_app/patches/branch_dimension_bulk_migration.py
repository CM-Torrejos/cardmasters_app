"""Bulk historical Branch migration for ERPNext.

Validated migration routes for this site:

Native repost:
- Sales Invoice
- Purchase Invoice
- Payment Entry
- Journal Entry, except Opening Entry

Direct classification backfill:
- Opening Journal Entry: source + active GL + active Payment Ledger
- Delivery Note: source + active GL
- Purchase Receipt: source + active GL
- Stock Entry: source + active GL
- Stock Reconciliation: source + active GL

Usage examples:

    bench --site ams.localhost execute \
      cardmasters_app.cardmasters_app.patches.branch_dimension_bulk_migration.run \
      --kwargs '{"dry_run": 1}'

    bench --site ams.localhost execute \
      cardmasters_app.cardmasters_app.patches.branch_dimension_bulk_migration.run \
      --kwargs '{"dry_run": 0, "batch_size": 100}'

    bench --site ams.localhost execute \
      cardmasters_app.cardmasters_app.patches.branch_dimension_bulk_migration.audit

Important:
- Temporarily unfreeze the accounting period before the live run.
- Allow native voucher types in Repost Accounting Ledger Settings.
- Run first on a freshly restored database.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import Any

import frappe
from frappe.utils import cint, flt, getdate, now_datetime


# =============================================================================
# CONFIGURATION
# =============================================================================

COMPANY = "CARDMASTERS CDO"
TARGET_BRANCH = "Cagayan de Oro"
BRANCH_FIELD = "branch"
CUTOFF_DATE = "2026-07-15"
DEFAULT_BATCH_SIZE = 100
PRECISION = 6

NATIVE_REPOST_TYPES = (
    "Sales Invoice",
    "Purchase Invoice",
    "Payment Entry",
    "Journal Entry",
)

DIRECT_GL_TYPES = (
    "Delivery Note",
    "Purchase Receipt",
    "Stock Entry",
    "Stock Reconciliation",
)

ALL_TYPES = NATIVE_REPOST_TYPES + DIRECT_GL_TYPES

DATE_FIELD_BY_DOCTYPE = {
    "Sales Invoice": "posting_date",
    "Purchase Invoice": "posting_date",
    "Payment Entry": "posting_date",
    "Journal Entry": "posting_date",
    "Delivery Note": "posting_date",
    "Purchase Receipt": "posting_date",
    "Stock Entry": "posting_date",
    "Stock Reconciliation": "posting_date",
}


# =============================================================================
# RESULT MODEL
# =============================================================================

@dataclass
class MigrationStats:
    processed: int = 0
    migrated: int = 0
    skipped: int = 0
    failed: int = 0
    source_updates: int = 0
    gl_updates: int = 0
    ple_updates: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "migrated": self.migrated,
            "skipped": self.skipped,
            "failed": self.failed,
            "source_updates": self.source_updates,
            "gl_updates": self.gl_updates,
            "ple_updates": self.ple_updates,
            "failures": self.failures,
        }


# =============================================================================
# HELPERS
# =============================================================================

def _number(value: Any) -> float:
    return round(flt(value), PRECISION)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _heading(title: str) -> None:
    print()
    print("=" * 110)
    print(title)
    print("=" * 110)


def _is_opening_journal_entry(doc) -> bool:
    return (
        _text(doc.get("is_opening")) == "Yes"
        or _text(doc.get("voucher_type")) == "Opening Entry"
    )


def _get_date_field(doctype: str) -> str:
    fieldname = DATE_FIELD_BY_DOCTYPE.get(doctype)
    if not fieldname:
        frappe.throw(f"No date field configured for {doctype}.")
    return fieldname


def _validate_configuration() -> None:
    if not frappe.db.exists("Company", COMPANY):
        frappe.throw(f"Company does not exist: {COMPANY}")

    if not frappe.db.exists("Branch", TARGET_BRANCH):
        frappe.throw(f"Branch does not exist: {TARGET_BRANCH}")

    if not frappe.get_meta("GL Entry").has_field(BRANCH_FIELD):
        frappe.throw("GL Entry does not have the Branch accounting-dimension field.")

    if not frappe.get_meta("Payment Ledger Entry").has_field(BRANCH_FIELD):
        frappe.throw("Payment Ledger Entry does not have the Branch field.")


def _source_branch_locations(doc) -> list[tuple[str, str, str | None]]:
    """Return (doctype, name, branch_value) for every applicable source location."""
    locations: list[tuple[str, str, str | None]] = []

    if doc.meta.has_field(BRANCH_FIELD):
        locations.append((doc.doctype, doc.name, doc.get(BRANCH_FIELD)))

    for df in doc.meta.fields:
        if df.fieldtype != "Table":
            continue

        for row in doc.get(df.fieldname) or []:
            if row.meta.has_field(BRANCH_FIELD):
                locations.append((row.doctype, row.name, row.get(BRANCH_FIELD)))

    return locations


def _assert_no_conflicting_source_branch(doc) -> None:
    conflicts = []

    for row_doctype, row_name, value in _source_branch_locations(doc):
        if value and value != TARGET_BRANCH:
            conflicts.append(f"{row_doctype} {row_name}: {value}")

    if conflicts:
        frappe.throw(
            "Conflicting Branch values found; refusing to overwrite:\n"
            + "\n".join(conflicts)
        )


def _set_source_branch_on_doc(doc) -> int:
    """Set Branch in-memory for native save/repost."""
    updated = 0

    if doc.meta.has_field(BRANCH_FIELD) and doc.get(BRANCH_FIELD) != TARGET_BRANCH:
        doc.set(BRANCH_FIELD, TARGET_BRANCH)
        updated += 1

    for df in doc.meta.fields:
        if df.fieldtype != "Table":
            continue

        for row in doc.get(df.fieldname) or []:
            if not row.meta.has_field(BRANCH_FIELD):
                continue
            if row.get(BRANCH_FIELD) == TARGET_BRANCH:
                continue
            row.set(BRANCH_FIELD, TARGET_BRANCH)
            updated += 1

    return updated


def _set_source_branch_directly(doc) -> int:
    """Set only source Branch columns, without document hooks or reposting."""
    updated = 0

    if doc.meta.has_field(BRANCH_FIELD):
        current = doc.get(BRANCH_FIELD)
        if current != TARGET_BRANCH:
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


def _verify_source_branch(doc) -> None:
    doc.reload()
    missing = []

    for row_doctype, row_name, value in _source_branch_locations(doc):
        if value != TARGET_BRANCH:
            missing.append(f"{row_doctype} {row_name}: {value}")

    if missing:
        frappe.throw(
            "Source Branch verification failed:\n" + "\n".join(missing)
        )


def _active_gl_snapshot(doctype: str, name: str) -> dict[str, Any]:
    rows = frappe.db.sql(
        """
        SELECT
            account,
            party_type,
            party,
            against,
            against_voucher_type,
            against_voucher,
            debit,
            credit,
            debit_in_account_currency,
            credit_in_account_currency,
            account_currency,
            cost_center,
            project,
            finance_book,
            branch
        FROM `tabGL Entry`
        WHERE voucher_type = %s
          AND voucher_no = %s
          AND is_cancelled = 0
        ORDER BY
            account,
            party_type,
            party,
            against_voucher_type,
            against_voucher,
            debit,
            credit
        """,
        (doctype, name),
        as_dict=True,
    )

    signature = []
    total_debit = 0.0
    total_credit = 0.0
    branches = []

    for row in rows:
        total_debit += flt(row.debit)
        total_credit += flt(row.credit)
        branches.append(row.branch)
        signature.append(
            (
                _text(row.account),
                _text(row.party_type),
                _text(row.party),
                _text(row.against),
                _text(row.against_voucher_type),
                _text(row.against_voucher),
                _number(row.debit),
                _number(row.credit),
                _number(row.debit_in_account_currency),
                _number(row.credit_in_account_currency),
                _text(row.account_currency),
                _text(row.cost_center),
                _text(row.project),
                _text(row.finance_book),
            )
        )

    signature.sort()

    return {
        "count": len(rows),
        "debit": _number(total_debit),
        "credit": _number(total_credit),
        "signature": signature,
        "branches": branches,
    }


def _active_ple_snapshot(doctype: str, name: str) -> dict[str, Any]:
    meta = frappe.get_meta("Payment Ledger Entry")
    filters = {"voucher_type": doctype, "voucher_no": name}

    if meta.has_field("delinked"):
        filters["delinked"] = 0

    fields = [
        "account",
        "party_type",
        "party",
        "against_voucher_type",
        "against_voucher_no",
        "amount",
        "branch",
    ]
    fields = [fieldname for fieldname in fields if meta.has_field(fieldname)]

    rows = frappe.get_all(
        "Payment Ledger Entry",
        filters=filters,
        fields=fields,
        order_by="creation asc",
    )

    signature = []
    total_amount = 0.0
    branches = []

    for row in rows:
        total_amount += flt(row.get("amount"))
        branches.append(row.get(BRANCH_FIELD))
        signature.append(
            (
                _text(row.get("account")),
                _text(row.get("party_type")),
                _text(row.get("party")),
                _text(row.get("against_voucher_type")),
                _text(row.get("against_voucher_no")),
                _number(row.get("amount")),
            )
        )

    signature.sort()

    return {
        "count": len(rows),
        "amount": _number(total_amount),
        "signature": signature,
        "branches": branches,
    }


def _stock_ledger_snapshot(doctype: str, name: str) -> dict[str, Any]:
    rows = frappe.db.sql(
        """
        SELECT
            item_code,
            warehouse,
            actual_qty,
            qty_after_transaction,
            valuation_rate,
            stock_value,
            stock_value_difference,
            batch_no,
            serial_no
        FROM `tabStock Ledger Entry`
        WHERE voucher_type = %s
          AND voucher_no = %s
          AND is_cancelled = 0
        ORDER BY item_code, warehouse, posting_date, posting_time, creation
        """,
        (doctype, name),
        as_dict=True,
    )

    signature = []
    for row in rows:
        signature.append(
            (
                _text(row.item_code),
                _text(row.warehouse),
                _number(row.actual_qty),
                _number(row.qty_after_transaction),
                _number(row.valuation_rate),
                _number(row.stock_value),
                _number(row.stock_value_difference),
                _text(row.batch_no),
                _text(row.serial_no),
            )
        )

    signature.sort()
    return {"count": len(rows), "signature": signature}


def _assert_snapshot_unchanged(before: dict[str, Any], after: dict[str, Any], label: str) -> None:
    for key in before:
        if key == "branches":
            continue
        if before[key] != after[key]:
            frappe.throw(
                f"{label} changed for key {key}.\n"
                f"Before: {before[key]}\nAfter: {after[key]}"
            )


def _assert_active_branches(snapshot: dict[str, Any], label: str) -> None:
    missing = [value for value in snapshot.get("branches", []) if value != TARGET_BRANCH]
    if missing:
        frappe.throw(f"{label} still has blank/conflicting active Branch values: {missing[:5]}")


def _update_active_gl_branch(doctype: str, name: str) -> int:
    return frappe.db.sql(
        """
        UPDATE `tabGL Entry`
        SET branch = %s
        WHERE voucher_type = %s
          AND voucher_no = %s
          AND is_cancelled = 0
          AND IFNULL(branch, '') = ''
        """,
        (TARGET_BRANCH, doctype, name),
    ) or 0


def _update_active_ple_branch(doctype: str, name: str) -> int:
    meta = frappe.get_meta("Payment Ledger Entry")
    delink_condition = "AND delinked = 0" if meta.has_field("delinked") else ""

    return frappe.db.sql(
        f"""
        UPDATE `tabPayment Ledger Entry`
        SET branch = %s
        WHERE voucher_type = %s
          AND voucher_no = %s
          {delink_condition}
          AND IFNULL(branch, '') = ''
        """,
        (TARGET_BRANCH, doctype, name),
    ) or 0


def _count_active_blank_gl(doctype: str, name: str) -> int:
    return cint(
        frappe.db.sql(
            """
            SELECT COUNT(*)
            FROM `tabGL Entry`
            WHERE voucher_type = %s
              AND voucher_no = %s
              AND is_cancelled = 0
              AND IFNULL(branch, '') = ''
            """,
            (doctype, name),
        )[0][0]
    )


def _count_active_blank_ple(doctype: str, name: str) -> int:
    meta = frappe.get_meta("Payment Ledger Entry")
    delink_condition = "AND delinked = 0" if meta.has_field("delinked") else ""
    return cint(
        frappe.db.sql(
            f"""
            SELECT COUNT(*)
            FROM `tabPayment Ledger Entry`
            WHERE voucher_type = %s
              AND voucher_no = %s
              {delink_condition}
              AND IFNULL(branch, '') = ''
            """,
            (doctype, name),
        )[0][0]
    )


def _needs_source_migration(doc) -> bool:
    locations = _source_branch_locations(doc)
    if not locations:
        return False
    return any(value != TARGET_BRANCH for _, _, value in locations)


# =============================================================================
# MIGRATION ROUTES
# =============================================================================

def _migrate_native(doc, dry_run: bool) -> dict[str, int]:
    """Native update-after-submit and ledger repost."""
    _assert_no_conflicting_source_branch(doc)

    before_gl = _active_gl_snapshot(doc.doctype, doc.name)
    before_ple = _active_ple_snapshot(doc.doctype, doc.name)
    before_sle = _stock_ledger_snapshot(doc.doctype, doc.name)

    source_updates = _set_source_branch_on_doc(doc)

    if dry_run:
        return {"source": source_updates, "gl": 0, "ple": 0}

    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True, ignore_version=True)
    doc.reload()

    after_gl = _active_gl_snapshot(doc.doctype, doc.name)
    after_ple = _active_ple_snapshot(doc.doctype, doc.name)
    after_sle = _stock_ledger_snapshot(doc.doctype, doc.name)

    _verify_source_branch(doc)
    _assert_snapshot_unchanged(before_gl, after_gl, "GL")
    _assert_snapshot_unchanged(before_ple, after_ple, "Payment Ledger")
    _assert_snapshot_unchanged(before_sle, after_sle, "Stock Ledger")
    _assert_active_branches(after_gl, "GL")
    _assert_active_branches(after_ple, "Payment Ledger")

    return {"source": source_updates, "gl": 0, "ple": 0}


def _migrate_opening_je_direct(doc, dry_run: bool) -> dict[str, int]:
    """Direct source + active GL + active Payment Ledger classification backfill."""
    _assert_no_conflicting_source_branch(doc)

    before_gl = _active_gl_snapshot(doc.doctype, doc.name)
    before_ple = _active_ple_snapshot(doc.doctype, doc.name)
    before_sle = _stock_ledger_snapshot(doc.doctype, doc.name)

    source_updates = sum(
        1 for _, _, value in _source_branch_locations(doc) if value != TARGET_BRANCH
    )
    gl_updates = _count_active_blank_gl(doc.doctype, doc.name)
    ple_updates = _count_active_blank_ple(doc.doctype, doc.name)

    if dry_run:
        return {"source": source_updates, "gl": gl_updates, "ple": ple_updates}

    source_updates = _set_source_branch_directly(doc)
    _update_active_gl_branch(doc.doctype, doc.name)
    _update_active_ple_branch(doc.doctype, doc.name)

    doc.reload()
    after_gl = _active_gl_snapshot(doc.doctype, doc.name)
    after_ple = _active_ple_snapshot(doc.doctype, doc.name)
    after_sle = _stock_ledger_snapshot(doc.doctype, doc.name)

    _verify_source_branch(doc)
    _assert_snapshot_unchanged(before_gl, after_gl, "GL")
    _assert_snapshot_unchanged(before_ple, after_ple, "Payment Ledger")
    _assert_snapshot_unchanged(before_sle, after_sle, "Stock Ledger")
    _assert_active_branches(after_gl, "GL")
    _assert_active_branches(after_ple, "Payment Ledger")

    return {"source": source_updates, "gl": gl_updates, "ple": ple_updates}


def _migrate_direct_gl(doc, dry_run: bool) -> dict[str, int]:
    """Direct source + active GL classification backfill; Stock Ledger is untouched."""
    _assert_no_conflicting_source_branch(doc)

    before_gl = _active_gl_snapshot(doc.doctype, doc.name)
    before_sle = _stock_ledger_snapshot(doc.doctype, doc.name)

    source_updates = sum(
        1 for _, _, value in _source_branch_locations(doc) if value != TARGET_BRANCH
    )
    gl_updates = _count_active_blank_gl(doc.doctype, doc.name)

    if dry_run:
        return {"source": source_updates, "gl": gl_updates, "ple": 0}

    source_updates = _set_source_branch_directly(doc)
    _update_active_gl_branch(doc.doctype, doc.name)

    doc.reload()
    after_gl = _active_gl_snapshot(doc.doctype, doc.name)
    after_sle = _stock_ledger_snapshot(doc.doctype, doc.name)

    _verify_source_branch(doc)
    _assert_snapshot_unchanged(before_gl, after_gl, "GL")
    _assert_snapshot_unchanged(before_sle, after_sle, "Stock Ledger")
    _assert_active_branches(after_gl, "GL")

    return {"source": source_updates, "gl": gl_updates, "ple": 0}

def _migrate_accounting_direct(doc, dry_run: bool) -> dict[str, int]:
    """
    Backfill Branch directly on the source document, active GL Entries,
    and active Payment Ledger Entries without reposting accounting.
    """
    _assert_no_conflicting_source_branch(doc)

    before_gl = _active_gl_snapshot(doc.doctype, doc.name)
    before_ple = _active_ple_snapshot(doc.doctype, doc.name)
    before_sle = _stock_ledger_snapshot(doc.doctype, doc.name)

    source_updates = sum(
        1
        for _, _, value in _source_branch_locations(doc)
        if value != TARGET_BRANCH
    )
    gl_updates = _count_active_blank_gl(doc.doctype, doc.name)
    ple_updates = _count_active_blank_ple(doc.doctype, doc.name)

    if dry_run:
        return {
            "source": source_updates,
            "gl": gl_updates,
            "ple": ple_updates,
        }

    source_updates = _set_source_branch_directly(doc)

    _update_active_gl_branch(doc.doctype, doc.name)
    _update_active_ple_branch(doc.doctype, doc.name)

    doc.reload()

    after_gl = _active_gl_snapshot(doc.doctype, doc.name)
    after_ple = _active_ple_snapshot(doc.doctype, doc.name)
    after_sle = _stock_ledger_snapshot(doc.doctype, doc.name)

    _verify_source_branch(doc)

    _assert_snapshot_unchanged(before_gl, after_gl, "GL")
    _assert_snapshot_unchanged(
        before_ple,
        after_ple,
        "Payment Ledger",
    )
    _assert_snapshot_unchanged(
        before_sle,
        after_sle,
        "Stock Ledger",
    )

    _assert_active_branches(after_gl, "GL")
    _assert_active_branches(
        after_ple,
        "Payment Ledger",
    )

    return {
        "source": source_updates,
        "gl": gl_updates,
        "ple": ple_updates,
    }


def _migrate_document(doc, dry_run: bool) -> dict[str, int]:
    if doc.doctype in {
        "Sales Invoice",
        "Purchase Invoice",
        "Payment Entry",
        "Journal Entry",
    }:
        return _migrate_accounting_direct(doc, dry_run)

    if doc.doctype in DIRECT_GL_TYPES:
        return _migrate_direct_gl(doc, dry_run)

    frappe.throw(f"No migration route configured for {doc.doctype}.")


# =============================================================================
# DOCUMENT DISCOVERY
# =============================================================================

def _get_candidate_names(doctype: str, start_after: str | None = None) -> list[str]:
    date_field = _get_date_field(doctype)

    filters: dict[str, Any] = {
        "company": COMPANY,
        "docstatus": 1,
        date_field: ["<=", CUTOFF_DATE],
    }

    if start_after:
        filters["name"] = [">", start_after]

    return frappe.get_all(
        doctype,
        filters=filters,
        pluck="name",
        order_by="name asc",
        limit_page_length=0,
    )


def _document_needs_any_migration(doc) -> bool:
    if _needs_source_migration(doc):
        return True

    if _count_active_blank_gl(doc.doctype, doc.name):
        return True

    if doc.doctype == "Journal Entry" and _is_opening_journal_entry(doc):
        if _count_active_blank_ple(doc.doctype, doc.name):
            return True

    return False


# =============================================================================
# PUBLIC ENTRY POINTS
# =============================================================================

def run(
    dry_run: int | bool = 1,
    batch_size: int = DEFAULT_BATCH_SIZE,
    only_doctype: str | None = None,
    stop_on_error: int | bool = 0,
) -> dict[str, Any]:
    """Run the bulk migration.

    Args:
        dry_run: 1 prints scope without writes; 0 performs migration.
        batch_size: commit after this many successful/processed documents.
        only_doctype: optional single DocType for staged execution.
        stop_on_error: 1 raises immediately; 0 logs and continues.
    """
    _validate_configuration()

    dry_run = bool(cint(dry_run))
    batch_size = max(cint(batch_size), 1)
    stop_on_error = bool(cint(stop_on_error))

    doctypes = list(ALL_TYPES)
    if only_doctype:
        if only_doctype not in doctypes:
            frappe.throw(f"Unsupported only_doctype: {only_doctype}")
        doctypes = [only_doctype]

    stats_by_type: dict[str, MigrationStats] = {}
    started_at = now_datetime()

    _heading("BRANCH ACCOUNTING DIMENSION BULK MIGRATION")
    print("Started:", started_at)
    print("Company:", COMPANY)
    print("Target Branch:", TARGET_BRANCH)
    print("Cutoff Date:", CUTOFF_DATE)
    print("Dry Run:", dry_run)
    print("Batch Size:", batch_size)
    print("DocTypes:", ", ".join(doctypes))

    for doctype in doctypes:
        _heading(f"PROCESSING {doctype}")
        stats = MigrationStats()
        stats_by_type[doctype] = stats
        names = _get_candidate_names(doctype)
        print("Submitted candidates:", len(names))

        for index, name in enumerate(names, start=1):
            stats.processed += 1
            savepoint = f"branch_migration_{doctype.replace(' ', '_')}_{index}"

            try:
                frappe.db.savepoint(savepoint)
                doc = frappe.get_doc(doctype, name)

                if not _document_needs_any_migration(doc):
                    stats.skipped += 1
                else:
                    changes = _migrate_document(doc, dry_run)
                    stats.migrated += 1
                    stats.source_updates += cint(changes.get("source"))
                    stats.gl_updates += cint(changes.get("gl"))
                    stats.ple_updates += cint(changes.get("ple"))

                if index % batch_size == 0:
                    if dry_run:
                        frappe.db.rollback()
                    else:
                        frappe.db.commit()
                    print(
                        f"{doctype}: {index}/{len(names)} | "
                        f"migrated={stats.migrated} skipped={stats.skipped} failed={stats.failed}"
                    )

            except Exception as exc:
                frappe.db.rollback(save_point=savepoint)
                stats.failed += 1
                failure = {
                    "doctype": doctype,
                    "name": name,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
                stats.failures.append(failure)
                print(f"ERROR {doctype} {name}: {exc}")

                if stop_on_error:
                    frappe.db.rollback()
                    raise

        if dry_run:
            frappe.db.rollback()
        else:
            frappe.db.commit()

        print(json.dumps(stats.as_dict(), indent=2, default=str))

    finished_at = now_datetime()
    summary = {
        "started_at": started_at,
        "finished_at": finished_at,
        "dry_run": dry_run,
        "company": COMPANY,
        "target_branch": TARGET_BRANCH,
        "cutoff_date": CUTOFF_DATE,
        "stats": {doctype: stats.as_dict() for doctype, stats in stats_by_type.items()},
    }

    _heading("MIGRATION SUMMARY")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def audit() -> dict[str, Any]:
    """Post-migration audit. Read-only."""
    _validate_configuration()
    results: dict[str, Any] = {}

    _heading("POST-MIGRATION BRANCH AUDIT")

    for doctype in ALL_TYPES:
        date_field = _get_date_field(doctype)
        table = f"tab{doctype}"

        submitted_blank_header = None
        if frappe.get_meta(doctype).has_field(BRANCH_FIELD):
            submitted_blank_header = frappe.db.sql(
                f"""
                SELECT COUNT(*)
                FROM `{table}`
                WHERE company = %s
                  AND docstatus = 1
                  AND `{date_field}` <= %s
                  AND IFNULL(branch, '') = ''
                """,
                (COMPANY, CUTOFF_DATE),
            )[0][0]

        active_blank_gl = frappe.db.sql(
            """
            SELECT COUNT(*)
            FROM `tabGL Entry`
            WHERE company = %s
              AND posting_date <= %s
              AND voucher_type = %s
              AND is_cancelled = 0
              AND IFNULL(branch, '') = ''
            """,
            (COMPANY, CUTOFF_DATE, doctype),
        )[0][0]

        results[doctype] = {
            "submitted_blank_header": submitted_blank_header,
            "active_blank_gl": active_blank_gl,
        }

    active_blank_ple = frappe.db.sql(
        """
        SELECT COUNT(*)
        FROM `tabPayment Ledger Entry`
        WHERE company = %s
          AND posting_date <= %s
          AND delinked = 0
          AND IFNULL(branch, '') = ''
        """,
        (COMPANY, CUTOFF_DATE),
    )[0][0]

    results["Payment Ledger Entry"] = {"active_blank": active_blank_ple}

    gl_totals = frappe.db.sql(
        """
        SELECT
            ROUND(SUM(debit), 6) AS debit,
            ROUND(SUM(credit), 6) AS credit,
            ROUND(SUM(debit - credit), 6) AS net
        FROM `tabGL Entry`
        WHERE company = %s
          AND posting_date <= %s
          AND is_cancelled = 0
        """,
        (COMPANY, CUTOFF_DATE),
        as_dict=True,
    )[0]

    branch_gl_totals = frappe.db.sql(
        """
        SELECT
            ROUND(SUM(debit), 6) AS debit,
            ROUND(SUM(credit), 6) AS credit,
            ROUND(SUM(debit - credit), 6) AS net
        FROM `tabGL Entry`
        WHERE company = %s
          AND posting_date <= %s
          AND is_cancelled = 0
          AND branch = %s
        """,
        (COMPANY, CUTOFF_DATE, TARGET_BRANCH),
        as_dict=True,
    )[0]

    results["GL Totals"] = {
        "company": dict(gl_totals),
        "target_branch": dict(branch_gl_totals),
        "match": dict(gl_totals) == dict(branch_gl_totals),
    }

    print(json.dumps(results, indent=2, default=str))
    return results