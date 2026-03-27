import frappe
from frappe.model.workflow import apply_workflow, WorkflowTransitionError, get_transitions

def work_order_workflow_trigger(doc, method):
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