import frappe


def execute():
	fieldname = "Delivery Note Item-custom_return_processing_stock_entry"
	if frappe.db.exists("Custom Field", fieldname):
		frappe.db.set_value(
			"Custom Field",
			fieldname,
			{
				"fieldtype": "Data",
				"options": None,
			},
		)

	frappe.clear_cache(doctype="Delivery Note")
	frappe.clear_cache(doctype="Delivery Note Item")
