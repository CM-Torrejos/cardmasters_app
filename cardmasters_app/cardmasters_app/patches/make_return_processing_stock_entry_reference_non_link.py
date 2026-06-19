import frappe


def execute():
	fieldname = "Stock Entry-custom_return_delivery_note"
	if frappe.db.exists("Custom Field", fieldname):
		frappe.db.set_value(
			"Custom Field",
			fieldname,
			{
				"fieldtype": "Data",
				"options": None,
			},
		)

	frappe.clear_cache(doctype="Stock Entry")
