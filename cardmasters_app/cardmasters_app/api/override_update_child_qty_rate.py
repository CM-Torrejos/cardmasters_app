import frappe
import json
# Import the standard core function
from erpnext.controllers.accounts_controller import update_child_qty_rate 

@frappe.whitelist()
def update_custom_child_fields(parent_doctype, trans_items, parent_doctype_name, child_docname="items", new_project_name=None):
    # BULLETPROOFING: Frappe sometimes parses arrays automatically from the frontend.
    # The standard core function strictly expects a string. We ensure both forms exist.
    if isinstance(trans_items, list):
        data = trans_items
        trans_items_str = json.dumps(trans_items)
    else:
        data = json.loads(trans_items)
        trans_items_str = trans_items

    # STEP 1: Let standard ERPNext handle all Qty, Rate, Stock, and GL logic safely
    # (Pass the stringified version)
    update_child_qty_rate(parent_doctype, trans_items_str, parent_doctype_name, child_docname)

    # STEP 2: Setup table name
    child_table = f"{parent_doctype} Item"

    # STEP 3: Save ONLY our custom fields directly to the database
    for row in data:
        if row.get("docname"):
            frappe.db.set_value(
                child_table,
                row.get("docname"),
                {
                    "custom_item_specifics": row.get("custom_item_specifics"),
                    "custom_particulars": row.get("custom_particulars")
                },
                update_modified=False # Prevents unnecessary validation loops
            )
            
    # STEP 4: Forcefully bypass submission locks to link the newly created project
    if new_project_name and parent_doctype == "Sales Order":
        frappe.db.sql("""
            UPDATE `tabSales Order` 
            SET project = %s 
            WHERE name = %s
        """, (new_project_name, parent_doctype_name), auto_commit=1)
    
    # STEP 5: Update the parent document's timestamp so the UI knows it was refreshed
    frappe.db.set_value(parent_doctype, parent_doctype_name, "modified", frappe.utils.now())