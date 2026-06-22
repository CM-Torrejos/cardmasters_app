import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Work Order Operation": [
				{
					"fieldname": "custom_workstation_hidden",
					"label": "Workstation Hidden",
					"fieldtype": "Check",
					"insert_after": "workstation",
					"default": "0",
					"hidden": 1,
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
				},
			],
		},
		update=True,
	)

	frappe.clear_cache(doctype="Work Order Operation")
