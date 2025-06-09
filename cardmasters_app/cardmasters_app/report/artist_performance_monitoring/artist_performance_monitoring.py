# Copyright (c) 2025, Shan Torrejos and contributors
# For license information, please see license.txt

# import frappe

# Copyright (c) 2025, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt

def execute(filters=None):
    filters    = filters or {}
    from_date  = filters.get("from_date")
    to_date    = filters.get("to_date")

    # Build WHERE clauses and params
    clauses = ["acard.workflow_state = %s"]
    params  = ["Client Approved"]

    if from_date:
        clauses.append("DATE(acard.creation) >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("DATE(acard.creation) <= %s")
        params.append(to_date)

    where_sql = " AND ".join(clauses)

    # Fetch averages per artist
    rows = frappe.db.sql(f"""
        SELECT
            acard.artist             AS artist_id,
            emp.first_name            AS artist,
            AVG(acard.expected_total_time)    AS avg_expected_total_time,
            AVG(acard.total_time_in_minutes)  AS avg_finished_total_time,
            AVG(CAST(acard.difficulty AS UNSIGNED)) AS avg_difficulty,
            AVG(acard.time_difference)        AS avg_time_difference
        FROM `tabArtist Card` AS acard
        LEFT JOIN `tabEmployee` AS emp
            ON emp.name = acard.artist
        WHERE {where_sql}
        GROUP BY acard.artist, emp.first_name
        ORDER BY emp.first_name
    """, tuple(params), as_dict=True)

    # Prepare data
    data = []
    for r in rows:
        data.append({
            "artist":                   r.artist,
            "avg_expected_total_time":  flt(r.avg_expected_total_time or 0),
            "avg_finished_total_time":  flt(r.avg_finished_total_time or 0),
            "avg_difficulty":           flt(r.avg_difficulty or 0),
            "avg_time_difference":      flt(r.avg_time_difference or 0),
        })

    # Define columns
    columns = [
        {"fieldname":"artist",                  "label":"Artist",                       "fieldtype":"Data",  "width":150},
        {"fieldname":"avg_expected_total_time", "label":"Avg. Expected Total Time",      "fieldtype":"Float", "width":180},
        {"fieldname":"avg_finished_total_time", "label":"Avg. Finished Total Time",      "fieldtype":"Float", "width":180},
        {"fieldname":"avg_difficulty",          "label":"Avg. Difficulty",              "fieldtype":"Float", "width":120},
        {"fieldname":"avg_time_difference",     "label":"Avg. Time Difference (min)",   "fieldtype":"Float", "width":180},
    ]

    return columns, data
