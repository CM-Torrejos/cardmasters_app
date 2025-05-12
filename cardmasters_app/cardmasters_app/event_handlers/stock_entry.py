# this is to strictly update stock entry on item manufacture
import frappe
from frappe import _


def inherit_item_details_on_insert(doc, method):
    # Only for Transfer for Manufacture with batching
    # if doc.purpose != "Material Transfer for Manufacture" or not doc.custom_batched:
    #     return
    # if not doc.work_order:
    #     return

    # Fetch Work Order and map item to its custom details
    wo = frappe.get_doc("Work Order", doc.work_order)
    details_map = {
        r.item_code: (r.get("custom_item_details") or "").strip()
        for r in wo.required_items
    }

    for d in doc.items:
        detail = details_map.get(d.item_code)
        if detail:
            d.custom_item_details = detail