import frappe
from frappe import _  # <--- THIS WAS MISSING

def manage_grant_usage(doc, method):
    if not doc.custom_grant:
        return

    # Fetch the Grant Document
    grant_doc = frappe.get_doc("Grant", doc.custom_grant)

    # Security: Customer Match
    if grant_doc.customer != doc.customer:
        frappe.throw(_("Grant {0} belongs to {1}, not {2}")
                     .format(doc.custom_grant, grant_doc.customer, doc.customer))

    if method == "on_submit":
        # Check balance BEFORE allowing the Sales Order to submit
        if doc.grand_total > grant_doc.available_balance:
            # Format numbers for better error messages
            avail = frappe.format_value(grant_doc.available_balance, "Currency")
            req = frappe.format_value(doc.grand_total, "Currency")
            frappe.throw(_("Insufficient Grant Balance! Available: {0}, Required: {1}").format(avail, req))

        # Add row to the child table
        grant_doc.append("grant_entries", {
            "sales_order": doc.name,
            "transaction_date": doc.transaction_date,
            "grand_total": doc.grand_total,
            "author": frappe.session.user
        })
        
        # This triggers Grant.validate() which handles redeemed_value and available_balance
        grant_doc.save(ignore_permissions=True)

    elif method == "on_cancel":
        found = False
        for row in grant_doc.get("grant_entries")[:]:
            if row.sales_order == doc.name:
                grant_doc.get("grant_entries").remove(row)
                found = True
        
        if found:
            # Again, saving triggers the recalculation automatically
            grant_doc.save(ignore_permissions=True)


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

def update_work_order_so_status(doc, method=None):
    """
    Triggers on Sales Order update. 
    Finds all linked Work Orders and updates their sales order status.
    """
    # Only proceed if the Sales Order has a workflow state
    if not doc.workflow_state:
        return

    # Find all Work Orders linked to this Sales Order
    work_orders = frappe.get_all("Work Order", 
        filters={"sales_order": doc.name}, 
        fields=["name", "custom_sales_order_state"]
    )

    for wo in work_orders:
        # Only update if the value has actually changed
        if wo.custom_sales_order_state != doc.workflow_state:
            frappe.db.set_value("Work Order", wo.name, "custom_sales_order_state", doc.workflow_state)

def strip_item_specifics_particulars_spaces(doc, method):
    """
    Strips leading and trailing spaces from custom_item_specifics 
    in Sales Order Items before submission.
    """
    for item in doc.items:
        if item.custom_item_specifics:
            item.custom_item_specifics = str(item.custom_item_specifics).strip()
        
        if item.custom_particulars:
            item.custom_particulars = str(item.custom_particulars).strip()