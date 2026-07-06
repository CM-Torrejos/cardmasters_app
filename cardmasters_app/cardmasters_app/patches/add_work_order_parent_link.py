import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Work Order": [
				{
					"fieldname": "custom_parent_work_order",
					"label": "Parent Work Order",
					"fieldtype": "Link",
					"options": "Work Order",
					"insert_after": "sales_order",
					"description": "Make-to-order Work Order that created this make-to-stock Work Order.",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"depends_on": "eval:doc.custom_parent_work_order",
				},
			],
		},
		update=True,
	)

	frappe.clear_cache(doctype="Work Order")
