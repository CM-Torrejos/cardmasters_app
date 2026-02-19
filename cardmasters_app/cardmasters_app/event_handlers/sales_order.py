import frappe

# Customer must have an alias if its facebook
def validate_alias_on_facebook_channel(doc, _method):
    has_alias = frappe.db.get_value("Sales Channel", doc.custom_sales_channel, "has_alias")
    if has_alias == 1:
        customer = frappe.db.get_value("Customer", doc.customer, "custom_alias")
        if not customer:
            frappe.throw(("The selected Sales Channel requires you to input the Customer's alias in the Customer Masters"))

def check_artist_status(doc, _method):
	so = frappe.get_doc("Sales Order", doc.sales_order)
	if so.custom_artist:
		so = apply_workflow(doc, "Begin Layout")
		so.save()

def update_item_class_on_update(doc, _method=None):
    """
    PURPOSE: update the sales-order-item's class field to the item's default selling cost center
    when using the 'Update Items' button or manual row edits.
    """
    # Look up the Company from the Parent Sales Order (DocType: Sales Order)
    order_company = frappe.db.get_value("Sales Order", doc.parent, "company")

    if order_company:
        # Check if the Item Master has a specific default for this Company
        item_specific_default = frappe.db.get_value("Item Default", 
            {
                "parent": doc.item_code, 
                "company": order_company
            }, 
            "selling_cost_center"
        )

        # Override the Cost Center if a specific default is found
        if item_specific_default:
            doc.cost_center = item_specific_default


def update_item_class_on_creation_from_quotation(doc, _method=None):
    """
    PURPOSE: update the sales-order-item's class field to the item's 
    default selling cost center when a Sales Order is generated from a Quotation.
    """
    if not doc.items:
        return

    for item in doc.items:
        # Search the 'Item Default' table using the Item Code and SO Company
        item_specific_default = frappe.db.get_value("Item Default", 
            {
                "parent": item.item_code, 
                "company": doc.company
            }, 
            "selling_cost_center"
        )

        # Force the Item-specific default into the mapped row
        if item_specific_default:
            item.cost_center = item_specific_default