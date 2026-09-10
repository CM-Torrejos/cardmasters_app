import frappe
from frappe import _


WORK_ORDER_FIELDS = ["name", "status", "produced_qty", "qty", "custom_bypass", "production_item"]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    branches = get_sales_order_branches(filters) + get_material_request_branches(filters)
    # Sort whole branches together by target date; preserve source order for ties.
    branches.sort(key=lambda branch: str(branch[0].get("date") or ""), reverse=True)
    return get_columns(), [row for branch in branches for row in branch]


def apply_source_filters(source_filters, filters):
    if filters.get("from_date") and filters.get("to_date"):
        source_filters["transaction_date"] = ["between", [filters.from_date, filters.to_date]]
    if filters.get("workflow_state"):
        source_filters["workflow_state"] = filters.workflow_state
    return source_filters


def get_sales_order_branches(filters):
    sales_orders = frappe.get_all(
        "Sales Order",
        filters=apply_source_filters({"docstatus": 1, "workflow_state": ["!=", "Production Concluded"]}, filters),
        fields=["name", "customer", "delivery_date", "workflow_state"],
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
        }, items, work_orders))
    return branches


def get_material_request_branches(filters):
    requests = frappe.get_all(
        "Material Request",
        filters=apply_source_filters({
            "docstatus": 1, "material_request_type": "Manufacture",
            "status": ["not in", ["Stopped", "Cancelled"]],
            "workflow_state": ["!=", "Production Concluded"],
        }, filters),
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


def build_branch(reference, items, work_orders_by_item):
    """Apply the same coverage, completion and bypass rules to each demand source."""
    item_rows = []
    total_qty = 0
    total_produced = 0
    has_bypass = 0

    eligible_item_count = 0
    fully_planned_item_count = 0

    for item in items:
        eligible_item_count += 1

        wos = work_orders_by_item.get(item.name, [])

        l3_rows = []
        item_produced_acc = 0
        item_planned_acc = 0

        for wo in wos:
            wo_qty = wo.qty or 0
            item_planned_acc += wo_qty
            wo_produced = wo_qty if wo.custom_bypass else (wo.produced_qty or 0)
            item_produced_acc += wo_produced

            if wo.custom_bypass:
                has_bypass = 1

            l3_rows.append({
                "label_name": wo.name,
                "reference_doctype": "Work Order",
                "reference_name": wo.name,
                "wo_status": wo.status,
                "produced_qty": wo.produced_qty,
                "qty": wo_qty,
                "completion_rate": f"{int(min((wo_produced / wo_qty * 100), 100)) if wo_qty > 0 else 0}%",
                "is_bypass": wo.custom_bypass,
                "indent": 2
            })

        if item_planned_acc >= item.qty:
            fully_planned_item_count += 1

        planning_status = "ok"
        if not wos:
            planning_status = "orphan"
        elif item_planned_acc < item.qty:
            planning_status = "shortfall"

        l2_perc = min((item_produced_acc / item.qty * 100), 100) if item.qty > 0 else 0
        total_qty += item.qty
        total_produced += min(item_produced_acc, item.qty)

        item_rows.append({
            "label_name": f"{item.item_code}: {item.item_name}",
            "qty": f"{int(item_planned_acc)} / {int(item.qty)}",
            # Keep fractional quantities for sorting; the display is rounded.
            "_sort_qty": item_planned_acc / item.qty if item.qty > 0 else None,
            "produced_qty": item_produced_acc,
            "completion_rate": f"{int(l2_perc)}%",
            "is_bypass": 1 if any(wo.get('is_bypass') for wo in l3_rows) else 0,
            "planning_status": planning_status,
            "indent": 1
        })
        item_rows.extend(l3_rows)

    completion_percent = min((total_produced / total_qty * 100), 100) if total_qty > 0 else 0
    incomplete_coverage = 1 if fully_planned_item_count != eligible_item_count else 0

    data = [{
        **reference,
        "completion_rate": f"{int(completion_percent)}%",
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
        {"label": _("Reference (SO / MR / Item / WO)"), "fieldname": "label_name", "fieldtype": "Data", "width": 400},
        {"label": _("Target Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": _("Stage"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 160},
        {"label": _("Completion"), "fieldname": "completion_rate", "fieldtype": "Data", "width": 110},
        {"label": _("Coverage (L0) / Plan (L1)"), "fieldname": "qty", "fieldtype": "Data", "width": 150},
        {"label": _("WO Status"), "fieldname": "wo_status", "fieldtype": "Data", "width": 130},
        {"label": _("Produced"), "fieldname": "produced_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Bypass"), "fieldname": "is_bypass", "fieldtype": "Check", "width": 80},
    ]
