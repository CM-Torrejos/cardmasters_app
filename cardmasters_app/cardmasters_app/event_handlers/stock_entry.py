# this is to strictly update stock entry on item manufacture
import frappe
from frappe.utils import flt
from frappe import _

def inherit_item_details_on_insert(doc, _method):
	# Only for Transfer for Manufacture with batching
	if doc.purpose != "Material Transfer for Manufacture" or not doc.custom_batched:
		return
	if not doc.work_order:
		return

	# Fetch Work Order and map item to its custom details
	wo = frappe.get_doc("Work Order", doc.work_order)
	details_map = {
		r.item_code: (r.get("custom_item_details") or "").strip()
		for r in wo.required_items
	}

	for d in doc.items:
		detail = details_map.get(d.item_code)
		if detail:
			d.custom_item_details = detail

def get_wip_warehouse_name():
	try:
		wip_warehouse = frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")

		if wip_warehouse:
			return wip_warehouse
		
		else:
			frappe.log_error("No Warehouse found.")
			return None
			
	except Exception as e:
		frappe.log_error(f"Error querying Warehouse DocType: {e}")
		return None

def validate_manufacture_source_warehouse(doc, _method):
	"""
	Shows a warning if any item's source warehouse
	is not 'Work In Progress - CM CDO'.
	"""
	
	warehouse = get_wip_warehouse_name()

	if doc.stock_entry_type != "Manufacture":
		return

	for item in doc.items:
		
		if item.s_warehouse != warehouse:
			if not item.s_warehouse:
				continue

			frappe.msgprint(
				"The items' source warehouses are not Work In Progress (WIP) locations.",
				title="Warehouse Warning",
				indicator="orange"
			)
			
			break

EXPENSE_ACCOUNT = "1504 - STOCK CONSUMPTION FOR FG - CM CDO"
TARGET_WAREHOUSE = "MAIN - CLAIMING - CM CDO"

def before_save_stock_entry(doc, _method=None):
	"""
	Rules:
	1) If Stock Entry type/purpose is 'Material Transfer for Consumption' OR 'Manufacture':
	   - set expense_account on each row in items to EXPENSE_ACCOUNT
	2) If type/purpose is 'Manufacture':
	   - for any row with t_warehouse == TARGET_WAREHOUSE, set allow_zero_valuation_rate = 1
	   - warn if a finished item target warehouse is not marked as a finished goods warehouse
	"""

	# ERPNext commonly uses "purpose". Some setups may use/alias "stock_entry_type".
	entry_type = (getattr(doc, "stock_entry_type", None) or getattr(doc, "purpose", None) or "").strip()

	if entry_type == "Manufacture":
		_warn_if_finished_goods_target_is_not_flagged(doc)
		for row in (doc.items or []):
			# Only for target warehouse lines where basic_rate is 0
			if getattr(row, "t_warehouse", None) == TARGET_WAREHOUSE and flt(row.basic_rate) == 0:
				if hasattr(row, "allow_zero_valuation_rate"):
					row.allow_zero_valuation_rate = 1


def _warn_if_finished_goods_target_is_not_flagged(doc):
	warehouses = {
		row.t_warehouse
		for row in (doc.items or [])
		if getattr(row, "is_finished_item", 0) and getattr(row, "t_warehouse", None)
	}
	if not warehouses:
		return

	unflagged = []
	for warehouse in sorted(warehouses):
		if not frappe.db.get_value("Warehouse", warehouse, "custom_is_finished_goods_warehouse"):
			unflagged.append(warehouse)

	if not unflagged:
		return

	frappe.msgprint(
		_(
			"The finished item target warehouse is not marked as a Finished Goods Warehouse: {0}"
		).format(", ".join(frappe.bold(warehouse) for warehouse in unflagged)),
		title=_("Finished Goods Warehouse Warning"),
		indicator="orange",
	)


# def after_insert_stock_entry(doc, method=None):
# 	entry_type = (getattr(doc, "stock_entry_type", None) or getattr(doc, "purpose", None) or "").strip()
# 	if entry_type == "Manufacture":
# 		for row in reversed(doc.items or []):
# 		# --- EXTENSION: Delete row if Target Warehouse is empty ---
# 			if not row.t_warehouse:
# 				doc.remove(row)
# 				continue
