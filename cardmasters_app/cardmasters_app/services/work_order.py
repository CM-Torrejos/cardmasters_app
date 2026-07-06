import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate


EDITABLE_OPERATION_FIELDS = (
    "operation",
    "workstation_type",
    "workstation",
    "sequence_id",
    "description",
    "time_in_mins",
    "batch_size",
)

PARENT_WORK_ORDER_FIELD = "custom_parent_work_order"


def get_linked_stock_work_orders(docname):
    if not docname:
        frappe.throw(_("Work Order is required."))

    parent_work_order = frappe.get_doc("Work Order", docname)
    parent_work_order.check_permission("read")

    return frappe.get_list(
        "Work Order",
        filters={PARENT_WORK_ORDER_FIELD: parent_work_order.name},
        fields=[
            "name",
            "item_name",
            "qty",
            "status",
            "workflow_state",
            "custom_particulars",
        ],
        order_by="creation asc",
    )


def get_damages_and_returns_defaults(docname):
    if not docname:
        frappe.throw(_("Work Order is required."))

    doc = frappe.get_doc("Work Order", docname)
    doc.check_permission("read")

    rows = []
    finished_batch = None

    if doc.sales_order and doc.sales_order_item and doc.production_item:
        from cardmasters_app.cardmasters_app.services.batch_handler import (
            resolve_sales_order_batch,
        )

        finished_batch = resolve_sales_order_batch(
            doc.sales_order,
            doc.sales_order_item,
            doc.production_item,
            doc.get("custom_item_specifics"),
        )

    if doc.production_item and finished_batch:
        rows.append({
            "item_code": doc.production_item,
            "item_name": doc.item_name or frappe.db.get_value("Item", doc.production_item, "item_name"),
            "quantity": flt(doc.qty),
            "batch": finished_batch,
            "uom": doc.stock_uom,
        })

    transfer_entries = frappe.get_all(
        "Stock Entry",
        filters={
            "work_order": doc.name,
            "docstatus": 1,
            "stock_entry_type": "Material Transfer for Manufacture",
        },
        pluck="name",
        order_by="posting_date asc, posting_time asc, creation asc",
    )

    if transfer_entries:
        transferred_rows = frappe.get_all(
            "Stock Entry Detail",
            filters={"parent": ["in", transfer_entries]},
            fields=["item_code", "item_name", "qty", "batch_no", "uom", "stock_uom"],
            order_by="parent asc, idx asc",
        )

        grouped_rows = {}
        for row in transferred_rows:
            if not row.item_code:
                continue

            uom = row.uom or row.stock_uom
            key = (row.item_code, row.batch_no or "", uom or "")
            if key not in grouped_rows:
                grouped_rows[key] = {
                    "item_code": row.item_code,
                    "item_name": row.item_name or frappe.db.get_value("Item", row.item_code, "item_name"),
                    "quantity": 0,
                    "batch": row.batch_no,
                    "uom": uom,
                }

            grouped_rows[key]["quantity"] += flt(row.qty)

        rows.extend(grouped_rows.values())

    existing_damages_and_returns = frappe.get_all(
        "Damages and Returns",
        filters={
            "work_order": doc.name,
            "docstatus": ["<", 2],
        },
        pluck="name",
        order_by="creation asc",
    )

    return {
        "work_order": doc.name,
        "date": nowdate(),
        "date_of_damage_or_return": nowdate(),
        "damaged_or_returned_item": rows,
        "existing_damages_and_returns": existing_damages_and_returns,
    }


def can_bypass_workstation_leader_check():
    return frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()


def get_work_order_operation_workstations(doc):
    workstations = []
    for row in doc.get("operations") or []:
        if row.workstation:
            workstations.append(row.workstation)

    return list(dict.fromkeys(workstations))


def get_work_order_operation_workstations_by_hidden_state(doc, hidden):
    workstations = []
    for row in doc.get("operations") or []:
        if row.workstation and cint(row.custom_workstation_hidden) == cint(hidden):
            workstations.append(row.workstation)

    return list(dict.fromkeys(workstations))


def get_current_employee_workstations():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee_name:
        return {
            "employee": None,
            "workstations": [],
            "message": _("No Employee record found for current user."),
        }

    employee = frappe.get_doc("Employee", employee_name)
    workstations = []

    workstation_leader_rows = employee.get("custom_workstation_leader")
    if isinstance(workstation_leader_rows, list):
        for row in workstation_leader_rows:
            if row.get("workstation"):
                workstations.append(row.workstation)
    elif workstation_leader_rows:
        workstation = frappe.db.get_value("Workstation Leader", workstation_leader_rows, "workstation")
        if workstation:
            workstations.append(workstation)

    workstations = list(dict.fromkeys(workstations))

    if not workstations:
        return {
            "employee": employee_name,
            "workstations": [],
            "message": _("You are not assigned as a workstation leader."),
        }

    return {
        "employee": employee_name,
        "workstations": workstations,
    }


def get_workstation_completion_options(docname, action=None):
    if not docname:
        frappe.throw(_("Work Order is required."))

    doc = frappe.get_doc("Work Order", docname)
    doc.check_permission("read")

    if doc.docstatus != 1:
        return {"can_show": False, "workstations": []}

    target_hidden = None
    if action == "complete":
        target_hidden = 0
    elif action == "undo":
        target_hidden = 1

    if target_hidden is None:
        operation_workstations = get_work_order_operation_workstations(doc)
    else:
        operation_workstations = get_work_order_operation_workstations_by_hidden_state(doc, target_hidden)

    completable_workstations = get_work_order_operation_workstations_by_hidden_state(doc, 0)
    undoable_workstations = get_work_order_operation_workstations_by_hidden_state(doc, 1)

    if can_bypass_workstation_leader_check():
        all_accessible_workstations = get_work_order_operation_workstations(doc)
        return {
            "can_show": bool(operation_workstations),
            "is_privileged": True,
            "workstations": operation_workstations,
            "prompt_required": len(all_accessible_workstations) > 1,
            "can_complete": bool(completable_workstations),
            "can_undo": bool(undoable_workstations),
            "message": get_no_workstation_completion_options_message(action),
        }

    employee_workstations = get_current_employee_workstations()
    if employee_workstations.get("message"):
        return {
            "can_show": False,
            "workstations": [],
            "message": employee_workstations.get("message"),
        }

    workstations = employee_workstations.get("workstations") or []
    all_accessible_workstations = workstations
    if target_hidden is not None:
        workstations = [workstation for workstation in workstations if workstation in operation_workstations]

    assigned_completable_workstations = [
        workstation for workstation in employee_workstations.get("workstations") or []
        if workstation in completable_workstations
    ]
    assigned_undoable_workstations = [
        workstation for workstation in employee_workstations.get("workstations") or []
        if workstation in undoable_workstations
    ]

    return {
        "can_show": bool(workstations),
        "is_privileged": False,
        "workstations": workstations,
        "prompt_required": len(all_accessible_workstations) > 1,
        "can_complete": bool(assigned_completable_workstations),
        "can_undo": bool(assigned_undoable_workstations),
        "message": get_no_workstation_completion_options_message(action),
    }


def get_no_workstation_completion_options_message(action):
    if action == "complete":
        return _("No workstation responsibilities are currently available to mark complete.")
    if action == "undo":
        return _("No completed workstation responsibilities are currently available to undo.")
    return None


def validate_workstation_completion_access(doc, workstation):
    if can_bypass_workstation_leader_check():
        operation_workstations = get_work_order_operation_workstations(doc)
        if workstation not in operation_workstations:
            frappe.throw(_("No operations found for the selected workstation."))
        return

    employee_workstations = get_current_employee_workstations()
    if not employee_workstations.get("employee"):
        frappe.throw(_("No Employee record found for current user."))

    assigned_workstations = employee_workstations.get("workstations") or []
    if not assigned_workstations:
        frappe.throw(_("You are not assigned as a workstation leader."))

    if workstation not in assigned_workstations:
        frappe.throw(_("You are not assigned as a workstation leader for {0}.").format(frappe.bold(workstation)))


def set_workstation_jobs_hidden(docname, workstation, hidden, action_label):
    if not docname:
        frappe.throw(_("Work Order is required."))
    if not workstation:
        frappe.throw(_("Workstation is required."))

    doc = frappe.get_doc("Work Order", docname)
    doc.check_permission("read")
    validate_workstation_completion_access(doc, workstation)

    updated_count = 0
    for row in doc.get("operations") or []:
        if row.workstation == workstation and cint(row.custom_workstation_hidden) != cint(hidden):
            row.custom_workstation_hidden = hidden
            updated_count += 1

    if not updated_count:
        return {
            "updated_count": 0,
            "message": _("No operations found for the selected workstation."),
        }

    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
    doc.add_comment(
        "Edit",
        text=_("{0} operation(s) for {1} {2} by {3}.").format(
            cint(updated_count),
            frappe.bold(workstation),
            action_label,
            frappe.bold(frappe.session.user),
        ),
    )

    return {
        "updated_count": cint(updated_count),
        "workstation": workstation,
    }


def mark_workstation_jobs_complete(docname, workstation):
    return set_workstation_jobs_hidden(docname, workstation, 1, _("hidden from workstation queue"))


def undo_workstation_jobs_complete(docname, workstation):
    return set_workstation_jobs_hidden(docname, workstation, 0, _("restored to workstation queue"))


def update_work_order_operations(doc, operations):
    """Apply user-editable operation values without accepting child rows from another Work Order."""
    operations = frappe.parse_json(operations)
    if not isinstance(operations, list):
        frappe.throw(_("Operations must be a list."))

    existing_rows = {row.name: row for row in doc.get("operations") or []}
    submitted_names = [
        row.get("operation_row_name")
        for row in operations
        if row.get("operation_row_name")
    ]
    if len(submitted_names) != len(set(submitted_names)):
        frappe.throw(_("The same operation row cannot be included more than once."))

    invalid_names = set(submitted_names) - set(existing_rows)
    if invalid_names:
        frappe.throw(_("One or more operation rows do not belong to this Work Order."))

    removed_names = set(existing_rows) - set(submitted_names)
    if removed_names:
        linked_job_cards = frappe.get_all(
            "Job Card",
            filters={
                "operation_id": ["in", list(removed_names)],
                "docstatus": ["<", 2],
            },
            pluck="name",
        )
        if linked_job_cards:
            frappe.throw(
                _("Operations linked to active Job Cards cannot be removed: {0}").format(
                    ", ".join(linked_job_cards)
                )
            )

    updated_rows = []
    for index, values in enumerate(operations, start=1):
        values = frappe._dict(values)
        if not values.operation:
            frappe.throw(_("Operation is required in row {0}.").format(index))
        if flt(values.time_in_mins) <= 0:
            frappe.throw(_("Operation Time must be greater than 0 in row {0}.").format(index))

        row = existing_rows.get(values.operation_row_name) or doc.append("operations", {})
        for fieldname in EDITABLE_OPERATION_FIELDS:
            row.set(fieldname, values.get(fieldname))
        row.batch_size = flt(row.batch_size) or 1
        row.idx = index
        updated_rows.append(row)

    doc.set("operations", updated_rows)


def update_work_order_details(docname, qty, item_specifics=None, particulars=None, operations=None):
    # 1. Load the document and basic variables
    doc = frappe.get_doc("Work Order", docname)
    doc.check_permission("write")

    qty = flt(qty)
    old_qty = flt(doc.qty)
    if qty <= 0:
        frappe.throw(_("Quantity must be greater than 0."))
    
    # Check if materials have already been transferred (greater than 0)
    current_transferred = float(doc.material_transferred_for_manufacturing or 0)
    
    # --- VALIDATION AGAINST SALES ORDER ---
    if doc.sales_order and doc.sales_order_item:
        so_qty = frappe.db.get_value("Sales Order Item", doc.sales_order_item, "qty")
        other_wo_qty = frappe.db.get_value("Work Order", 
            {"sales_order_item": doc.sales_order_item, "name": ["!=", docname], "docstatus": ["!=", 2]}, 
            "sum(qty)") or 0
        
        if (other_wo_qty + qty) > so_qty:
            frappe.throw(_("Total Work Order quantity ({0}) would exceed Sales Order quantity ({1})")
                         .format(other_wo_qty + qty, so_qty))

    changes = []

    if operations is not None:
        old_operation_count = len(doc.get("operations") or [])
        update_work_order_operations(doc, operations)
        new_operation_count = len(doc.get("operations") or [])
        changes.append(
            f"Operations updated ({old_operation_count} to {new_operation_count} rows)"
        )

    # --- UPDATE QUANTITY & CHILD BOM ITEMS ---
    if qty != old_qty:
        # Update Header Qty
        if operations is not None:
            doc.qty = qty
        else:
            frappe.db.set_value("Work Order", docname, "qty", qty, update_modified=True)
        
        # --- CONDITIONAL TRANSFER UPDATE ---
        # If materials were already transferred, update the tracking field to match new qty
        if current_transferred > 0:
            if operations is not None:
                doc.material_transferred_for_manufacturing = qty
            else:
                frappe.db.set_value("Work Order", docname, "material_transferred_for_manufacturing", qty)
        
        # Update Child Table (Required Items)
        for item in doc.required_items:
            # Calculate new proportional required quantity
            new_req_qty = (item.required_qty / old_qty) * qty
            
            update_dict = {"required_qty": new_req_qty}
            
            # If header transfer qty was > 0, update the row's transferred_qty as well
            # if current_transferred > 0:
            #     update_dict["transferred_qty"] = new_req_qty
                
            if operations is not None:
                item.required_qty = new_req_qty
            else:
                frappe.db.set_value("Work Order Item", item.name, update_dict)
        
        changes.append(f"Qty from {old_qty} to {qty}")

    # --- UPDATE EXISTING STOCK ENTRIES ---
    stock_entries = frappe.get_all("Stock Entry", 
        filters={"work_order": docname, "docstatus": 1, "stock_entry_type": "Material Transfer for Manufacture"}, 
        order_by="creation asc")
    
    if stock_entries:
        for i, entry in enumerate(stock_entries):
            new_fg_qty = qty if i == 0 else 0
            frappe.db.set_value("Stock Entry", entry.name, "fg_completed_qty", new_fg_qty)
            

    # --- UPDATE CUSTOM FIELDS AND OPERATIONS ---
    doc.custom_item_specifics = item_specifics or ""
    doc.custom_particulars = particulars or ""

    if operations is not None:
        # Work Orders are submitted when this action is available. Explicitly allow
        # the controlled child-table update while retaining normal Work Order validation.
        doc.flags.ignore_validate_update_after_submit = True
        doc.save(ignore_permissions=True)
    else:
        frappe.db.set_value("Work Order", docname, {
            "custom_item_specifics": doc.custom_item_specifics,
            "custom_particulars": doc.custom_particulars
        })

    # --- REFRESH & CACHE CLEAR ---
    if changes or item_specifics is not None or particulars is not None:
        change_summary = ", ".join(changes) or "Work Order details"
        doc.add_comment("Edit", text=f"Updated: {change_summary}")
        frappe.clear_cache(doctype="Work Order")
        frappe.clear_document_cache("Work Order", docname)
    
    return "Success"
