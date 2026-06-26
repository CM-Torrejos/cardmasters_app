import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	custom_fields = {
		"Warehouse": [
			{
				"fieldname": "custom_accepts_returns",
				"label": "Accepts Returns",
				"fieldtype": "Check",
				"default": "0",
				"insert_after": "disabled",
				"description": "Allow this warehouse as a destination for Sales Return returned items.",
			},
			{
				"fieldname": "custom_is_finished_goods_warehouse",
				"label": "Is Finished Goods Warehouse",
				"fieldtype": "Check",
				"default": "0",
				"insert_after": "custom_accepts_returns",
				"description": "Mark this warehouse as a valid finished goods destination for operations.",
			},
		],
		"Delivery Note": [
			{
				"fieldname": "custom_return_warehouse",
				"label": "Returned Item Destination Warehouse",
				"fieldtype": "Link",
				"options": "Warehouse",
				"insert_after": "custom_damages_and_returns",
				"mandatory_depends_on": "eval:doc.is_return",
				"read_only_depends_on": "eval:doc.docstatus > 0",
			},
		],
	}

	create_custom_fields(custom_fields, update=True)
	frappe.clear_cache(doctype="Warehouse")
	frappe.clear_cache(doctype="Delivery Note")
