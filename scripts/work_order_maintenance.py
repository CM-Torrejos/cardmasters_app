"""Standalone Work Order maintenance commands for bench Python."""
import argparse
import json
import os
from pathlib import Path

import frappe

from cardmasters_app.maintenance.legacy_work_orders import run as cleanup


def complete_operations(apply, output, limit=None):
    operation_filter = """
        FROM `tabWork Order` wo
        JOIN `tabWork Order Operation` op ON op.parent = wo.name
        WHERE op.parenttype = 'Work Order' AND op.parentfield = 'operations'
          AND wo.docstatus <> 2
          AND TRIM(wo.workflow_state) NOT IN ('', 'Draft', 'Not Started', 'In Production')
          AND COALESCE(op.custom_progress, '') <> 'Done'
    """
    params = {}
    if limit:
        parents = frappe.db.sql(
            "SELECT DISTINCT wo.name " + operation_filter + " ORDER BY wo.name LIMIT %s",
            (limit,), pluck=True,
        )
        if parents:
            operation_filter += " AND wo.name IN %(parents)s"
            params["parents"] = tuple(parents)
        else:
            operation_filter += " AND 1=0"
    query = "SELECT op.name, op.parent, op.custom_progress, wo.workflow_state " + operation_filter
    query += " ORDER BY wo.name, op.idx" + (" FOR UPDATE" if apply else "")
    rows = frappe.db.sql(query, params, as_dict=True)
    json.dump({"site": frappe.local.site, "apply": apply, "before": rows}, output, indent=2)
    output.flush()
    os.fsync(output.fileno())
    print(f"Matched {len(rows)} operation rows on {len({row.parent for row in rows})} Work Orders")
    if apply:
        for index, row in enumerate(rows, 1):
            frappe.db.set_value("Work Order Operation", row.name, "custom_progress", "Done",
                                update_modified=False)
            if index % 100 == 0 or index == len(rows):
                print(f"Updated {index}/{len(rows)} operation rows")
        for parent in sorted({row.parent for row in rows}):
            frappe.clear_document_cache("Work Order", parent)
        frappe.db.commit()
        print(f"COMMITTED: {len(rows)} operation rows")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", choices=["wo_cleanup", "wo_transition"])
    parser.add_argument("--site", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, help="Maximum eligible records per run")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    frappe.init(site=args.site)
    frappe.connect()
    try:
        frappe.set_user("Administrator")
        with args.output.open("x") as output:
            if args.job == "wo_cleanup":
                report = cleanup(apply=args.apply, limit=args.limit)
                json.dump(report, output, default=str)
                if report["failed"]:
                    raise RuntimeError(f"Some orders failed. See {args.output}")
            else:
                complete_operations(args.apply, output, args.limit)
    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == "__main__":
    main()
