import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	custom_fields = {
		"Delivery Note": [
			{
				"fieldname": "custom_return_processing_status",
				"label": "Return Processing Status",
				"fieldtype": "Select",
				"options": "Not Applicable\nPending\nPartially Processed\nProcessed",
				"default": "Not Applicable",
				"insert_after": "custom_reference_no",
				"read_only": 1,
				"allow_on_submit": 1,
			},
		],
		"Delivery Note Item": [
			{
				"fieldname": "custom_return_processing_status",
				"label": "Return Processing Status",
				"fieldtype": "Select",
				"options": "Pending\nConverted to RM\nIssued as Damage",
				"default": "Pending",
				"insert_after": "custom_item_specifics",
				"read_only": 1,
				"allow_on_submit": 1,
			},
			{
				"fieldname": "custom_return_processing_stock_entry",
				"label": "Return Processing Stock Entry",
				"fieldtype": "Data",
				"insert_after": "custom_return_processing_status",
				"read_only": 1,
				"allow_on_submit": 1,
			},
			{
				"fieldname": "custom_return_processed_by",
				"label": "Return Processed By",
				"fieldtype": "Link",
				"options": "User",
				"insert_after": "custom_return_processing_stock_entry",
				"read_only": 1,
				"allow_on_submit": 1,
			},
			{
				"fieldname": "custom_return_processed_on",
				"label": "Return Processed On",
				"fieldtype": "Datetime",
				"insert_after": "custom_return_processed_by",
				"read_only": 1,
				"allow_on_submit": 1,
			},
			{
				"fieldname": "custom_return_processing_remarks",
				"label": "Return Processing Remarks",
				"fieldtype": "Small Text",
				"insert_after": "custom_return_processed_on",
				"allow_on_submit": 1,
			},
			{
				"fieldname": "custom_target_items_json",
				"label": "Return Processing Target Items JSON",
				"fieldtype": "Code",
				"options": "JSON",
				"insert_after": "custom_return_processing_remarks",
				"read_only": 1,
				"allow_on_submit": 1,
			},
		],
		"Stock Entry": [
			{
				"fieldname": "custom_return_delivery_note",
				"label": "Return Delivery Note",
				"fieldtype": "Data",
				"insert_after": "custom_damages_and_returns",
				"read_only": 1,
				"allow_on_submit": 1,
			},
			{
				"fieldname": "custom_return_delivery_note_item",
				"label": "Return Delivery Note Item Row",
				"fieldtype": "Data",
				"insert_after": "custom_return_delivery_note",
				"read_only": 1,
				"allow_on_submit": 1,
			},
		],
	}

	create_custom_fields(custom_fields, update=True)
	frappe.clear_cache(doctype="Delivery Note")
	frappe.clear_cache(doctype="Delivery Note Item")
	frappe.clear_cache(doctype="Stock Entry")
