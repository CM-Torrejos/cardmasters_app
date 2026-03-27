import frappe
from frappe.model.workflow import apply_workflow  # get_transitions no longer used
from frappe import _

def pull_sales_order_details(doc, method=None):
	"""Runs on Work Order (e.g., validate/before_save).
	Copies header + line-level fields from Sales Order when linked,
	but gracefully skips when there's no SO.
	"""

	# --- No Sales Order? Skip politely and exit.
	if not doc.sales_order:
		frappe.msgprint("No Sales Order linked; skipping field inheritance.",
						alert=True, indicator="orange")
		return

	# --- Sales Order name provided but missing in DB
	if not frappe.db.exists("Sales Order", doc.sales_order):
		frappe.msgprint(f"Sales Order {doc.sales_order} not found; skipping field inheritance.",
						alert=True, indicator="orange")
		return

	# --- Load Sales Order and copy header fields
	so = frappe.get_doc("Sales Order", doc.sales_order)

	# --- Matches the Work Order Item to its Respective Sales Order Row
	so_item_row = None
	if getattr(doc, "sales_order_item", None):
		try:
			so_item_row = frappe.get_doc("Sales Order Item", doc.sales_order_item)
		except frappe.DoesNotExistError:
			for row in so.items:
				if row.name == doc.sales_order_item:
					so_item_row = row
					break

	# --- Fallback if the previous method failed to match
	if not so_item_row and doc.production_item:
		for row in so.items:
			if row.item_code == doc.production_item:
				so_item_row = row
				break

	# --- Pulls and sets the matched item row's specifics and particulars
	if so_item_row:

		so_item_specifics = so_item_row.get("custom_item_specifics")
		so_item_particulars = so_item_row.get("custom_particulars")
		so_has_advance_withdrawal = so_item_row.get("custom_has_advance_withdrawal")

		doc.custom_has_advance_withdrawal = so_has_advance_withdrawal

		# Checks if theres item specifics to pull
		if not so_item_specifics:
			doc.custom_item_specifics = "No Item Specifics"
		else:
			doc.custom_item_specifics = so_item_specifics

		# Checks if theres item particulars to pull
		if not so_item_particulars:
			doc.custom_particulars = "No Item Particulars"
		else:
			doc.custom_particulars = so_item_particulars

	else:
		hint = (f"SO Item not matched. Checked sales_order_item={getattr(doc, 'sales_order_item', None)} "
				f"and production_item={getattr(doc, 'production_item', None)}.")
		frappe.msgprint(f"Could not copy item-level specifics/particulars. {hint}",
						alert=True, indicator="orange")
	
	# --- Pull and sets header values
	doc.custom_customer = so.get("customer")
	doc.custom_for_new_flow = so.get("custom_for_new_flow")
	doc.custom_blue_order = so.get("custom_blue_order")
	doc.custom_deadline = so.get("delivery_date")
	doc.custom_rush_order = so.get("custom_rush_order")
	doc.custom_for_branch = so.get("custom_for_branch")

	# --- Pull and sets remarks
	so_remarks = so.get("custom_remarks")
	so_remarks_production = so.get("custom_remarks_production")

	if not so_remarks:
		doc.custom_remarks = "No Remarks from Customer"
	else:
		doc.custom_remarks = so_remarks

	if not so_remarks_production:
		doc.custom_remarks_production = "No Remarks for Production"
	else:
		doc.custom_remarks_production = so_remarks_production

	# --- Pulls Artist Card and Artist assigned
	artist_card = frappe.db.get_value("Artist Card", {"sales_order": doc.sales_order}, "name")
	if artist_card:
		doc.custom_artist_card = artist_card
		ac = frappe.get_doc("Artist Card", artist_card)
		doc.custom_artist_assigned = ac.get("artist")

		ac_bom = ac.get("bom")
		ac_remarks = ac.get("remarks")

		if not ac_bom:
			doc.custom_artist_bom = "No BOM from Artist"
		else:
			doc.custom_artist_bom = ac_bom

		if not ac_remarks:
			doc.custom_artist_remarks = "No Remarks from Artist"
		else:
			doc.custom_artist_remarks = ac_remarks
		
	else:
		frappe.publish_realtime(
			"msgprint",
			{
				"message": "This Work Order has no Artist Card. Be warned!",
				"title": "Warning",
				"indicator": "orange",
				"alert": True
			},
			user=frappe.session.user,
			after_commit=True
		)

def before_work_order_submit(doc, method):
	"""On WO submit, advance the SO workflow from 'Artist' → 'Begin Production' when linked."""
	if not doc.sales_order:
		return

	so_name = doc.sales_order
	if not frappe.db.exists("Sales Order", so_name):
		frappe.msgprint(f"Sales Order {so_name} not found; skipping workflow transition.",
						alert=True, indicator="orange")
		return

	so = frappe.get_doc("Sales Order", so_name)

	if so.workflow_state == "Artist":
		try:
			apply_workflow(so, "Begin Production")
			so.save()
		except Exception:
			frappe.log_error(frappe.get_traceback(),
							 f"Failed to advance Sales Order workflow for {so.name}")
			frappe.msgprint("Could not advance Sales Order workflow. Check state/permissions.",
							alert=True, indicator="red")

def validate_so_workflow_state(doc, method):
    # Only check if there is a linked Sales Order
    if doc.sales_order:
        # Fetch the workflow state from the Sales Order
        so_workflow_state = frappe.db.get_value("Sales Order", doc.sales_order, "workflow_state")

        if so_workflow_state == "Pending":
            frappe.throw(
                _("Work Order cannot be created. Sales Order {0} is still in 'Pending' state.")
                .format(frappe.bold(doc.sales_order))
            )
			
def clear_child_rows(doc, method):
	# Clean up child table rows for this Work Order as needed.
	frappe.db.delete("Artist BOM table", {"parent": doc.name})
