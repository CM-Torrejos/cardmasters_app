import frappe


def execute():
	fieldname = "Delivery Note Item-custom_return_processing_status"
	if frappe.db.exists("Custom Field", fieldname):
		frappe.db.set_value(
			"Custom Field",
			fieldname,
			"options",
			"Pending\nConverted to RM\nIssued as Damage\nConverted to RM and Issued as Damage",
		)
		frappe.clear_cache(doctype="Delivery Note Item")
