import frappe
from frappe import _

def update_work_order_details(docname, qty, item_specifics=None, particulars=None):
    # 1. Load the document and basic variables
    doc = frappe.get_doc("Work Order", docname)
    qty = float(qty)
    old_qty = float(doc.qty)
    
    # Check if materials have already been transferred (greater than 0)
    current_transferred = float(doc.material_transferred_for_manufacturing or 0)
    
    # --- VALIDATION AGAINST SALES ORDER ---
    if doc.sales_order and doc.sales_order_item:
        so_qty = frappe.db.get_value("Sales Order Item", doc.sales_order_item, "qty")
        other_wo_qty = frappe.db.get_value("Work Order", 
            {"sales_order_item": doc.sales_order_item, "name": ["!=", docname], "docstatus": ["!=", 2]}, 
            "sum(qty)") or 0
        
        if (other_wo_qty + qty) > so_qty:
            frappe.throw(_("Total Work Order quantity ({0}) would exceed Sales Order quantity ({1})")
                         .format(other_wo_qty + qty, so_qty))

    changes = []

    # --- UPDATE QUANTITY & CHILD BOM ITEMS ---
    if qty != old_qty:
        # Update Header Qty
        frappe.db.set_value("Work Order", docname, "qty", qty, update_modified=True)
        
        # --- CONDITIONAL TRANSFER UPDATE ---
        # If materials were already transferred, update the tracking field to match new qty
        if current_transferred > 0:
            frappe.db.set_value("Work Order", docname, "material_transferred_for_manufacturing", qty)
        
        # Update Child Table (Required Items)
        for item in doc.required_items:
            # Calculate new proportional required quantity
            new_req_qty = (item.required_qty / old_qty) * qty
            
            update_dict = {"required_qty": new_req_qty}
            
            # If header transfer qty was > 0, update the row's transferred_qty as well
            # if current_transferred > 0:
            #     update_dict["transferred_qty"] = new_req_qty
                
            frappe.db.set_value("Work Order Item", item.name, update_dict)
        
        changes.append(f"Qty from {old_qty} to {qty}")

    # --- UPDATE EXISTING STOCK ENTRIES ---
    stock_entries = frappe.get_all("Stock Entry", 
        filters={"work_order": docname, "docstatus": 1, "stock_entry_type": "Material Transfer for Manufacture"}, 
        order_by="creation asc")
    
    if stock_entries:
        for i, entry in enumerate(stock_entries):
            new_fg_qty = qty if i == 0 else 0
            frappe.db.set_value("Stock Entry", entry.name, "fg_completed_qty", new_fg_qty)
            

    # --- UPDATE CUSTOM FIELDS ---
    frappe.db.set_value("Work Order", docname, {
        "custom_item_specifics": item_specifics or "",
        "custom_particulars": particulars or ""
    })

    # --- REFRESH & CACHE CLEAR ---
    if changes or item_specifics or particulars:
        doc.add_comment("Edit", text=f"Updated: {', '.join(changes)}")
        frappe.clear_cache(doctype="Work Order")
        frappe.clear_document_cache("Work Order", docname)
    
    return "Success"
