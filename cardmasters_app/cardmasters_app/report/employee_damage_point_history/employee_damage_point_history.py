import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "incident_date", "label": "Date", "fieldtype": "Date", "width": 120},
        {"fieldname": "points", "label": "Points", "fieldtype": "Float", "width": 100},
        {"fieldname": "reference_document", "label": "Damages and Returns ID", "fieldtype": "Link", "options": "Damages and Returns", "width": 220},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 100},
        {"fieldname": "reset_date", "label": "Reset Date", "fieldtype": "Date", "width": 120}
    ]

def get_data(filters):
    # Setup conditions based on the filter
    query_filters = {}
    if filters and filters.get("employee"):
        query_filters["employee"] = filters.get("employee")
        
    # Fetch all records, newest first
    return frappe.db.get_all(
        "Damage Point Ledger",
        filters=query_filters,
        fields=["incident_date", "points", "reference_document", "status", "reset_date"],
        order_by="incident_date DESC"
    )