import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Delivery Note": [
				{
					"fieldname": "custom_damages_and_returns",
					"label": "Damages and Returns",
					"fieldtype": "Link",
					"options": "Damages and Returns",
					"insert_after": "is_return",
					"mandatory_depends_on": "eval:doc.is_return",
				},
			],
		},
		update=True,
	)

	fieldname = "Delivery Note-custom_return_processing_status"
	if frappe.db.exists("Custom Field", fieldname):
		frappe.db.set_value("Custom Field", fieldname, "insert_after", "custom_damages_and_returns")

	frappe.clear_cache(doctype="Delivery Note")
