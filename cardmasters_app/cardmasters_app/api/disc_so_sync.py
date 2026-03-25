import frappe
from frappe.model.document import Document

def sync_wo_from_so_master(doc, method=None):
    """
    Main entry point for Sales Order 'on_update_after_submit'.
    """
    # --- PASS 1: GLOBAL HEADER SYNC ---
    # Update every linked Work Order with the SO Header info
    all_linked_wos = frappe.get_all("Work Order",
        filters={"sales_order": doc.name, "docstatus": ["<", 2]},
        fields=["name"]
    )
    for wo_info in all_linked_wos:
        update_wo_header_metadata(wo_info.name, doc)

    # --- PASS 2: ITEM-LEVEL SYNC ---
    for item in doc.items:
        work_orders = frappe.get_all("Work Order",
            filters={
                "sales_order": doc.name, 
                "sales_order_item": item.name, 
                "docstatus": ["<", 2]
            },
            fields=["name", "qty", "docstatus"],
            order_by="creation asc" # Oldest to Newest
        )
        
        if not work_orders:
            continue

        # Sync line-item text fields for these specific WOs
        for wo_info in work_orders:
            update_wo_item_specifics(wo_info.name, item)

        # Quantity Logic
        total_wo_qty = sum(wo.qty for wo in work_orders)
        delta = item.qty - total_wo_qty

        if delta == 0:
            continue

        if delta > 0:
            # INCREASE: Add to the newest WO
            update_wo_qty(work_orders[-1].name, work_orders[-1].qty + delta)
        else:
            # DECREASE: Cascade reduction from newest down to oldest
            reduce_wo_cascade_simple(work_orders, abs(delta))

def update_wo_header_metadata(wo_name, so_doc):
    """Pushes Header and Artist Card data."""
    artist_card = frappe.db.get_value("Artist Card", {"sales_order": so_doc.name}, 
                                     ["name", "artist", "bom", "remarks"], as_dict=True)
    header_values = {
        "custom_customer": so_doc.customer,
        "custom_deadline": so_doc.delivery_date,
        "custom_remarks": so_doc.get("custom_remarks") or "No Remarks from Customer",
        "custom_blue_order": so_doc.get("custom_blue_order"),
        "custom_remarks_production": so_doc.get("custom_remarks_production") or "No Remarks for Production",
        "custom_rush_order": so_doc.get("custom_rush_order"),
        "custom_for_branch": so_doc.get("custom_for_branch")
    }
    if artist_card:
        header_values.update({
            "custom_artist_card": artist_card.name,
            "custom_artist_assigned": artist_card.artist,
            "custom_artist_bom": artist_card.bom or "No BOM from Artist",
            "custom_artist_remarks": artist_card.remarks or "No Remarks from Artist"
        })
    frappe.db.set_value("Work Order", wo_name, header_values, update_modified=True)
    frappe.clear_document_cache("Work Order", wo_name)

def update_wo_item_specifics(wo_name, so_item):
    """Pushes Line-Item specific fields."""
    item_values = {
        "custom_item_specifics": so_item.get("custom_item_specifics") or "No Item Specifics",
        "custom_particulars": so_item.get("custom_particulars") or "No Item Particulars",
        "custom_has_advance_withdrawal": so_item.get("custom_has_advance_withdrawal")
    }
    frappe.db.set_value("Work Order", wo_name, item_values, update_modified=True)
    frappe.clear_document_cache("Work Order", wo_name)

def update_wo_qty(wo_name, new_qty):
    """Updates Qty and recalculates BOM."""
    wo = frappe.get_doc("Work Order", wo_name)
    wo.reload() # Prevent 'Document Modified' error
    wo.qty = new_qty
    wo.flags.ignore_validate_update_after_submit = True
    wo.get_items_and_operations_from_bom() 
    wo.save(ignore_permissions=True)
    frappe.msgprint(f"Updated {wo_name} quantity to {new_qty}")

def reduce_wo_cascade_simple(work_orders_asc, amount_to_reduce):
    """Subtracts qty from newest. Relinks SEs with 0 FG Qty if cancelled."""
    remaining = amount_to_reduce
    
    # Iterate backwards (Newest to Oldest)
    for i in range(len(work_orders_asc) - 1, -1, -1):
        if remaining <= 0:
            break
            
        current_wo = work_orders_asc[i]
        
        if current_wo.qty <= remaining:
            remaining -= current_wo.qty
            
            # Find the next WO in line to take the stock entries
            survivor_wo = work_orders_asc[i-1].name if i > 0 else None
            simple_relink_and_cleanup(current_wo.name, survivor_wo)
        else:
            update_wo_qty(current_wo.name, current_wo.qty - remaining)
            remaining = 0

def simple_relink_and_cleanup(source_wo, survivor_wo):
    """Moves SEs, sets FG qty to 0, and cancels the source WO."""
    # 1. Relink and Reset Stock Entries
    ses = frappe.get_all("Stock Entry", filters={"work_order": source_wo, "docstatus": ["<", 2]})
    for se in ses:
        if survivor_wo:
            # Simple Move: Assign to new WO and zero out the 'Produced' flag
            frappe.db.set_value("Stock Entry", se.name, {
                "work_order": survivor_wo,
                "fg_completed_qty": 0
            })
            frappe.msgprint(f"Relinked {se.name} to {survivor_wo} (FG Qty reset to 0)")
        else:
            frappe.msgprint(f"Note: {se.name} left on cancelled WO (No survivor found)")

    # 2. Cancel the Source Work Order
    wo = frappe.get_doc("Work Order", source_wo)
    wo.reload() # Safety first
    
    if wo.docstatus == 1:
        if frappe.db.get_value("Workflow State", "Cancelled"):
            wo.db_set("workflow_state", "Cancelled")
        wo.cancel()
        frappe.msgprint(f"Cancelled redundant Work Order {source_wo}")
    elif wo.docstatus == 0:
        wo.delete()
        frappe.msgprint(f"Deleted redundant Draft Work Order {source_wo}")