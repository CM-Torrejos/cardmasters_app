# this is to strictly update stock entry on item manufacture
import frappe
from frappe import _


def inherit_item_details_on_insert(doc, method):
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

def get_wip_stock_entry_type():  
    try:
        wip_type_name = frappe.db.get_value(
            "Stock Entry Type", 
            {"custom_is_wip": 1}, 
            "name"
        )

        if wip_type_name:
            return wip_type_name
        
        else:
            frappe.log_error("No Stock Entry Type found with 'custom_is_wip' checked.")
            return None

    except Exception as e:
        frappe.log_error(f"Error querying Stock Entry Type: {e}")
        return None

def get_wip_warehouse_name():
    try:
        wip_warehouse = frappe.db.get_value(
            "Warehouse", 
            {"custom_is_wip": 1}, 
            "name"
        )

        if wip_warehouse:
            return wip_warehouse
        
        else:
            frappe.log_error("No Warehouse found with 'custom_is_wip' checked.")
            return None
            
    except Exception as e:
        frappe.log_error(f"Error querying Warehouse DocType: {e}")
        return None

def validate_manufacture_source_warehouse(doc, method):
    """
	Shows a warning if any item's source warehouse
	is not 'Work In Progress - CM CDO'.
	"""
    
    manufacture = get_wip_stock_entry_type()
    warehouse = get_wip_warehouse_name()

    frappe.log_error("manufacture", manufacture)
    frappe.log_error("warehouse", warehouse)

    if doc.stock_entry_type != manufacture:
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