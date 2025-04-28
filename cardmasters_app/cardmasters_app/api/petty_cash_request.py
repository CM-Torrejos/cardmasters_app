import frappe
from frappe.model.workflow import apply_workflow
from frappe import _

@frappe.whitelist()
def cancel_request(docname):
    # find any submitted Purchase Invoices linked to this request
    invoices = frappe.get_all(
        "Purchase Invoice",
        filters={
            "petty_cash_request": docname,
            "docstatus": 1
        },
        pluck="name"
    )
    if invoices:
        frappe.throw(
            _("Cannot cancel Petty Cash Request because Purchase Invoice {0} is already submitted. "
              "Please cancel those invoices first.")
        .format(", ").join(invoices)
        )
    # safe to transition
    doc = frappe.get_doc("Petty Cash Request", docname)
    apply_workflow(doc.as_dict(), "Cancel")
    frappe.db.commit()
    return True

