import frappe
from frappe.utils import getdate, add_months
import urllib.parse
import json

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "employee_name", "label": "Employee Name", "fieldtype": "Data", "width": 250},
        {"fieldname": "current_month_points", "label": "Current Month Points", "fieldtype": "Float", "width": 170},
        {"fieldname": "consecutive_points", "label": "Consecutive Months Points", "fieldtype": "Float", "width": 210},
        {"fieldname": "consecutive_streak", "label": "Consecutive Months", "fieldtype": "Int", "width": 160},
        {"fieldname": "total_active_points", "label": "Total Active Points", "fieldtype": "Data", "width": 150},
        {"fieldname": "total_damage_value", "label": "Total Active Damage Value", "fieldtype": "Currency", "width": 200},
        {"fieldname": "total_employee_charge", "label": "Total Active Employee Charge", "fieldtype": "Currency", "width": 240},
        {"fieldname": "total_all_points", "label": "All-time Points", "fieldtype": "Float", "width": 120}
    ]

def get_data(filters):
    # 1. ALWAYS fetch all active ledgers to keep employee point/streak math 100% accurate
    ledgers = frappe.db.get_all(
        "Damage Point Ledger",
        filters={
            "status": "Active",
            "docstatus": 1 
        },
        fields=["employee", "points", "incident_date", "reference_document"],
        order_by="incident_date asc"
    )
    
    # 2. Fetch the absolute total points (Active + Inactive) per employee efficiently
    all_points_query = frappe.db.get_all(
        "Damage Point Ledger",
        filters={"docstatus": 1},
        fields=["employee", "sum(points) as total_points"],
        group_by="employee"
    )
    total_points_map = {row.employee: row.total_points for row in all_points_query}

    dnr_names = list(set(row.reference_document for row in ledgers if row.reference_document))
    
    dnr_data = {}
    employee_charges = {}
    
    if dnr_names:
        # Fetch the workstation here so we know which documents belong where
        dnr_records = frappe.db.get_all(
            "Damages and Returns",
            filters={"name": ["in", dnr_names]},
            fields=["name", "value_of_damages", "workstation"]
        )
        dnr_data = {d.name: d for d in dnr_records}

        charge_records = frappe.db.get_all(
            "Damages and Returns Employee Table",
            filters={"parent": ["in", dnr_names], "parenttype": "Damages and Returns"},
            fields=["parent", "employee", "charge"]
        )
        employee_charges = {(d.parent, d.employee): (d.charge or 0.0) for d in charge_records}

    summary = {}
    current_month_str = getdate().strftime("%Y-%m")

    for row in ledgers:
        emp = row.employee
        if emp not in summary:
            summary[emp] = {
                "total_active_points": 0.0, 
                "current_month_points": 0.0, 
                "monthly_totals": {},
                "total_damage_value": 0.0,
                "total_employee_charge": 0.0,
                "seen_dnrs": set(),
                "workstations": set() # Track all workstations this employee has incidents in
            }
        
        summary[emp]["total_active_points"] += row.points
        
        if row.reference_document and row.reference_document not in summary[emp]["seen_dnrs"]:
            doc_info = dnr_data.get(row.reference_document, {})
            
            summary[emp]["total_damage_value"] += doc_info.get("value_of_damages", 0.0)
            summary[emp]["total_employee_charge"] += employee_charges.get((row.reference_document, emp), 0.0)
            
            # Save the workstation to the employee's list of involved workstations
            if doc_info.get("workstation"):
                summary[emp]["workstations"].add(doc_info.get("workstation"))
                
            summary[emp]["seen_dnrs"].add(row.reference_document)
        
        incident_month = row.incident_date.strftime("%Y-%m")
        if incident_month == current_month_str:
            summary[emp]["current_month_points"] += row.points
            
        summary[emp]["monthly_totals"][incident_month] = summary[emp]["monthly_totals"].get(incident_month, 0) + row.points

    data = []
    
    # Check if the user applied a workstation filter
    filter_ws = filters.get("workstation") if filters else None

    for emp, stats in summary.items():
        
        # --- SAFE FILTER LOGIC ---
        if filter_ws and filter_ws not in stats["workstations"]:
            continue

        emp_name = frappe.db.get_value("Employee", emp, "employee_name") or emp
        sorted_months = sorted(stats["monthly_totals"].keys())
        
        streak = 0
        consecutive_pts = 0.0
        
        if sorted_months:
            if current_month_str in sorted_months:
                latest_date = getdate(current_month_str + "-01")
                streak = 1
                consecutive_pts = stats["monthly_totals"][current_month_str]
                
                for i in range(1, len(sorted_months)):
                    prev_expected_date = add_months(latest_date, -i)
                    prev_expected_str = prev_expected_date.strftime("%Y-%m")
                    
                    if prev_expected_str in sorted_months:
                        streak += 1
                        consecutive_pts += stats["monthly_totals"][prev_expected_str]
                    else:
                        break 
            else:
                streak = 0
                consecutive_pts = 0.0

        emp_encoded = urllib.parse.quote(emp)
        emp_link = f"<a href='/app/employee/{emp_encoded}' style='color: var(--text-color); font-weight: 500;'>{emp_name}</a>"
        
        dnr_list = list(stats["seen_dnrs"])
        total_active = stats["total_active_points"]
        absolute_total_points = total_points_map.get(emp, 0.0)
        
        if dnr_list and total_active > 0:
            filter_value = json.dumps(["in", dnr_list])
            encoded_filter = urllib.parse.quote(filter_value)
            
            url = f"/app/damages-and-returns?name={encoded_filter}"
            points_display = f"<a href='{url}' style='color: var(--blue-500); font-weight: bold; text-align: right; display: block;'>{total_active:,.2f}</a>"
        else:
            points_display = f"<span style='text-align: right; display: block;'>{total_active:,.2f}</span>"
        
        data.append({
            "employee_name": emp_link,
            "current_month_points": stats["current_month_points"],
            "consecutive_points": consecutive_pts,
            "consecutive_streak": streak,
            "total_active_points": points_display,
            "total_all_points": absolute_total_points,
            "total_damage_value": stats["total_damage_value"],
            "total_employee_charge": stats["total_employee_charge"]
        })
        
    return data