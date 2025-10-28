import frappe

@frappe.whitelist()
def get_sales_order_outstanding(so_name):
    """
    Calculates the true outstanding amount for a given Sales Order by checking
    all linked and submitted Sales Invoices and the payments made against them.
    """
    if not so_name:
        return 0

    # Get the Sales Order details
    so = frappe.get_doc("Sales Order", so_name)
    so_grand_total = so.grand_total

    # Get all submitted Sales Invoices linked to this Sales Order
    linked_invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "sales_order": so_name,
            "docstatus": 1  # Only consider submitted invoices
        },
        fields=["name", "grand_total", "outstanding_amount"]
    )

    total_paid = 0
    # Add the advance paid directly on the Sales Order
    total_paid += so.advance_paid

    # Calculate the amount paid against each invoice
    for inv in linked_invoices:
        paid_on_invoice = inv.grand_total - inv.outstanding_amount
        total_paid += paid_on_invoice

    outstanding_balance = so_grand_total - total_paid

    # save new outstanding balance in database 
    so.db_set('custom_outstanding_balance', outstanding_balance)

    # Ensure the balance doesn't go below zero
    return outstanding_balance if outstanding_balance > 0 else 0


@frappe.whitelist()
def update_so_balance_on_payment(doc, method):
    """
    This function is triggered by hooks on Payment Entry and Journal Entry.
    It finds the related Sales Order and updates its outstanding balance field.
    """
    # --- FIX STARTS HERE ---
    # Add a guard clause to check if the 'references' table exists.
    # A Journal Entry does not have this table, so doc.get("references") will be None.
    # This check prevents the code from crashing when a Journal Entry is submitted.
    if not doc.get("references"):
        return  # Exit the function gracefully
    # --- FIX ENDS HERE ---

    sales_orders_to_update = set()

    for ref in doc.get("references"):
        if ref.reference_doctype == "Sales Invoice":
            so_name = frappe.db.get_value(
                "Sales Invoice Item",
                {"parent": ref.reference_name, "sales_order": ["is", "set"]},
                "sales_order"
            )

            if so_name:
                sales_orders_to_update.add(so_name)
    
    # Now update each unique Sales Order found
    for so_name in sales_orders_to_update:
        try:
            new_balance = get_sales_order_outstanding(so_name)
            frappe.db.set_value("Sales Order", so_name, "custom_outstanding_balance", new_balance)

        except Exception as e:
            frappe.log_error(f"Failed to update outstanding balance for SO {so_name}: {e}", "SO Balance Update Error")