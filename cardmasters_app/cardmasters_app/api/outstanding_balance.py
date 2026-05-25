import frappe

@frappe.whitelist()
def get_sales_order_outstanding(so_name):
    """
    Calculates the true outstanding amount for a Sales Order by preventing 
    the double-counting of allocated advances.
    """
    if not so_name:
        return 0

    so = frappe.get_doc("Sales Order", so_name)
    
    # 1. Safely find all linked Sales Invoices via the Item table
    linked_items = frappe.get_all(
        "Sales Invoice Item",
        filters={"sales_order": so_name, "docstatus": 1},
        fields=["parent"]
    )
    invoice_names = list(set([item.parent for item in linked_items]))

    total_billed = 0
    total_invoice_outstanding = 0
    allocated_advances = 0

    # 2. If invoices exist, tally their totals and applied advances
    if invoice_names:
        invoices = frappe.get_all(
            "Sales Invoice",
            filters={"name": ["in", invoice_names], "docstatus": 1},
            fields=["name", "grand_total", "outstanding_amount"]
        )

        for inv in invoices:
            total_billed += inv.grand_total
            total_invoice_outstanding += inv.outstanding_amount

        # --- THE FIX ---
        # Fetch advances linked to these specific invoices without forcing the Reference Type.
        # This correctly captures the Payment Entries pulled in via "Get Advances".
        advances = frappe.get_all(
            "Sales Invoice Advance",
            filters={"parent": ["in", invoice_names]},
            fields=["allocated_amount"]
        )
        allocated_advances = sum(adv.allocated_amount for adv in advances)

    # 3. Calculate remaining unbilled value
    unbilled_amount = max(0, so.grand_total - total_billed)
    
    # 4. Calculate advances still floating on the SO (not yet invoiced)
    unallocated_advance = max(0, so.advance_paid - allocated_advances)

    # 5. Final True Outstanding
    outstanding_balance = unbilled_amount + total_invoice_outstanding - unallocated_advance

    return outstanding_balance if outstanding_balance > 0 else 0


@frappe.whitelist()
def update_so_balance_on_payment(doc, method):
	"""
	Triggered by hooks (on_submit, on_cancel) for Payment Entry and Journal Entry.
	"""
	if not doc.get("references"):
		return  

	sales_orders_to_update = set()

	for ref in doc.get("references"):
		# Catch Downpayments made directly against the Sales Order
		if ref.reference_doctype == "Sales Order":
			sales_orders_to_update.add(ref.reference_name)

		# Catch Payments made against Sales Invoices
		elif ref.reference_doctype == "Sales Invoice":
			so_items = frappe.get_all(
				"Sales Invoice Item",
				filters={"parent": ref.reference_name, "sales_order": ["is", "set"]},
				fields=["sales_order"]
			)
			for item in so_items:
				sales_orders_to_update.add(item.sales_order)
	
	# Update each unique Sales Order found
	for so_name in sales_orders_to_update:
		try:
			new_balance = get_sales_order_outstanding(so_name)
			frappe.db.set_value("Sales Order", so_name, "custom_outstanding_balance", new_balance)
		except Exception as e:
			frappe.log_error(
				message=f"Failed to update outstanding balance for SO {so_name}: {str(e)}", 
				title="SO Balance Update Error"
			)