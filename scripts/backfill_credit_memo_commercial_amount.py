"""Copy legacy Amount to Sponsored Amount and derive Commercial Amount.

Run using bench Python from the bench sites directory. Defaults to dry run.
See backfill_credit_memo_commercial_amount.md for commands.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import frappe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--output", required=True, help="New JSON audit file")
    parser.add_argument("--apply", action="store_true", help="Commit the changes")
    parser.add_argument("--limit", type=int, help="Maximum eligible records per run")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    output = Path(args.output).resolve()
    if output.exists():
        parser.error("Audit file already exists; choose a new output path")

    frappe.init(site=args.site)
    frappe.connect()
    try:
        rows = frappe.db.sql(
            """
            SELECT cm.name, cm.sales_order, so.transaction_date AS sales_order_date,
                   cm.docstatus, cm.commercial_amount, cm.sponsored_amount, cm.amount,
                   so.grand_total AS sales_order_grand_total,
                   cm.modified, cm.modified_by
            FROM `tabCredit Memo` cm
            JOIN `tabSales Order` so ON so.name = cm.sales_order
            WHERE cm.docstatus = 1
              AND cm.sponsored_amount = 0
              AND cm.commercial_amount = 0
              AND cm.amount > 0
            ORDER BY cm.name
            """ + (f" LIMIT {args.limit}" if args.limit else "") + (" FOR UPDATE" if args.apply else ""),
            as_dict=True,
        )
        changes = []
        for row in rows:
            sponsored = Decimal(str(row.amount))
            commercial = Decimal(str(row.sales_order_grand_total)) - sponsored
            changes.append({"name": row.name, "sponsored_amount": sponsored,
                            "commercial_amount": commercial})
        total = sum((Decimal(str(row.amount)) for row in rows), Decimal("0"))
        report = {
            "site": args.site,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if args.apply else "dry_run",
            "scope": "Submitted linked Credit Memos across all dates with both totals zero and positive hidden amount",
            "count": len(rows),
            "total_amount": str(total),
            "before": [dict(row) for row in rows],
            "changes": changes,
            "operation": "sponsored_amount = amount; commercial_amount = Sales Order grand_total - amount",
            "note": "Before-image only. This file does not prove that the transaction committed.",
        }
        # Save a durable before-image before changing any database records.
        with output.open("x") as handle:
            json.dump(report, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())

        print(f"Matched {len(rows)} submitted memos; total Amount: {total:,.2f}")
        print(f"Memos needing changes: {len(changes)}")
        print(f"Audit file: {output}")
        if not args.apply:
            frappe.db.rollback()
            print("DRY RUN: no records changed. Use --apply to commit.")
            return

        for index, change in enumerate(changes, 1):
            # Intentionally bypass submitted-document validation and client formulas.
            frappe.db.sql(
                """UPDATE `tabCredit Memo`
                   SET sponsored_amount = %s, commercial_amount = %s
                   WHERE name = %s AND docstatus = 1
                     AND amount > 0""",
                (change["sponsored_amount"], change["commercial_amount"], change["name"]),
            )
            actual = frappe.db.get_value("Credit Memo", change["name"],
                                         ["sponsored_amount", "commercial_amount"])
            if tuple(Decimal(str(value)) for value in actual) != (
                    change["sponsored_amount"], change["commercial_amount"]):
                raise RuntimeError(f"Verification failed for {change['name']}; rolling back")
            if index % 100 == 0 or index == len(changes):
                print(f"Verified {index}/{len(changes)} Credit Memos")
        frappe.db.commit()
        print(f"COMMITTED: updated and verified {len(changes)} credit memos.")
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
