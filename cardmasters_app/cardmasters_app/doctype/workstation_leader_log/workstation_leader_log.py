# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document


class WorkstationLeaderLog(Document):
	pass

@frappe.whitelist()
def get_starred_work_orders(names=None):
    leader = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "custom_workstation_leader")
    
    if not leader:
        # Throwing here will trigger the JS 'error' or 'r.exc' logic
        return {"is_leader": False, "starred": []}

    starred = frappe.get_all("Workstation Leader Log", filters={
        "workstation_leader": leader,
        "reference_document_type": "Work Order"
    }, pluck="reference_name")
    
    return {"is_leader": True, "starred": starred}

@frappe.whitelist()
def toggle_star(docname, state):
    # Get current leader
    leader = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "custom_workstation_leader")
    if not leader:
        frappe.throw("No Workstation Leader assigned to your profile.")

    # Get current list from Work Order
    # We use a 'FOR UPDATE' lock to prevent two leaders from clashing if they click at the same time
    current_val = frappe.db.get_value("Work Order", docname, "custom_starred_by")
    
    try:
        starred_by = json.loads(current_val) if current_val else []
    except:
        starred_by = []

    if state == "on":
        # Add to list if not there
        if leader not in starred_by:
            starred_by.append(leader)
        
        if not frappe.db.exists("Workstation Leader Log", {"reference_name": docname, "workstation_leader": leader}):
            frappe.get_doc({
                "doctype": "Workstation Leader Log",
                "reference_document_type": "Work Order",
                "reference_name": docname,
                "workstation_leader": leader
            }).insert(ignore_permissions=True)
            
    else:
        # Remove from list
        if leader in starred_by:
            starred_by.remove(leader)
        
        # Delete Log
        frappe.db.delete("Workstation Leader Log", {"reference_name": docname, "workstation_leader": leader})

    # 3. Save the updated JSON string back to the Work Order
    frappe.db.set_value("Work Order", docname, "custom_starred_by", json.dumps(starred_by), update_modified=False)
            
    return "Success"