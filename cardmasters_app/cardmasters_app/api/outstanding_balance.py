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

    # Ensure the balance doesn't go below zero
    return outstanding_balance if outstanding_balance > 0 else 0


@frappe.whitelist()
def update_so_balance_on_payment(payment_doc, method):
    """
    This function is triggered by hooks on Payment Entry and Journal Entry.
    It finds the related Sales Order and updates its outstanding balance field.
    """
    sales_orders_to_update = set()

    for ref in payment_doc.get("references"):
        if ref.reference_doctype == "Sales Invoice":
            # --- THIS IS THE CORRECTED PART ---
            # The link from SI to SO is in the child table (Sales Invoice Item), not the header.
            # We get the sales_order from the first item in the invoice that has a link.
            # This is safe because items on a single invoice are almost always from the same SO.
            so_name = frappe.db.get_value(
                "Sales Invoice Item",
                {"parent": ref.reference_name, "sales_order": ["is", "set"]},
                "sales_order"
            )
            # --- END OF CORRECTION ---

            if so_name:
                sales_orders_to_update.add(so_name)
    
    # Now update each unique Sales Order found
    for so_name in sales_orders_to_update:
        try:
            # RE-USE THE FUNCTION YOU ALREADY WROTE!
            # Assuming get_sales_order_outstanding is in the same file
            new_balance = get_sales_order_outstanding(so_name)

            # Update the value directly in the database
            frappe.db.set_value("Sales Order", so_name, "custom_outstanding_balance", new_balance)

        except Exception as e:
            frappe.log_error(f"Failed to update outstanding balance for SO {so_name}: {e}", "SO Balance Update Error")
