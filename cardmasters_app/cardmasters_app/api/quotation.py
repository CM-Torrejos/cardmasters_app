"""Quotation item updates, including Cardmasters' descriptive fields."""

import math

import frappe
from frappe import _
from frappe.utils import cstr, get_datetime


@frappe.whitelist()
def update_details(quotation, items, modified):
    from erpnext.controllers.accounts_controller import update_child_qty_rate

    doc = frappe.get_doc("Quotation", quotation, for_update=True)
    doc.check_permission("write")
    if doc.docstatus != 1 or doc.status in ("Lost", "Ordered", "Cancelled"):
        frappe.throw(_("Only submitted, open Quotations can be updated."))
    if not modified or get_datetime(modified) != get_datetime(doc.modified):
        frappe.throw(_("This Quotation has changed. Reload it before updating details."),
                     frappe.TimestampMismatchError)

    data = frappe.parse_json(items)
    if not isinstance(data, list) or not data or any(not isinstance(row, dict) for row in data):
        frappe.throw(_("Provide the Quotation items to update."))
    existing = {row.name: row for row in doc.items}
    names = [row["docname"] for row in data if row.get("docname")]
    if len(set(names)) != len(names) or not set(names).issubset(existing):
        frappe.throw(_("An item is duplicated or does not belong to this Quotation. Reload the document."))
    for values in data:
        if not values.get("item_code"):
            frappe.throw(_("Item Code is required for every row."))
        if values.get("docname") and values["item_code"] != existing[values["docname"]].item_code:
            frappe.throw(_("Item Code cannot be changed on an existing row. Add a new row instead."))
        for field in ("qty", "rate", "conversion_factor"):
            try:
                value = float(values.get(field))
            except (TypeError, ValueError):
                value = math.nan
            if not math.isfinite(value) or (value <= 0 if field != "rate" else value < 0):
                frappe.throw(_("{0} must be a valid {1} number.").format(
                    field, _("non-negative") if field == "rate" else _("positive")))
        if not values.get("uom"):
            frappe.throw(_("UOM is required for every row."))

    # Core enforces workflow/permissions and ordered-item restrictions, and recalculates totals.
    update_child_qty_rate("Quotation", frappe.as_json(data), quotation, "items")
    doc.reload()
    by_name = {row.name: row for row in doc.items}
    # Core appends new rows in request order; item codes need not be unique.
    added = iter(row for row in doc.items if row.name not in existing)
    for values in data:
        row = by_name[values["docname"]] if values.get("docname") else next(added)
        if "custom_particulars" in values:
            row.custom_particulars = cstr(values["custom_particulars"]).strip()
    doc.flags.ignore_validate_update_after_submit = True
    doc.save()
    return {"updated": True}
