import frappe

@frappe.whitelist()
def update_work_order_details(docname, qty, item_specifics=None, particulars=None):
    doc = frappe.get_doc("Work Order", docname)
    
    # Normalize inputs: if they are None, turn them into empty strings
    item_specifics = item_specifics or ""
    particulars = particulars or ""
    
    changes = []
    
    # Check Quantity
    if float(qty) != float(doc.qty):
        doc.db_set('qty', qty)
        changes.append(f"Qty to {qty}")
        
    # Check Item Specifics
    if item_specifics != (doc.custom_item_specifics or ""):
        doc.db_set('custom_item_specifics', item_specifics)
        changes.append("Item Specifics")
        
    # Check Particulars
    if particulars != (doc.custom_particulars or ""):
        doc.db_set('custom_particulars', particulars)
        changes.append("Particulars")

    # Only add a comment if something actually changed
    if changes:
        doc.add_comment("Edit", text=f"Updated: {', '.join(changes)}")
        # refresh the timestamp of the document
        doc.db_set('modified', frappe.utils.now())
    
    return "Success"