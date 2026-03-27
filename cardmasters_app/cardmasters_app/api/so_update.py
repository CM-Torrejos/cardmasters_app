import frappe
from frappe.model.workflow import apply_workflow, WorkflowTransitionError
from frappe.model.workflow import get_transitions

def work_order_workflow_trigger(doc, method):
    if not doc.sales_order:
        return

    # 1. Fetch Sales Order and Row IDs
    so = frappe.get_doc("Sales Order", doc.sales_order)
    eligible_row_ids = [item.name for item in so.items if item.bom_no]
    
    if not eligible_row_ids:
        return

    # 2. Map current statuses of all Work Orders
    linked_wos = frappe.get_all("Work Order", 
        filters={"sales_order": so.name, "docstatus": ["<", 2]},
        fields=["sales_order_item", "workflow_state"]
    )

    wo_row_map = {wo.sales_order_item: wo.workflow_state for wo in linked_wos}
    # Important: Include the state of the document currently being saved
    wo_row_map[doc.sales_order_item] = doc.workflow_state 

    target_states = ["In Claiming", "Pending Claiming", "Pending Consumption"]

    # 3. Determine the "Production Status"
    done_count = 0
    for row_id in eligible_row_ids:
        if wo_row_map.get(row_id) in target_states:
            done_count += 1

    # 4. Determine Action based on SO current state vs Work Order reality
    action = None
    curr_so_state = so.workflow_state

    if done_count == len(eligible_row_ids):
        # EVERYTHING IS DONE
        if curr_so_state != "Production Concluded":
            action = "Conclude Production"

    elif done_count > 0:
        # AT LEAST ONE BUT NOT ALL
        if curr_so_state == "Production":
            action = "Partially Conclude Production"
        elif curr_so_state == "Production Concluded":
            action = "Convert to Partial Production Concluded"

    else:
        # NOTHING IS DONE (Everything reverted)
        if curr_so_state in ["Partial Production Concluded", "Production Concluded"]:
            action = "Revert to Production"

    # 5. Execute Action
    if action:
        try:
            # Final safety check: does this action actually exist for the current state?
            allowed_actions = [t.action for t in get_transitions(so)]
            if action in allowed_actions:
                apply_workflow(so, action)
            else:
                frappe.log_error(
                    title="Workflow Action Not Available",
                    message=f"Action '{action}' is not allowed from state '{curr_so_state}' for {so.name}"
                )
        except WorkflowTransitionError:
             frappe.log_error(
                title="SO Workflow Automation Failed",
                message=f"Error applying '{action}' to {so.name}. State: {curr_so_state}"
            )