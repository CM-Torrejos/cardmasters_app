"""Submit selected legacy deliveries using normal production and stock validations."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

BRANCH = "Cagayan de Oro"
PAYMENT_METHODS = {"Acknowledgement Receipt": "Cash", "Collection Receipt": "Credit"}
CLAIMING_STATES = ("Not Started", "In Production", "Pending Consumption", "Pending Claiming", "In Claiming")


def _authorize(sales_order):
    frappe.only_for("System Manager")
    order = frappe.get_doc("Sales Order", sales_order)
    order.check_permission("write")
    if order.docstatus != 1 or order.status in ("Closed", "On Hold"):
        frappe.throw(_("Select a submitted Sales Order that is not closed or on hold."))
    return order


@frappe.whitelist()
def get_delivery_backlog(sales_order: str):
    order = _authorize(sales_order)
    names = frappe.get_all("Delivery Note Item", filters={"against_sales_order": order.name}, pluck="parent")
    if not names:
        return []
    return frappe.get_list(
        "Delivery Note", filters={"name": ["in", names], "docstatus": 0, "is_return": 0},
        fields=["name", "posting_date", "grand_total", "currency"], order_by="posting_date asc, name asc",
    )


def _payment_method(order):
    if order.get("custom_payment_method"):
        return order.custom_payment_method
    payments = frappe.db.sql("""
        SELECT DISTINCT pe.custom_receipt_type
        FROM `tabPayment Entry` pe JOIN `tabPayment Entry Reference` ref ON ref.parent = pe.name
        WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive'
          AND pe.party_type = 'Customer' AND pe.party = %s AND pe.company = %s
          AND ref.reference_doctype = 'Sales Order' AND ref.reference_name = %s
          AND ref.allocated_amount > 0
    """, (order.customer, order.company, order.name))
    methods = {PAYMENT_METHODS.get(row[0]) for row in payments}
    if len(methods) != 1 or None in methods:
        return "Cash"
    return methods.pop()


def _workflow_action(doc, target_status):
    """Use an allowed workflow transition for submit/cancel, when configured."""
    from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

    name = get_workflow_name(doc.doctype)
    if not name:
        return doc.submit() if target_status == 1 else doc.cancel()
    workflow = frappe.get_cached_doc("Workflow", name)
    targets = {state.state for state in workflow.states if cint(state.doc_status) == target_status}
    actions = [transition for transition in get_transitions(doc) if transition.next_state in targets]
    if len(actions) != 1:
        frappe.throw(_("{0}: expected one allowed workflow action to {1}; found {2}. Resolve the workflow first.").format(
            doc.name, "submit" if target_status == 1 else "cancel", len(actions)))
    return apply_workflow(doc, actions[0].action)


def _update_order_header(order):
    # Keep Allow on Submit off. The authorized backlog action performs only the
    # existing whitespace cleanup, without changing metadata or saving the order.
    cleaned_rows = []
    for row in order.items:
        changes = {}
        for fieldname in ("custom_item_specifics", "custom_particulars"):
            value = row.get(fieldname)
            if value and str(value).strip() != value:
                changes[fieldname] = str(value).strip()
        if changes:
            frappe.db.set_value("Sales Order Item", row.name, changes, update_modified=False)
            row.update(changes)
            cleaned_rows.append(str(row.idx))
    order.db_set({"custom_payment_method": _payment_method(order), "custom_production_branch": BRANCH})
    order.add_comment("Comment", "Updated Payment Method and Branch to enable submission of Delivery Note backlog.")
    if cleaned_rows:
        order.add_comment("Comment", "Trimmed surrounding whitespace from Item Specifics/Particulars on rows "
                          + ", ".join(cleaned_rows) + " through the System Manager backlog action; Allow on Submit remains off.")


def _advance_work_order_to_claiming(work):
    """Walk forward through allowed workflow actions after stock preparation."""
    from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

    workflow_name = get_workflow_name("Work Order")
    if not workflow_name:
        frappe.throw(_("Configure a Work Order workflow leading to In Claiming before submitting delivery backlog."))
    workflow = frappe.get_cached_doc("Workflow", workflow_name)
    work.reload()
    state_field = workflow.workflow_state_field
    state = work.get(state_field)
    if state not in CLAIMING_STATES:
        frappe.throw(_("Work Order {0}: cannot advance unsupported workflow state {1} to In Claiming.").format(work.name, state))
    if state == "In Claiming":
        return work
    for next_state in CLAIMING_STATES[CLAIMING_STATES.index(state) + 1:]:
        # Several roles may expose the same action; count distinct actions.
        actions = {transition.action for transition in get_transitions(work)
                   if transition.next_state == next_state}
        if len(actions) != 1:
            frappe.throw(_("Work Order {0}: expected one allowed workflow action from {1} to {2}; found {3}. "
                           "Check your workflow roles and transition conditions.").format(
                               work.name, work.get(state_field), next_state, len(actions)))
        work = apply_workflow(work, actions.pop())
        if work.docstatus != 1 or work.get(state_field) != next_state:
            frappe.throw(_("Work Order {0}: workflow did not reach submitted state {1}.").format(work.name, next_state))
    work.add_comment("Comment", "Advanced the Work Order to In Claiming through the Sales Order backlog automation.")
    return work


def _active_bom(item, company):
    boms = frappe.get_all("BOM", filters={"item": item, "company": company, "is_active": 1, "docstatus": 1},
                          fields=["name", "is_default"], order_by="name asc")
    defaults = [bom for bom in boms if bom.is_default]
    candidates = defaults or boms
    if len(candidates) != 1:
        frappe.throw(_("Item {0}: set exactly one active default BOM for company {1}.").format(item, company))
    return candidates[0].name


def _work_order(order, row, warehouse, branch, posting_date, result):
    names = frappe.get_all("Work Order", filters={"sales_order": order.name, "sales_order_item": row.name,
                                                 "docstatus": ["<", 2]}, pluck="name")
    if len(names) > 1:
        frappe.throw(_("Sales Order row {0} has multiple Work Orders. Resolve the production allocation first.").format(row.idx))
    work = frappe.get_doc("Work Order", names[0]) if names else None
    if not work and frappe.db.exists("Work Order", {"sales_order": order.name, "production_item": row.item_code,
                                                    "sales_order_item": ["is", "not set"], "docstatus": ["<", 2]}):
        frappe.throw(_("Item {0} has a legacy Work Order without a Sales Order item link. Link that Work Order first.").format(row.item_code))
    if work and (work.production_item != row.item_code or work.company != order.company):
        frappe.throw(_("Work Order {0} does not match the Sales Order item/company.").format(work.name))
    if work and not frappe.db.get_value("BOM", work.bom_no, "is_active"):
        if frappe.db.exists("Stock Entry", {"work_order": work.name, "docstatus": ["<", 2]}):
            frappe.throw(_("Work Order {0} has stock entries and an inactive BOM. Resolve those entries before amending.").format(work.name))
        active = _active_bom(row.item_code, order.company)
        if work.docstatus == 1:
            work.check_permission("cancel")
            cancelled = _workflow_action(work, 2)
            work = frappe.copy_doc(cancelled)
            work.amended_from = cancelled.name
            work.docstatus = 0
            work.workflow_state = None
            work.custom_batch = None
        work.bom_no = active
        work.get_items_and_operations_from_bom()
    if not work:
        work = frappe.get_doc({
            "doctype": "Work Order", "company": order.company, "production_item": row.item_code,
            "sales_order": order.name, "sales_order_item": row.name, "qty": row.stock_qty,
            "bom_no": _active_bom(row.item_code, order.company), "project": order.project,
            "fg_warehouse": warehouse, "wip_warehouse": branch.custom_workinprogress_warehouse,
            "source_warehouse": branch.custom_source_warehouse, "custom_production_branch": BRANCH,
            "planned_start_date": posting_date,
        })
        work.get_items_and_operations_from_bom()
    if work.docstatus == 0:
        work.custom_production_branch = BRANCH
        work.fg_warehouse = warehouse
        work.source_warehouse = branch.custom_source_warehouse
        work.wip_warehouse = branch.custom_workinprogress_warehouse
        for material in work.required_items:
            material.source_warehouse = branch.custom_source_warehouse
        work.save()
        work = _workflow_action(work, 1)
        work.add_comment("Comment", "Created the Work Order to enable submission of Delivery Note backlog.")
        result["work_orders"].append(work.name)
    if work.status in ("Closed", "Stopped"):
        frappe.throw(_("Work Order {0} is closed or stopped.").format(work.name))
    if not work.get("custom_batch"):
        from cardmasters_app.cardmasters_app.services.batch_handler import (
            autofill_work_order_batch_source_fields, create_or_assign_work_order_batch,
        )
        autofill_work_order_batch_source_fields(work)
        create_or_assign_work_order_batch(work)
        work.add_comment("Comment", "Linked the Sales Order item batch to enable submission of Delivery Note backlog.")
    return work


def _stock_entry(work, purpose, qty, posting_date, branch, result):
    from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

    if frappe.db.exists("Stock Entry", {"work_order": work.name, "docstatus": 0}):
        frappe.throw(_("Work Order {0} already has draft stock entries. Submit or remove those drafts first.").format(work.name))
    entry = frappe.get_doc(make_stock_entry(work.name, purpose, qty))
    entry.set_posting_time = 1
    entry.posting_date = posting_date
    entry.posting_time = "00:00:00"
    entry.custom_batched = 0 if purpose == "Material Transfer for Manufacture" else 1
    if purpose == "Material Transfer for Manufacture":
        entry.from_warehouse = branch.custom_source_warehouse
        entry.to_warehouse = branch.custom_workinprogress_warehouse
        for item in entry.items:
            item.s_warehouse = entry.from_warehouse
            item.t_warehouse = entry.to_warehouse
    entry.insert()
    entry.submit()
    label = "the Material Transfer for Manufacture" if purpose == "Material Transfer for Manufacture" else "the Manufacture entry"
    entry.add_comment("Comment", f"Created {label} to enable submission of Delivery Note backlog.")
    result["stock_entries"].append(entry.name)


@frappe.whitelist(methods=["POST"])
def submit_delivery_backlog(sales_order: str, delivery_notes: str, target_month: str):
    """One transaction; stock/controller errors roll back every document and comment."""
    order = _authorize(sales_order)
    selected = frappe.parse_json(delivery_notes)
    if not isinstance(selected, list) or not selected or any(not isinstance(name, str) for name in selected):
        frappe.throw(_("Select at least one draft Delivery Note."))
    if len(selected) != len(set(selected)):
        frappe.throw(_("Delivery Note selection contains duplicates."))
    if not target_month:
        frappe.throw(_("Choose a target month."))
    posting_date = getdate(target_month).replace(day=1)
    if posting_date > getdate():
        frappe.throw(_("Choose a target month that is not in the future."))
    # Serialize calls for the same order, including calls from different managers.
    frappe.db.sql("SELECT name FROM `tabSales Order` WHERE name=%s FOR UPDATE", order.name)
    order.reload()
    if order.docstatus != 1 or order.status in ("Closed", "On Hold"):
        frappe.throw(_("The Sales Order is no longer available for backlog submission."))
    frappe.db.savepoint("delivery_backlog")
    try:
        return _submit(order, selected, posting_date)
    except Exception:
        frappe.db.rollback(save_point="delivery_backlog")
        raise


def _submit(order, selected, posting_date):
    from erpnext.stock.doctype.batch.batch import get_batch_qty

    result = {"delivery_notes": [], "work_orders": [], "stock_entries": []}
    notes = []
    demand = {}
    rows = {row.name: row for row in order.items}
    for name in sorted(selected):
        frappe.db.sql("SELECT name FROM `tabDelivery Note` WHERE name=%s FOR UPDATE", name)
        note = frappe.get_doc("Delivery Note", name)
        note.check_permission("write")
        note.check_permission("submit")
        if note.docstatus != 0 or note.is_return or note.company != order.company or note.customer != order.customer:
            frappe.throw(_("{0} must be a draft non-return Delivery Note for this order's customer and company.").format(name))
        if note.get("packed_items"):
            frappe.throw(_("{0} contains a product bundle. Resolve its production manually.").format(name))
        for item in note.items:
            row = rows.get(item.so_detail)
            if item.against_sales_order != order.name or not row or row.item_code != item.item_code:
                frappe.throw(_("Every row of {0} must link to a matching item on Sales Order {1}.").format(name, order.name))
            if flt(item.stock_qty) <= 0:
                frappe.throw(_("{0} row {1} must have positive stock quantity.").format(name, item.idx))
            master = frappe.get_cached_doc("Item", item.item_code)
            if not master.is_stock_item:
                continue
            if not master.has_batch_no or master.has_serial_no:
                frappe.throw(_("Item {0}: backlog automation requires batch-tracked, non-serialized stock items.").format(item.item_code))
            if item.serial_and_batch_bundle:
                frappe.throw(_("{0} row {1} already has a serial/batch bundle. Resolve it first.").format(name, item.idx))
            key = (row.name, item.warehouse)
            demand[key] = demand.get(key, 0) + flt(item.stock_qty)
        notes.append(note)
    if len({key[0] for key in demand}) != len(demand):
        frappe.throw(_("The same Sales Order item is delivered from multiple warehouses. Resolve its production allocation first."))
    branch = frappe.get_cached_doc("Branch", BRANCH)
    for warehouse in (branch.custom_source_warehouse, branch.custom_workinprogress_warehouse, *[key[1] for key in demand]):
        details = frappe.db.get_value("Warehouse", warehouse, ["company", "is_group", "disabled"], as_dict=True) if warehouse else None
        if not details or details.company != order.company or details.is_group or details.disabled:
            frappe.throw(_("Configure enabled Cagayan de Oro warehouses belonging to {0}; invalid warehouse: {1}.").format(order.company, warehouse))
    _update_order_header(order)
    prepared_work_orders = []
    for (row_name, warehouse), qty in demand.items():
        work = _work_order(order, rows[row_name], warehouse, branch, posting_date, result)
        prepared_work_orders.append(work)
        available = flt(get_batch_qty(batch_no=work.custom_batch, warehouse=warehouse,
                                     posting_datetime=f"{posting_date} 00:00:00", ignore_reserved_stock=True,
                                     do_not_check_future_batches=True))
        missing = max(0, qty - available)
        if missing <= 0.000001:
            continue
        if work.fg_warehouse != warehouse:
            frappe.throw(_("Work Order {0} produces into {1}, but the Delivery Note uses {2}.").format(work.name, work.fg_warehouse, warehouse))
        if missing > flt(work.qty) - flt(work.produced_qty) + 0.000001:
            frappe.throw(_("Work Order {0} has insufficient unmanufactured quantity. Check existing stock and posting dates.").format(work.name))
        if not work.skip_transfer:
            if work.wip_warehouse != branch.custom_workinprogress_warehouse:
                frappe.throw(_("Work Order {0} uses a different WIP warehouse. Resolve it first.").format(work.name))
            transfer_qty = max(0, flt(work.produced_qty) + missing - flt(work.material_transferred_for_manufacturing))
            if transfer_qty > 0.000001:
                _stock_entry(work, "Material Transfer for Manufacture", transfer_qty, posting_date, branch, result)
        _stock_entry(work, "Manufacture", missing, posting_date, branch, result)
    for work in prepared_work_orders:
        _advance_work_order_to_claiming(work)
    for note in notes:
        note.set_posting_time = 1
        note.posting_date = posting_date
        note.posting_time = "00:00:00"
        note.custom_batched = 1
        note.custom_production_branch = BRANCH
        note.save()
        _workflow_action(note, 1)
        note.add_comment("Comment", "Submitted the Delivery Note backlog through the Sales Order automation.")
        result["delivery_notes"].append(note.name)
    return result
