import frappe
from frappe.model.mapper import get_mapped_doc
import json

@frappe.whitelist()
def make_quotation_from_so(source_name):
    # Create the Quotation using the mapper
    target_doc = get_mapped_doc("Sales Order", source_name, {
        "Sales Order": {
            "doctype": "Quotation",
            "field_map": {
                "customer": "party_name",
                "customer_name": "customer_name",
                "name": "custom_sales_order_ref"
            }
        },
        "Sales Order Item": {
            "doctype": "Quotation Item",
        }
    })

    # Set mandatory Quotation fields
    target_doc.quotation_to = "Customer"
    
    return target_doc

def link_so_to_qtn(doc, method=None):
    """
    Runs on Quotation Save. 
    Takes the ID from the Quotation's 'custom_so_link' 
    and writes the Quotation ID back to the Sales Order.
    """
    so_id = doc.get("custom_sales_order_ref")
    if so_id:
        # Update the Sales Order's link field
        frappe.db.set_value("Sales Order", so_id, "custom_quotation_ref", doc.name)

@frappe.whitelist()
def check_wo_discrepancy(so_name, items):
    if not so_name:
        return None
        
    # Parse the incoming JSON items from the frontend
    current_items = json.loads(items)
    current_items_map = {item.get("name"): item for item in current_items if item.get("name")}
    
    # Fetch the original items from the database BEFORE the save commits
    old_items = frappe.get_all(
        "Sales Order Item", 
        filters={"parent": so_name}, 
        fields=["name", "item_code", "custom_item_specifics", "custom_particulars"]
    )
    
    discrepancy_messages = []
    
    for old_item in old_items:
        current_item = current_items_map.get(old_item.name)
        if not current_item:
            continue
            
        # Safely get old and new values, defaulting to empty strings if None
        old_specifics = old_item.custom_item_specifics or ""
        new_specifics = current_item.get("custom_item_specifics") or ""
        
        old_particulars = old_item.custom_particulars or ""
        new_particulars = current_item.get("custom_particulars") or ""
        
        # Check if either field was modified
        if old_specifics != new_specifics or old_particulars != new_particulars:
            
            # Look for linked Work Orders that are not cancelled
            work_orders = frappe.get_all(
                "Work Order", 
                filters={
                    "sales_order": so_name, 
                    "sales_order_item": old_item.name, 
                    "docstatus": ["<", 2] 
                },
                fields=["name"]
            )
            
            # Format the string for each Work Order found
            for wo in work_orders:
                msg = f"<b>{wo.name}</b> - {old_item.item_code}<br>"
                if old_specifics != new_specifics:
                    msg += f"Item specifics: {old_specifics} &rarr; {new_specifics}<br>"
                if old_particulars != new_particulars:
                    msg += f"Particulars: {old_particulars} &rarr; {new_particulars}<br>"
                    
                discrepancy_messages.append(msg)
                
    # If we found discrepancies, build the final HTML message
    if discrepancy_messages:
        header = "The following changes will cause a discrepancy in the linked work orders.<br><br>Please immediately contact the work order authors to update the details of the work orders as below:<br><br>"
        body = "<br>".join(discrepancy_messages)
        footer = "<br><br>If discrepancies are found by the time of consumption, damages will be charged to the sales order owner. Proceed?"
        return header + body + footer
        
    return None

@frappe.whitelist()
def update_custom_child_fields(parent_doctype, trans_items, parent_doctype_name, child_docname="items", new_project_name=None):
    from erpnext.controllers.accounts_controller import update_child_qty_rate 
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