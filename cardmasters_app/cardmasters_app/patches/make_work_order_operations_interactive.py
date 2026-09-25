"""Run Work Order Operations immediately instead of queuing prepared reports."""

import frappe


def execute():
    if frappe.db.exists("Report", "Work Order Operations"):
        frappe.db.set_value("Report", "Work Order Operations", {
            "prepared_report": 0,
            "disable_prepared_report_automation": 1,
        })
        frappe.clear_document_cache("Report", "Work Order Operations")
