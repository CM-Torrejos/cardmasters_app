"""Keep the batched Production Tower report out of the prepared-report queue."""

import frappe


def execute():
    if frappe.db.exists("Report", "Production Tower"):
        frappe.db.set_value("Report", "Production Tower", {
            "prepared_report": 0,
            "disable_prepared_report_automation": 1,
        })
        frappe.clear_document_cache("Report", "Production Tower")
