import frappe


def execute():
	for fieldname in ("holding_document", "replacement_document", "processing_document"):
		frappe.db.set_value(
			"DocField",
			{
				"parent": "Damages and Returns Item Table",
				"fieldname": fieldname,
			},
			{
				"fieldtype": "Data",
				"options": None,
			},
		)

	frappe.clear_cache(doctype="Damages and Returns Item Table")
