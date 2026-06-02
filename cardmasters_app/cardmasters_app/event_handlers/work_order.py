import frappe
from frappe.utils import cstr

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
			doc.custom_item_specifics = ""
		else:
			doc.custom_item_specifics = so_item_specifics

		# Checks if theres item particulars to pull
		if not so_item_particulars:
			doc.custom_particulars = ""
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

def warn_data_mismatch(doc, method):
    # Since this is an onload event for the Work Order, 'doc' is the Work Order.
    sales_order_item_ref = doc.sales_order_item
    
    if not sales_order_item_ref:
        return # Exit early if there's no linked Sales Order Item

    # Fetch the SO Item data
    so_item_data = frappe.db.get_value(
        "Sales Order Item",       
        sales_order_item_ref,     
        ["item_code", "custom_item_specifics", "custom_particulars"], 
        as_dict=True
    )

    if so_item_data:
        # --- START VALIDATION CHECK ---
        mismatches = []
        
        # Use cstr() to safely compare strings, treating None and "" as equal
        so_item_code = cstr(so_item_data.get("item_code"))
        wo_item_code = cstr(doc.production_item)
        
        so_specifics = cstr(so_item_data.get("custom_item_specifics"))
        wo_specifics = cstr(doc.custom_item_specifics)
        
        so_particulars = cstr(so_item_data.get("custom_particulars"))
        wo_particulars = cstr(doc.custom_particulars)

        if so_item_code != wo_item_code:
            mismatches.append(
                f"<b>Item Code:</b> SO Item ({so_item_code}) vs Work Order ({wo_item_code})"
            )
            
        if so_specifics != wo_specifics:
            mismatches.append(
                f"<b>Item Specifics:</b> SO Item ({so_specifics}) vs Work Order ({wo_specifics})"
            )
            
        if so_particulars != wo_particulars:
            mismatches.append(
                f"<b>Particulars:</b> SO Item ({so_particulars}) vs Work Order ({wo_particulars})"
            )
            
        if mismatches:
            msg_content = frappe._("There exist fields that do not match between the Sales Order Item and Work Order.<br><br>Please contact the sales order and work order owners to reconcile the discrepancy.<br><br>{0}").format("<br>".join(mismatches))
            
            # Use msgprint to show a non-blocking warning modal
            frappe.msgprint(
                msg=msg_content, 
                title=frappe._("Data Mismatch Warning"), 
                indicator="orange"
            )
        # --- END VALIDATION CHECK ---

def work_order_workflow_trigger(doc, method):
    from frappe.model.workflow import apply_workflow, WorkflowTransitionError, get_transitions
    if not doc.sales_order:
        return

    # 1. Fetch Sales Order
    so = frappe.get_doc("Sales Order", doc.sales_order)
    
    # Structure: { row_id: required_qty }
    so_item_requirements = {item.name: item.qty for item in so.items if item.bom_no}

    if not so_item_requirements:
        return

    # 2. Fetch all linked Work Orders (Exclude cancelled)
    linked_wos = frappe.get_all("Work Order", 
        filters={"sales_order": so.name, "docstatus": ["<", 2]},
        fields=["sales_order_item", "workflow_state", "qty", "name"]
    )

    # 3. Calculate Total "Finished" Quantity per SO Row
    target_states = ["In Claiming", "Pending Claiming", "Pending Consumption"]
    row_qty_done_map = {row_id: 0 for row_id in so_item_requirements.keys()}

    for wo in linked_wos:
        if wo.name == doc.name:
            continue # Skip DB version of current doc
            
        if wo.workflow_state in target_states:
            if wo.sales_order_item in row_qty_done_map:
                row_qty_done_map[wo.sales_order_item] += wo.qty

    # Add current doc progress if it's not being cancelled
    if doc.docstatus < 2 and doc.workflow_state in target_states:
        if doc.sales_order_item in row_qty_done_map:
            row_qty_done_map[doc.sales_order_item] += doc.qty

    # 4. Evaluation Logic
    total_rows = len(so_item_requirements)
    fully_done_rows = 0
    any_qty_progress = False

    for row_id, req_qty in so_item_requirements.items():
        actual_qty = row_qty_done_map.get(row_id, 0)
        if actual_qty >= req_qty:
            fully_done_rows += 1
        if actual_qty > 0:
            any_qty_progress = True

    # 5. Determine Action
    action = None
    curr_so_state = so.workflow_state.strip() # Clean state name

    # Condition A: Everything is finished
    if fully_done_rows == total_rows:
        if curr_so_state != "Production Concluded":
            action = "Conclude Production"

    # Condition B: Partial Progress (Some qty done, or some rows done, but not all)
    elif any_qty_progress or fully_done_rows > 0:
        if curr_so_state == "Production":
            action = "Partially Conclude Production"
        elif curr_so_state == "Production Concluded":
            action = "Convert to Partial Production Concluded"

    # Condition C: Zero Progress (Everything reverted or cancelled)
    else:
        if curr_so_state in ["Partial Production Concluded", "Production Concluded"]:
            action = "Revert to Production"

    # 6. Apply Workflow
    if action:
        try:
            allowed_actions = [t.action for t in get_transitions(so)]
            if action in allowed_actions:
                apply_workflow(so, action)
            else:
                # Diagnostics: If it gets "stuck", this log will tell us exactly why
                frappe.log_error(
                    title="SO Workflow Logic Skip",
                    message=(f"Action: {action} | "
                             f"Current SO State: {curr_so_state} | "
                             f"Allowed: {allowed_actions} | "
                             f"Progress: {any_qty_progress} | "
                             f"Done Rows: {fully_done_rows}/{total_rows}")
                )
        except WorkflowTransitionError:
             frappe.log_error(title="SO Workflow Failure", message=f"Workflow error on {so.name}")