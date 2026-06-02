import frappe


def link_so_to_qtn(doc, method=None):
    """
    Hook: Quotation → on_update
    Takes the ID from the Quotation's 'custom_sales_order_ref'
    and writes the Quotation ID back to the linked Sales Order.
    """
    so_id = doc.get("custom_sales_order_ref")
    if so_id:
        frappe.db.set_value("Sales Order", so_id, "custom_quotation_ref", doc.name)
