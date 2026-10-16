import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
         {"fieldname": "reference_document", "label": "Damages and Returns ID", "fieldtype": "Link", "options": "Damages and Returns", "width": 220},
        {"fieldname": "incident_date", "label": "Incident Date", "fieldtype": "Date", "width": 120},
        {"fieldname": "workstation", "label": "Workstation Incurred", "fieldtype": "Data", "width": 150},
        {"fieldname": "department", "label": "Department Incurred", "fieldtype": "Data", "width": 150},
        {"fieldname": "workstation_detected", "label": "Workstation Detected", "fieldtype": "Data", "width": 150},
        {"fieldname": "department_detected", "label": "Department Detected", "fieldtype": "Data", "width": 150},
        {"fieldname": "value_of_damages", "label": "Total Value of Damages", "fieldtype": "Currency", "width": 150},
        {"fieldname": "charge", "label": "Charge", "fieldtype": "Currency", "width": 120},
        {"fieldname": "points", "label": "Points", "fieldtype": "Float", "width": 100},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 100},
        {"fieldname": "reset_date", "label": "Reset Date", "fieldtype": "Date", "width": 120}
    ]

def get_data(filters):
    # Set docstatus to 1 to exclusively fetch submitted ledgers.
    query_filters = {"docstatus": 1}
    
    if filters and filters.get("employee"):
        query_filters["employee"] = filters.get("employee")
        
    # 1. Fetch ledgers
    ledgers = frappe.db.get_all(
        "Damage Point Ledger",
        filters=query_filters,
        fields=["employee", "incident_date", "points", "reference_document", "status", "reset_date"],
        order_by="incident_date DESC"
    )
    
    if not ledgers:
        return []
        
    dnr_names = list(set(row.reference_document for row in ledgers if row.reference_document))
    
    dnr_data = {}
    employee_charges = {}
    
    if dnr_names:
        # 2. Fetch the parent Damages and Returns fields
        dnr_records = frappe.db.get_all(
            "Damages and Returns",
            filters={"name": ["in", dnr_names]},
            fields=["name", "workstation", "department", "workstation_detected", "department_detected", "value_of_damages"]
        )
        dnr_data = {d.name: d for d in dnr_records}
        
        # 3. Fetch the specific charge for the employee from the child table
        charge_records = frappe.db.get_all(
            "Damages and Returns Employee Table",
            filters={"parent": ["in", dnr_names], "parenttype": "Damages and Returns"},
            fields=["parent", "employee", "charge"]
        )
        employee_charges = {(d.parent, d.employee): (d.charge or 0.0) for d in charge_records}

    # 4. Map the fetched data to the rows
    data = []
    for row in ledgers:
        doc_info = dnr_data.get(row.reference_document, {})
        emp_charge = employee_charges.get((row.reference_document, row.employee), 0.0)
        
        data.append({
            "incident_date": row.incident_date,
            "reference_document": row.reference_document,
            "workstation": doc_info.get("workstation"),
            "department": doc_info.get("department"),
            "workstation_detected": doc_info.get("workstation_detected"),
            "department_detected": doc_info.get("department_detected"),
            "value_of_damages": doc_info.get("value_of_damages", 0.0),
            "charge": emp_charge,
            "points": row.points,
            "status": row.status,
            "reset_date": row.reset_date
        })
        
    return data