frappe.query_reports["HR Damage Point Summary"] = {
    "filters": [
        {
            "fieldname": "workstation",
            "label": __("Workstation Incurred"),
            "fieldtype": "Link",
            "options": "Workstation", 
            "reqd": 0
        }
    ]
};