import frappe
from frappe.model.document import Document

def sync_wo_with_so(doc, method=None):
    """
    Triggered when Sales Order is saved. 
    Syncs SO Item Qty with linked Work Orders.
    """
    for item in doc.items:
        # 1. Get all active/submitted Work Orders for this specific SO Item
        work_orders = frappe.get_all("Work Order",
            filters={
                "sales_order": doc.name,
                "sales_order_item": item.name,
                "docstatus": ["<", 2] # Skip cancelled
            },
            fields=["name", "qty", "docstatus"],
            order_by="creation desc" # Newest first
        )

        if not work_orders:
            continue

        total_wo_qty = sum(wo.qty for wo in work_orders)
        delta = item.qty - total_wo_qty

        if delta == 0:
            continue

        if delta > 0:
            # INCREASE: Add the entire delta to the newest WO
            update_wo_qty(work_orders[0].name, work_orders[0].qty + delta)
        
        else:
            # DECREASE: Reduce from newest, cascading if necessary
            reduce_wo_cascade(work_orders, abs(delta))

def update_wo_qty(wo_name, new_qty):
    """Updates WO quantity, bypassing standard submit restrictions if needed."""
    wo = frappe.get_doc("Work Order", wo_name)
    # Using db_set to bypass some validation, but keep flags for integrity
    wo.qty = new_qty
    wo.flags.ignore_validate_update_after_submit = True
    # Re-calculate required items based on new qty
    wo.get_items_and_operations_from_bom() 
    wo.save(ignore_permissions=True)
    frappe.msgprint(f"Updated {wo_name} quantity to {new_qty}")

def reduce_wo_cascade(work_orders, amount_to_reduce):
    """Cascades quantity reduction across multiple WOs starting from newest."""
    remaining_reduction = amount_to_reduce

    for wo_info in work_orders:
        if remaining_reduction <= 0:
            break

        current_wo_qty = wo_info.qty

        if current_wo_qty <= remaining_reduction:
            # This WO needs to be cancelled/deleted entirely
            remaining_reduction -= current_wo_qty
            cancel_and_cleanup_wo(wo_info.name)
        else:
            # This WO can absorb the rest of the reduction
            new_qty = current_wo_qty - remaining_reduction
            update_wo_qty(wo_info.name, new_qty)
            remaining_reduction = 0

def cancel_and_cleanup_wo(wo_name):
    """Cancels Stock Entries, resets Workflow, and cancels the Work Order."""
    wo = frappe.get_doc("Work Order", wo_name)
    
    # 1. Handle Stock Entries
    stock_entries = frappe.get_all("Stock Entry", 
        filters={"work_order": wo_name, "docstatus": 1})
    
    for se in stock_entries:
        se_doc = frappe.get_doc("Stock Entry", se.name)
        se_doc.cancel()
        frappe.msgprint(f"Cancelled Stock Entry {se.name}")

    # 2. Update Workflow State & Cancel
    if wo.docstatus == 1:
        # Manually set the workflow state to 'Cancelled' 
        # (Change 'Cancelled' to match the exact name in your Workflow setup)
        if frappe.db.get_value("Workflow State", "Cancelled"):
            wo.workflow_state = "Cancelled"
        
        # We use db_set if the WO is already submitted to bypass standard edit restrictions
        wo.db_set("workflow_state", "Cancelled")
        
        wo.cancel()
        frappe.msgprint(f"Cancelled Work Order {wo_name} and set state to Cancelled")
        
    elif wo.docstatus == 0:
        wo.delete()
        frappe.msgprint(f"Deleted Draft Work Order {wo_name}")