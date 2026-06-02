import frappe

@frappe.whitelist()
def update_work_order_details(docname, qty, item_specifics=None, particulars=None):
    from cardmasters_app.cardmasters_app.services.work_order import update_work_order_details as update_details
    return update_details(docname, qty, item_specifics, particulars)
