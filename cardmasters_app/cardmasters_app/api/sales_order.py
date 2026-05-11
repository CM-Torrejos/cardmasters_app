import frappe
from frappe.model.mapper import get_mapped_doc

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