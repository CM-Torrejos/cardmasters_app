import frappe
from frappe.utils import getdate, add_months

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "employee", "label": "Employee ID", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": "Employee Name", "fieldtype": "Data", "width": 180},
        {"fieldname": "current_month_points", "label": "Current Month Points", "fieldtype": "Float", "width": 160},
        {"fieldname": "consecutive_points", "label": "Consecutive Months Points", "fieldtype": "Float", "width": 200},
        {"fieldname": "consecutive_streak", "label": "Consecutive Months", "fieldtype": "Int", "width": 160},
        {"fieldname": "total_active_points", "label": "Total Active Points", "fieldtype": "Float", "width": 160}
    ]

def get_data(filters):
    ledgers = frappe.db.get_all(
        "Damage Point Ledger",
        filters={"status": "Active"},
        fields=["employee", "points", "incident_date"],
        order_by="incident_date asc"
    )
    
    summary = {}
    current_month_str = getdate().strftime("%Y-%m")

    for row in ledgers:
        emp = row.employee
        if emp not in summary:
            summary[emp] = {
                "total_points": 0.0, 
                "current_month_points": 0.0, 
                "monthly_totals": {} 
            }
        
        summary[emp]["total_points"] += row.points
        
        incident_month = row.incident_date.strftime("%Y-%m")
        if incident_month == current_month_str:
            summary[emp]["current_month_points"] += row.points
            
        summary[emp]["monthly_totals"][incident_month] = summary[emp]["monthly_totals"].get(incident_month, 0) + row.points

    data = []
    for emp, stats in summary.items():
        emp_name = frappe.db.get_value("Employee", emp, "employee_name")
        sorted_months = sorted(stats["monthly_totals"].keys())
        
        streak = 0
        consecutive_pts = 0.0
        
        if sorted_months:
            # STRICT CHECK: Does the employee have points in the CURRENT calendar month?
            if current_month_str in sorted_months:
                # Streak is active. Count backward from the current month.
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
                # Employee has 0 points in the current month. 
                # According to Zero-Damage Reset Rule, consecutive streak drops to 0.
                streak = 0
                consecutive_pts = 0.0
        
        data.append({
            "employee": emp,
            "employee_name": emp_name,
            "current_month_points": stats["current_month_points"],
            "consecutive_points": consecutive_pts,
            "consecutive_streak": streak,
            "total_active_points": stats["total_points"]
        })
        
    return data