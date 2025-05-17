import frappe

def execute(filters=None):
    # default filter
    status = (filters or {}).get("status") or "pending"

    # build your filters
    conditions = []
    if status == "pending":
        conditions.append(["workflow_state", "!=", "Client Approved"])
    else:  # finished
        conditions.append(["workflow_state", "=", "Client Approved"])

    # fetch all rows, ordered by artist then name
    rows = frappe.get_all(
        "Artist Sheet",
        filters=conditions,
        fields=["name", "artist", "workflow_state"],
        order_by="artist asc, name asc"
    )

    # build columns
    columns = [
        {"fieldname": "artist",        "label": "Artist",        "fieldtype": "Link", "options": "User",         "width": 200},
        {"fieldname": "name",          "label": "Artist Sheet",  "fieldtype": "Link", "options": "Artist Sheet", "width": 200},
        {"fieldname": "workflow_state","label": "Workflow State","fieldtype": "Data",                         "width": 150},
    ]

    # blank out duplicate artists
    data = []
    last_artist = None
    for r in rows:
        row_artist = r.artist if r.artist != last_artist else ""
        data.append({
            "artist":         row_artist,
            "name":           r.name,
            "workflow_state": r.workflow_state
        })
        last_artist = r.artist

    return columns, data
