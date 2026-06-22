import frappe

@frappe.whitelist()
def update_work_order_details(docname, qty, item_specifics=None, particulars=None, operations=None):
    from cardmasters_app.cardmasters_app.services.work_order import update_work_order_details as update_details
    return update_details(docname, qty, item_specifics, particulars, operations)

@frappe.whitelist()
def get_current_employee_workstations():
    from cardmasters_app.cardmasters_app.services.work_order import get_current_employee_workstations as get_workstations
    return get_workstations()

@frappe.whitelist()
def get_workstation_completion_options(docname, action=None):
    from cardmasters_app.cardmasters_app.services.work_order import get_workstation_completion_options as get_options
    return get_options(docname, action)

@frappe.whitelist()
def mark_workstation_jobs_complete(docname, workstation):
    from cardmasters_app.cardmasters_app.services.work_order import mark_workstation_jobs_complete as mark_complete
    return mark_complete(docname, workstation)

@frappe.whitelist()
def undo_workstation_jobs_complete(docname, workstation):
    from cardmasters_app.cardmasters_app.services.work_order import undo_workstation_jobs_complete as undo_complete
    return undo_complete(docname, workstation)
