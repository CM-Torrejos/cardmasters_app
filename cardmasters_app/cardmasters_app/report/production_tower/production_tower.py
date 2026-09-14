import frappe
from frappe import _
from frappe.utils import cint


WORK_ORDER_FIELDS = [
    "name", "produced_qty", "qty", "custom_bypass", "production_item",
    "custom_blue_order", "custom_rush_order", "workflow_state",
]

# Keep aligned with work_order_workflow_trigger's production-concluded states.
PRODUCTION_CONCLUDED_STATES = {"Pending Consumption", "Pending Claiming", "In Claiming"}


def completion_label(completed_qty, required_qty, pending_posting=False):
    percent = int(min(completed_qty / required_qty * 100, 100)) if required_qty > 0 else 0
    label = f"{percent}%"
    if pending_posting:
        label += " ({0})".format(_("Pending Posting"))
    return label


def execute(filters=None):
    filters = frappe._dict(filters or {})
    branches = (get_sales_order_branches(filters) + get_material_request_branches(filters)
                + get_sales_return_branches(filters))
    # Sort whole branches together by target date; preserve source order for ties.
    branches.sort(key=lambda branch: str(branch[0].get("date") or ""), reverse=True)
    rows = [row for branch in branches for row in branch]
    if cint(filters.get("hide_completed")):
        rows = hide_completed_rows(rows)
    return get_columns(), rows


def hide_completed_rows(rows):
    # Filter after calculating totals so hiding finished work does not change
    # the remaining parents' coverage or completion. Remove a completed row's
    # descendants too, keeping children attached to their original parent.
    visible = []
    hidden_indent = None
    for row in rows:
        if hidden_indent is not None:
            if row["indent"] > hidden_indent:
                continue
            hidden_indent = None
        if (row.get("completion_rate") or "").split("%", 1)[0] == "100":
            hidden_indent = row["indent"]
            continue
        visible.append(row)
    return visible


def apply_source_filters(source_filters, filters, doctype):
    if filters.get("company"):
        source_filters["company"] = filters.company
    if filters.get("target_date"):
        date_field = "delivery_date" if doctype == "Sales Order" else "schedule_date"
        source_filters[date_field] = filters.target_date
    if filters.get("branch"):
        # Only allow the two supported source fields, including for API callers.
        if filters.get("branch_source") == "custom_production_branch":
            branch_field = "custom_production_branch"
        else:
            branch_field = "branch" if doctype == "Sales Order" else "custom_for_branch"
        source_filters[branch_field] = filters.branch
    if filters.get("from_date") and filters.get("to_date"):
        source_filters["transaction_date"] = ["between", [filters.from_date, filters.to_date]]
    if filters.get("workflow_state"):
        source_filters["workflow_state"] = filters.workflow_state
    return source_filters


def get_sales_order_branches(filters):
    sales_orders = frappe.get_all(
        "Sales Order",
        filters=apply_source_filters(
            {"docstatus": 1, "workflow_state": ["!=", "Production Concluded"]}, filters, "Sales Order"
        ),
        fields=["name", "customer", "delivery_date", "workflow_state", "custom_blue_order", "custom_rush_order",
                "custom_quick_production_note"],
        order_by="delivery_date desc, name asc",
    )
    branches = []
    for so in sales_orders:
        items = frappe.get_all(
            "Sales Order Item", filters={"parent": so.name},
            fields=["item_code", "item_name", "qty", "name", "bom_no"], order_by="idx asc",
        )
        items = [item for item in items if item.bom_no]
        work_orders = {
            item.name: frappe.get_all(
                "Work Order",
                filters={"sales_order": so.name, "sales_order_item": item.name,
                         "production_item": item.item_code, "docstatus": ["!=", 2]},
                fields=WORK_ORDER_FIELDS, order_by="name asc",
            ) for item in items
        }
        branches.append(build_branch({
            "label_name": f"{so.name} - {so.customer}",
            "reference_doctype": "Sales Order", "reference_name": so.name,
            "date": so.delivery_date, "workflow_state": so.workflow_state,
            "custom_blue_order": so.custom_blue_order, "custom_rush_order": so.custom_rush_order,
            "custom_quick_production_note": so.custom_quick_production_note,
        }, items, work_orders))
    return branches


def get_material_request_branches(filters):
    requests = frappe.get_all(
        "Material Request",
        filters=apply_source_filters({
            "docstatus": 1, "material_request_type": "Manufacture",
            "status": ["not in", ["Stopped", "Cancelled"]],
            "workflow_state": ["!=", "Production Concluded"],
        }, filters, "Material Request"),
        fields=["name", "schedule_date", "workflow_state", "status", "custom_for_branch"],
        order_by="schedule_date desc, name asc",
    )
    if not requests:
        return []

    names = [request.name for request in requests]
    items = frappe.get_all(
        "Material Request Item", filters={"parent": ["in", names]},
        fields=["parent", "name", "item_code", "item_name", "qty", "stock_qty", "conversion_factor"],
        order_by="parent asc, idx asc",
    )
    items_by_parent = {}
    item_by_key = {}
    for item in items:
        # Work Orders use stock UOM. Do not compare e.g. boxes against pieces.
        item.qty = item.stock_qty if item.stock_qty is not None else item.qty * (item.conversion_factor or 1)
        items_by_parent.setdefault(item.parent, []).append(item)
        item_by_key[(item.parent, item.name)] = item

    fields = WORK_ORDER_FIELDS + ["material_request", "material_request_item", "custom_document",
                                  "custom_document_id", "custom_document_item_id"]
    linked = {}
    for links in ({"material_request": ["in", names]},
                  {"custom_document": "Material Request", "custom_document_id": ["in", names]}):
        for wo in frappe.get_all("Work Order", filters={**links, "docstatus": ["!=", 2]},
                                 fields=fields, order_by="name asc"):
            linked[wo.name] = wo

    work_orders = {}
    for wo in sorted(linked.values(), key=lambda row: row.name):
        # Standard links take precedence. Custom links support older app records.
        # Never guess by item code: the same item can occur twice on one request.
        if wo.material_request and wo.material_request_item:
            key = (wo.material_request, wo.material_request_item)
        elif wo.custom_document == "Material Request":
            key = (wo.custom_document_id, wo.custom_document_item_id)
        else:
            continue
        item = item_by_key.get(key)
        if item and item.item_code == wo.production_item:
            work_orders.setdefault(item.name, []).append(wo)

    branches = []
    for request in requests:
        label = f"[MR] {request.name}"
        if request.custom_for_branch:
            label += f" - {request.custom_for_branch}"
        branches.append(build_branch({
            "label_name": label, "reference_doctype": "Material Request", "reference_name": request.name,
            "date": request.schedule_date, "workflow_state": request.workflow_state or request.status,
        }, items_by_parent.get(request.name, []), work_orders))
    return branches


def get_sales_return_branches(filters):
    source_filters = {"docstatus": 1, "is_return": 1}
    if filters.get("company"):
        source_filters["company"] = filters.company
    if filters.get("branch"):
        # Returns own their branch assignments; backjobs may run elsewhere
        # than the original Sales Order. Delivery Note's For Branch is `branch`.
        branch_field = "custom_production_branch" if filters.get("branch_source") == "custom_production_branch" else "branch"
        source_filters[branch_field] = filters.branch
    if filters.get("from_date") and filters.get("to_date"):
        source_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
    # Delivery Notes have status, but no workflow_state field.
    if filters.get("workflow_state"):
        source_filters["status"] = filters.workflow_state
    returns = frappe.get_all(
        "Delivery Note", filters=source_filters,
        fields=["name", "customer", "posting_date", "status"], order_by="posting_date desc, name asc",
    )
    if not returns:
        return []

    items = frappe.get_all(
        "Delivery Note Item",
        filters={"parent": ["in", [row.name for row in returns]], "custom_for_backjob": 1},
        fields=["parent", "name", "item_code", "item_name", "qty", "stock_qty", "conversion_factor",
                "against_sales_order", "so_detail"], order_by="parent asc, idx asc",
    )
    if not items:
        return []
    so_names = sorted({item.against_sales_order for item in items if item.against_sales_order})
    sales_orders = {so.name: so for so in frappe.get_all(
        "Sales Order", filters={"name": ["in", so_names]},
        fields=["name", "delivery_date"], order_by="name asc",
    )} if so_names else {}

    items_by_parent = {}
    item_by_key = {}
    dates_by_parent = {}
    for item in items:
        so = sales_orders.get(item.against_sales_order, frappe._dict())
        if so.delivery_date:
            dates_by_parent.setdefault(item.parent, []).append(so.delivery_date)
        item.qty = abs(item.stock_qty if item.stock_qty is not None else item.qty * (item.conversion_factor or 1))
        # Creation links to the SO item, not the Delivery Note row. Combine batch
        # splits of that exact SO item so its Work Orders are counted only once.
        key = (item.parent, item.against_sales_order, item.so_detail, item.item_code)
        if item.against_sales_order and item.so_detail:
            if key in item_by_key:
                item_by_key[key].qty += item.qty
                continue
            item_by_key[key] = item
        items_by_parent.setdefault(item.parent, []).append(item)

    if not items_by_parent:
        return []
    work_orders = {}
    for wo in frappe.get_all(
        "Work Order",
        filters={"custom_sales_return_reference": ["in", list(items_by_parent)], "docstatus": ["!=", 2]},
        fields=WORK_ORDER_FIELDS + ["custom_sales_return_reference", "custom_document", "custom_document_id",
                                   "custom_document_item_id", "sales_order", "sales_order_item"],
        order_by="name asc",
    ):
        if wo.custom_document == "Sales Order" and wo.custom_document_id and wo.custom_document_item_id:
            so_name, so_item = wo.custom_document_id, wo.custom_document_item_id
        else:
            so_name, so_item = wo.sales_order, wo.sales_order_item
        item = item_by_key.get((wo.custom_sales_return_reference, so_name, so_item, wo.production_item))
        if item:
            work_orders.setdefault(item.name, []).append(wo)

    branches = []
    for sales_return in returns:
        return_items = items_by_parent.get(sales_return.name)
        if not return_items:
            continue
        # A return can reference several orders. Show the earliest linked due
        # date; leave it blank when none exists rather than inventing a deadline.
        dates = dates_by_parent.get(sales_return.name, [])
        target_date = min(dates) if dates else None
        if filters.get("target_date") and str(target_date or "") != str(filters.target_date):
            continue
        branches.append(build_branch({
            "label_name": f"[SR] {sales_return.name} - {sales_return.customer}",
            "reference_doctype": "Delivery Note", "reference_name": sales_return.name,
            "date": target_date, "workflow_state": sales_return.status,
        }, return_items, work_orders))
    return branches


def build_branch(reference, items, work_orders_by_item):
    """Apply the same coverage, completion and bypass rules to each demand source."""
    item_rows = []
    total_qty = 0
    total_completed = 0
    has_pending_posting = False
    has_bypass = 0

    eligible_item_count = 0
    fully_planned_item_count = 0

    for item in items:
        eligible_item_count += 1

        wos = work_orders_by_item.get(item.name, [])

        l3_rows = []
        item_produced_acc = 0
        item_completed_acc = 0
        item_planned_acc = 0

        for wo in wos:
            wo_qty = wo.qty or 0
            item_planned_acc += wo_qty
            wo_produced = wo_qty if wo.custom_bypass else (wo.produced_qty or 0)
            item_produced_acc += wo_produced
            wo_completed = max(wo_produced, wo_qty) if wo.workflow_state in PRODUCTION_CONCLUDED_STATES else wo_produced
            item_completed_acc += wo_completed

            if wo.custom_bypass:
                has_bypass = 1

            l3_rows.append({
                "label_name": wo.name,
                "reference_doctype": "Work Order",
                "reference_name": wo.name,
                "wo_status": wo.workflow_state,
                "produced_qty": wo.produced_qty,
                "qty": wo_qty,
                "completion_rate": completion_label(wo_completed, wo_qty, wo_completed > wo_produced),
                "is_bypass": wo.custom_bypass,
                "custom_blue_order": wo.custom_blue_order,
                "custom_rush_order": wo.custom_rush_order,
                "indent": 2
            })

        if item_planned_acc >= item.qty:
            fully_planned_item_count += 1

        planning_status = "ok"
        if not wos:
            planning_status = "orphan"
        elif item_planned_acc < item.qty:
            planning_status = "shortfall"

        # Only mark the parent pending when its required progress relies on
        # unposted work. Extra WOs cannot overstate another item's progress.
        pending_posting = min(item_completed_acc, item.qty) > min(item_produced_acc, item.qty)
        has_pending_posting = has_pending_posting or pending_posting
        total_qty += item.qty
        total_completed += min(item_completed_acc, item.qty)

        item_rows.append({
            "label_name": f"{item.item_code}: {item.item_name}",
            "qty": f"{int(item_planned_acc)} / {int(item.qty)}",
            # Keep fractional quantities for sorting; the display is rounded.
            "_sort_qty": item_planned_acc / item.qty if item.qty > 0 else None,
            "produced_qty": item_produced_acc,
            "completion_rate": completion_label(item_completed_acc, item.qty, pending_posting),
            "is_bypass": 1 if any(wo.get('is_bypass') for wo in l3_rows) else 0,
            "planning_status": planning_status,
            "indent": 1
        })
        item_rows.extend(l3_rows)

    incomplete_coverage = 1 if fully_planned_item_count != eligible_item_count else 0

    data = [{
        **reference,
        "completion_rate": completion_label(total_completed, total_qty, has_pending_posting),
        "qty": f"{fully_planned_item_count} / {eligible_item_count}",
        "_sort_qty": fully_planned_item_count / eligible_item_count if eligible_item_count else None,
        "is_bypass": has_bypass,
        "is_orphan_so": 1 if reference["reference_doctype"] == "Sales Order" and eligible_item_count == 0 else 0,
        "incomplete_coverage": incomplete_coverage,
        "indent": 0
    }]
    data.extend(item_rows)
    return data


def get_columns():
    return [
        {"label": _("Reference (SO / MR / SR / Item / WO)"), "fieldname": "label_name", "fieldtype": "Data", "width": 400},
        {"label": _("Target Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": _("Stage"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 160},
        {"label": _("Work Order Coverage"), "fieldname": "qty", "fieldtype": "Data", "width": 220},
        {"label": _("Completion"), "fieldname": "completion_rate", "fieldtype": "Data", "width": 210},
        {"label": _("WO Workflow State"), "fieldname": "wo_status", "fieldtype": "Data", "width": 180},
        {"label": _("Produced"), "fieldname": "produced_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Blue Order"), "fieldname": "custom_blue_order", "fieldtype": "Check", "width": 100},
        {"label": _("Rush Order"), "fieldname": "custom_rush_order", "fieldtype": "Check", "width": 100},
        {"label": _("Quick Production Note"), "fieldname": "custom_quick_production_note", "fieldtype": "Data", "width": 300},
    ]
