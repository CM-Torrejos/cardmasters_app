import frappe


def execute():
	field_name = "Work Order-custom_cm_jobs"

	if frappe.db.exists("Custom Field", field_name):
		frappe.db.set_value("Custom Field", field_name, "hidden", 1)

	frappe.clear_cache(doctype="Work Order")
