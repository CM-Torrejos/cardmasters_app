# Copyright (c) 2025, Shan Torrejos and contributors
# For license information, please see license.txt
# import frappe


# your_app/your_app/report/artist_monitoring/artist_monitoring.py
import frappe
from frappe.utils import flt

def execute(filters=None):
    filters    = filters or {}
    status     = filters.get("status") or "pending"
    from_date  = filters.get("from_date")
    to_date    = filters.get("to_date")

    # decide operator for workflow_state
    op = "!=" if status == "pending" else "="

    # build WHERE clauses & params
    conditions = [f"acard.workflow_state {op} %s"]
    params     = ["Client Approved"]

    if from_date:
        conditions.append("DATE(acard.creation) >= %s")
        params.append(from_date)
    if to_date:
        conditions.append("DATE(acard.creation) <= %s")
        params.append(to_date)

    where_clause = " AND ".join(conditions)

    # pull all fields + join to Employee for first_name
    sheets = frappe.db.sql(f"""
        SELECT
            acard.name                  AS sheet_name,
            acard.artist                AS artist_id,
            emp.first_name               AS artist_name,
            acard.sales_order           AS sales_order,
            acard.workflow_state        AS workflow_state,
            acard.expected_total_time   AS expected_total_time,
            acard.total_time_in_minutes AS total_time
        FROM `tabArtist Card` AS acard
        LEFT JOIN `tabEmployee` emp
            ON emp.name = acard.artist
        WHERE {where_clause}
        ORDER BY acard.artist, acard.name
    """, tuple(params), as_dict=True)

    data = []
    last_artist_id = None
    sum_expected   = 0.0
    sum_total      = 0.0

    for s in sheets:
        artist_id    = s.artist_id
        display_name = s.artist_name or ""
        state        = s.workflow_state
        expected     = flt(s.expected_total_time or 0)
        total        = flt(s.total_time or 0)

        # when you hit a new artist, flush the previous artist’s subtotal
        if artist_id != last_artist_id and last_artist_id is not None:
            data.append(_make_summary_row(sum_expected, sum_total, status))
            sum_expected = 0.0
            sum_total    = 0.0

        # accumulate for the current artist
        sum_expected += expected
        if status == "finished":
            sum_total += total

        # detail row, blanking out repeat artist names
        data.append({
            "artist":             display_name if artist_id != last_artist_id else "",
            "sheet":              s.sheet_name,
            "sales_order":        s.sales_order,
            "workflow_state":     state,
            "expected_total_time": expected,
            **({"total_time": total} if status == "finished" else {})
        })

        last_artist_id = artist_id

    # final artist subtotal
    if last_artist_id is not None:
        data.append(_make_summary_row(sum_expected, sum_total, status))

    # column definitions
    columns = [
        {"fieldname":"artist",              "label":"Artist",              "fieldtype":"Data",  "width":150},
        {"fieldname":"sheet",               "label":"Artist Card",        "fieldtype":"Link",  "options":"Artist Card","width":200},
        {"fieldname":"sales_order",         "label":"Sales Order",         "fieldtype":"Link",  "options":"Sales Order", "width":150},
        {"fieldname":"workflow_state",      "label":"Workflow State",      "fieldtype":"Data",  "width":150},
        {"fieldname":"expected_total_time", "label":"Expected Total Time", "fieldtype":"Float", "width":150},
    ]
    if status == "finished":
        columns.append({
            "fieldname":"total_time",
            "label":"Total Time (min)",
            "fieldtype":"Float",
            "width":150
        })

    return columns, data


def _make_summary_row(sum_expected, sum_total, status):
    """Per-artist subtotal row."""
    row = {
        "artist":             "",
        "sheet":              "Total",
        "sales_order":        "",
        "workflow_state":     "",
        "expected_total_time": sum_expected
    }
    if status == "finished":
        row["total_time"] = sum_total
    return row
