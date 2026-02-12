# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
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
    leader = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "custom_workstation_leader")
    if not leader:
        frappe.throw("No Workstation Leader assigned to your Employee profile.")

    if state == "on":
        # Create Log
        doc = frappe.get_doc({
            "doctype": "Workstation Leader Log",
            "reference_document_type": "Work Order",
            "reference_name": docname,
            "workstation_leader": leader
        })
        doc.insert(ignore_permissions=True)
    else:
        # Delete Log
        frappe.db.delete("Workstation Leader Log", {
            "reference_name": docname,
            "workstation_leader": leader
        })
    return "Success"