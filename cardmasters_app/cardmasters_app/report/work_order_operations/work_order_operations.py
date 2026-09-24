"""Independent Work Order lists grouped by operation."""

import frappe
from frappe import _


SOURCE_FIELDS = [
    "sales_order", "material_request", "custom_sales_return_reference",
    "custom_document", "custom_document_id",
]


def source_order(work_order):
    # A return can retain its original Sales Order; the return is the source.
    if work_order.get("custom_sales_return_reference"):
        return "Delivery Note", work_order["custom_sales_return_reference"]
    if work_order.get("material_request"):
        return "Material Request", work_order["material_request"]
    if work_order.get("custom_document") in ("Sales Order", "Material Request"):
        if work_order.get("custom_document_id"):
            return work_order["custom_document"], work_order["custom_document_id"]
    if work_order.get("sales_order"):
        return "Sales Order", work_order["sales_order"]
    return "", ""


def build_result(work_orders, operations):
    orders = {row["name"]: row for row in work_orders}
    groups = {}
    for operation in operations:
        if operation["parent"] in orders and operation.get("operation"):
            groups.setdefault(operation["operation"], []).append(operation)

    columns, data = [], []
    for index, (operation_name, entries) in enumerate(sorted(groups.items())):
        prefix = f"operation_{index}"
        for suffix, label, fieldtype, options, width in (
            ("source_order", _("Source Order"), "Dynamic Link", f"{prefix}_source_type", 210),
            ("work_order", _("Work Order"), "Link", "Work Order", 210),
            ("item_name", _("Item Name"), "Data", None, 200),
            ("particulars", _("Particulars"), "Text", None, 300),
            ("progress", _("Progress"), "Data", None, 130),
        ):
            columns.append({
                "fieldname": f"{prefix}_{suffix}", "label": label,
                "fieldtype": fieldtype, "options": options, "width": width,
                "operation_group": operation_name, "sortable": False, "dropdown": False,
            })
        columns.append({
            "fieldname": f"{prefix}_source_type", "label": _("Source Type"),
            "fieldtype": "Data", "hidden": 1,
        })
        for row_index, entry in enumerate(entries):
            if row_index == len(data):
                data.append({})
            work_order = orders[entry["parent"]]
            source_type, source_name = source_order(work_order)
            data[row_index].update({
                f"{prefix}_work_order": entry["parent"],
                f"{prefix}_item_name": work_order.get("item_name") or "",
                f"{prefix}_particulars": work_order.get("custom_particulars") or "",
                f"{prefix}_source_type": source_type,
                f"{prefix}_source_order": source_name,
                f"{prefix}_progress": entry.get("custom_progress") or "",
            })
    return columns, data


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = {"docstatus": ["<", 2]}
    for field in ("company", "name", "status"):
        value = filters.get("work_order" if field == "name" else field)
        if value:
            conditions[field] = value
    if filters.branch:
        branch_field = (
            "custom_production_branch"
            if filters.branch_source == "custom_production_branch"
            else "custom_for_branch"
        )
        conditions[branch_field] = filters.branch
    meta = frappe.get_meta("Work Order")
    fields = ["name", "item_name"] + [
        field for field in [*SOURCE_FIELDS, "custom_particulars"] if meta.has_field(field)
    ]
    # Apply Work Order permissions before reading any of its child rows.
    orders = frappe.get_list(
        "Work Order", filters=conditions, fields=fields,
        order_by="creation asc, name asc", limit_page_length=0,
    )
    if not orders:
        return [], []
    if not frappe.get_meta("Work Order Operation").has_field("custom_progress"):
        frappe.throw(_("Work Order Operation requires the custom_progress field."))
    operations = []
    names = [row.name for row in orders]
    for start in range(0, len(names), 500):
        child_filters = {
            "parent": ["in", names[start:start + 500]],
            "parenttype": "Work Order", "parentfield": "operations",
        }
        if filters.operation:
            # Keep older single-operation URLs/API calls working too.
            selected = filters.operation
            child_filters["operation"] = ["in", selected] if isinstance(selected, list) else selected
        if filters.progress:
            child_filters["custom_progress"] = filters.progress
        operations.extend(frappe.get_all(
            "Work Order Operation", filters=child_filters,
            fields=["parent", "operation", "custom_progress", "idx"],
            order_by="parent asc, idx asc",
        ))
    order_position = {name: index for index, name in enumerate(names)}
    operations.sort(key=lambda row: (order_position[row.parent], row.idx))
    return build_result(orders, operations)
