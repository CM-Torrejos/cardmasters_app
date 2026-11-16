"""Keep Sales Order workflows manual when automation is switched off."""

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_workflow_name

from cardmasters_app.cardmasters_app.doctype.cardmasters_settings.cardmasters_settings import (
    sales_order_workflow_automation_disabled,
)


def protect_sales_order_workflow(doc, method=None):
    if not sales_order_workflow_automation_disabled() or doc.is_new():
        return

    previous = doc.get_doc_before_save()
    workflow_name = get_workflow_name("Sales Order")
    if not previous or not workflow_name:
        return

    state_field = frappe.get_cached_doc("Workflow", workflow_name).workflow_state_field
    if previous.get(state_field) == doc.get(state_field):
        return
    if frappe.flags.get("manual_sales_order_workflow") == doc.name:
        return

    frappe.throw(_(
        "Automatic Sales Order workflow transitions are disabled in Cardmasters Settings. "
        "Use the Actions menu to change this Sales Order's workflow state."
    ))


@frappe.whitelist()
def apply_manual_workflow(doc, action):
    """Allow the standard Actions endpoint; retain Frappe's workflow checks."""
    data = frappe.parse_json(doc) if isinstance(doc, str) else doc
    if data.get("doctype") != "Sales Order":
        return apply_workflow(doc, action)

    previous = frappe.flags.get("manual_sales_order_workflow")
    frappe.flags.manual_sales_order_workflow = data.get("name")
    try:
        return apply_workflow(doc, action)
    finally:
        frappe.flags.manual_sales_order_workflow = previous
