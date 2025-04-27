import frappe
from frappe.model.workflow import apply_workflow

@frappe.whitelist()
def cancel_request(docname):
    # load the document
    doc = frappe.get_doc("Petty Cash Request", docname)
    # invoke the workflow action whose 'next_state' is "Cancelled"
    # typically your Transition’s Action label is "Cancel"
    apply_workflow(doc.as_dict(), "Cancel")
    # commit so the docstatus change (if any) is persisted
    frappe.db.commit()
    return True
