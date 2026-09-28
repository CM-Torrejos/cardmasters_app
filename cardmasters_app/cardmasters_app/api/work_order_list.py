"""Operation progress for the visible, permission-filtered Work Order list."""

import frappe
from frappe import _


@frappe.whitelist()
def get_operation_progress(names, filters):
    names = frappe.parse_json(names)
    filters = frappe.parse_json(filters)
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        frappe.throw(_("Invalid Work Order names."))
    if not isinstance(filters, list):
        frappe.throw(_("Invalid operation filters."))
    meta = frappe.get_meta("Work Order Operation")
    conditions = []
    for condition in filters:
        if (
            not isinstance(condition, list) or len(condition) != 4
            or condition[0] != "Work Order Operation"
            or not isinstance(condition[1], str) or not meta.has_field(condition[1])
        ):
            frappe.throw(_("Invalid operation filter."))
        conditions.append(condition)
    if not names or not conditions:
        return {}

    result = {}
    names = list(dict.fromkeys(names))
    for start in range(0, len(names), 500):
        allowed = frappe.get_list(
            "Work Order", filters={"name": ["in", names[start:start + 500]]},
            pluck="name", limit_page_length=0,
        )
        if not allowed:
            continue
        rows = frappe.get_all(
            "Work Order Operation",
            filters=[
                ["parent", "in", allowed], ["parenttype", "=", "Work Order"],
                ["parentfield", "=", "operations"], *conditions,
            ],
            fields=["parent", "operation", "custom_progress", "idx"],
            order_by="parent asc, idx asc",
        )
        for row in rows:
            result.setdefault(row.parent, []).append({
                "operation": row.operation, "progress": row.custom_progress, "idx": row.idx,
            })
    return result
