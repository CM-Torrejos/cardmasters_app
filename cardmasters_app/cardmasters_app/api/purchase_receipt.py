import frappe
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt

from cardmasters_app.cardmasters_app.services.batch_handler import resolve_sales_order_batch


@frappe.whitelist()
def make_purchase_receipt_from_sales_order(source_name, target_doc=None, args=None):
	if isinstance(args, str):
		args = frappe.parse_json(args)

	filtered_children = set((args or {}).get("filtered_children") or [])

	def set_missing_values(source, target):
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	def update_item(source, target, source_parent):
		target.qty = flt(source.qty) - flt(source.delivered_qty)
		target.stock_qty = flt(target.qty) * flt(source.conversion_factor or 1)
		target.sales_order = source_parent.name
		target.sales_order_item = source.name

		if source.item_code and frappe.get_cached_value("Item", source.item_code, "has_batch_no"):
			item_specifics = (source.get("custom_item_specifics") or "").strip() or None
			found_batch = resolve_sales_order_batch(
				so_name=source_parent.name,
				so_detail=source.name,
				item_code=source.item_code,
				item_specifics=item_specifics,
			)
			if found_batch:
				target.batch_no = found_batch
				target.use_serial_batch_fields = 1

	def item_condition(doc):
		if filtered_children and doc.name not in filtered_children:
			return False
		return flt(doc.qty) > flt(doc.delivered_qty)

	return get_mapped_doc(
		"Sales Order",
		source_name,
		{
			"Sales Order": {
				"doctype": "Purchase Receipt",
				"validation": {
					"docstatus": ["=", 1],
				},
				"field_no_map": [
					"naming_series",
					"taxes_and_charges",
					"tc_name",
					"terms",
					"currency",
					"conversion_rate",
					"price_list_currency",
					"plc_conversion_rate",
					"set_warehouse",
					"contact_person",
					"contact_display",
					"contact_email",
					"contact_mobile",
					"shipping_address",
					"shipping_address_display",
					"additional_discount_percentage",
					"discount_amount",
					"base_discount_amount",
				],
			},
			"Sales Order Item": {
				"doctype": "Purchase Receipt Item",
				"field_map": {
					"name": "sales_order_item",
					"parent": "sales_order",
					"uom": "uom",
					"stock_uom": "stock_uom",
					"conversion_factor": "conversion_factor",
				},
				"field_no_map": [
					"rate",
					"base_rate",
					"amount",
					"base_amount",
					"net_rate",
					"net_amount",
					"pricing_rules",
				],
				"postprocess": update_item,
				"condition": item_condition,
			},
		},
		target_doc,
		set_missing_values,
	)