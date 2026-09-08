"""Controlled updates to items on submitted Material Requests."""

import math
from html import escape

import frappe
from frappe import _
from frappe.model.delete_doc import check_if_doc_is_dynamically_linked, check_if_doc_is_linked
from frappe.model.workflow import get_workflow_name
from frappe.utils import cint, cstr, flt, get_datetime, getdate, sbool


EDITABLE_FIELDS = (
    "qty", "rate", "uom", "conversion_factor", "schedule_date",
    "custom_item_specifics", "custom_particulars",
)


def update_material_request_details(material_request, items, modified, confirm_work_orders=False):
    doc = frappe.get_doc("Material Request", material_request, for_update=True)
    doc.check_permission("write")
    if doc.docstatus != 1 or doc.status in ("Stopped", "Cancelled"):
        frappe.throw(_("Only submitted, active Material Requests can be updated."))
    if not modified or get_datetime(modified) != get_datetime(doc.modified):
        frappe.throw(_("This Material Request has changed. Reload it before updating details."),
                     frappe.TimestampMismatchError)
    _check_workflow_permission(doc)

    data = frappe.parse_json(items)
    if not isinstance(data, list) or not data:
        frappe.throw(_("Provide the Material Request items to update."))
    existing = {row.name: row for row in doc.items}
    if any(not isinstance(row, dict) for row in data):
        frappe.throw(_("Invalid item data."))
    names = [row["docname"] for row in data if row.get("docname")]
    if len(set(names)) != len(names) or not set(names).issubset(existing):
        frappe.throw(_("An item is duplicated or does not belong to this Material Request. Reload the document."))
    removed = [row for row in doc.items if row.name not in names]
    for row in removed:
        _validate_row_removal(doc, row)
    has_new_rows = any(not row.get("docname") for row in data)
    if has_new_rows:
        doc.check_permission("create")
    for row in removed:
        doc.remove(row)

    changes = []
    quantity_changed = bool(removed or has_new_rows)
    rate_changed = False
    for values in data:
        row = existing[values["docname"]] if values.get("docname") else _append_item(doc, values)
        if values.get("item_code", row.item_code) != row.item_code:
            frappe.throw(_("Row {0}: Item Code cannot be changed after submission.").format(row.idx))
        before = {field: row.get(field) for field in EDITABLE_FIELDS}
        for field in EDITABLE_FIELDS:
            if field in values:
                row.set(field, values[field])
        for field in ("qty", "rate", "conversion_factor"):
            try:
                value = float(row.get(field))
            except (TypeError, ValueError):
                value = math.nan
            if not math.isfinite(value) or (value <= 0 if field != "rate" else value < 0):
                frappe.throw(_("Row {0}: {1} must be a valid {2} number.").format(
                    row.idx, field, _("non-negative") if field == "rate" else _("positive")))
            row.set(field, flt(value, row.precision(field)))
        if row.qty <= 0 or row.conversion_factor <= 0:
            frappe.throw(_("Row {0}: Quantity and conversion factor must be greater than zero.").format(row.idx))
        if not row.uom or not row.schedule_date:
            frappe.throw(_("Row {0}: UOM and Required By are required.").format(row.idx))
        row.schedule_date = getdate(row.schedule_date)
        for field in ("custom_item_specifics", "custom_particulars"):
            row.set(field, cstr(row.get(field)).strip())

        stock_qty = flt(row.qty * row.conversion_factor, row.precision("stock_qty"))
        row_quantity_changed = any(row.get(f) != before[f] for f in ("qty", "uom", "conversion_factor"))
        if row_quantity_changed and stock_qty < max(flt(row.ordered_qty), flt(row.received_qty)):
            frappe.throw(_("Row {0}: Quantity cannot be less than the quantity already ordered, received, or transferred ({1} {2}).").format(
                row.idx, max(flt(row.ordered_qty), flt(row.received_qty)), row.stock_uom))
        row.stock_qty = stock_qty
        row.amount = flt(row.qty * row.rate, row.precision("amount"))
        if row.rate != before["rate"]:
            row.price_list_rate = row.rate
            rate_changed = True
        quantity_changed |= row_quantity_changed
        changed = [field for field in EDITABLE_FIELDS if cstr(before[field] or "") != cstr(row.get(field) or "")]
        if changed and values.get("docname"):
            changes.append((row, before, changed))

    warning = _work_order_warning(doc, changes)
    if warning and not cint(sbool(confirm_work_orders)):
        return {"confirmation_required": True, "message": warning}
    if not changes and not quantity_changed:
        return {"updated": False}

    # Submitted saves do not run the regular validate event automatically.
    doc.run_method("validate")
    doc.flags.ignore_validate_update_after_submit = True
    doc.save()
    if quantity_changed:
        if removed:
            _refresh_removed_row_totals(doc, removed)
        doc.update_requested_qty_in_production_plan()
        doc.update_requested_qty()
        if doc.material_request_type == "Purchase":
            doc.update_prevdoc_status()
        else:
            doc.update_completed_qty()
        for target, percent in (("ordered_qty", "per_ordered"), ("received_qty", "per_received")):
            doc._update_percent_field({
                "target_dt": "Material Request Item", "target_parent_dt": "Material Request",
                "target_parent_field": percent, "target_ref_field": "stock_qty",
                "target_field": target, "name": doc.name,
            })
    if (quantity_changed or rate_changed) and doc.material_request_type == "Purchase":
        doc.validate_budget()
    return {"updated": True}


def _append_item(doc, values):
    from erpnext.stock.get_item_details import get_item_details

    if not values.get("item_code"):
        frappe.throw(_("Item Code is required for new rows."))
    details = get_item_details({
        "doctype": doc.doctype, "name": doc.name, "company": doc.company,
        "material_request_type": doc.material_request_type,
        "transaction_date": doc.transaction_date, "item_code": values["item_code"],
        "qty": values.get("qty", 1), "uom": values.get("uom"),
        "set_warehouse": doc.set_warehouse, "warehouse": values.get("warehouse"),
        "buying_price_list": doc.buying_price_list,
    }, doc=doc)
    row = doc.append("items", details)
    row.item_code = values["item_code"]
    row.qty = values.get("qty", 1)
    row.rate = flt(details.get("rate"))
    row.schedule_date = values.get("schedule_date") or doc.schedule_date
    row.warehouse = values.get("warehouse") or doc.set_warehouse or row.warehouse
    row.from_warehouse = values.get("from_warehouse") or doc.set_from_warehouse
    row.ordered_qty = row.received_qty = 0
    return row


def _validate_row_removal(doc, row):
    if flt(row.ordered_qty) or flt(row.received_qty):
        frappe.throw(_("Row {0}: Cannot delete an item that has already been ordered, received, or transferred.").format(row.idx))
    # Several ERPNext row references are Data fields, so generic Link checks alone miss them.
    reference_doctypes = (
        "Work Order", "Purchase Order Item", "Purchase Receipt Item", "Purchase Invoice Item",
        "Stock Entry Detail", "Pick List Item", "Request for Quotation Item",
        "Supplier Quotation Item", "Production Plan Item", "Sales Order Item",
        "Delivery Note Item", "Subcontracting Order Item", "Subcontracting Order Service Item",
    )
    for doctype in reference_doctypes:
        if frappe.db.exists(doctype, {"material_request_item": row.name, "docstatus": ["<", 2]}):
            frappe.throw(_("Row {0}: Cannot delete this item because it is referenced by {1}.").format(row.idx, _(doctype)))
    if frappe.db.exists("Work Order", {
        "custom_document": "Material Request", "custom_document_id": doc.name,
        "custom_document_item_id": row.name, "docstatus": ["<", 2],
    }):
        frappe.throw(_("Row {0}: Cannot delete this item because it is referenced by a Work Order.").format(row.idx))
    check_if_doc_is_linked(row)
    check_if_doc_is_dynamically_linked(row)


def _refresh_removed_row_totals(doc, removed):
    # Include the deleted rows when refreshing their former warehouses and Sales Orders.
    previous = frappe.get_doc(doc.as_dict())
    previous.set("items", removed)
    previous.update_requested_qty()
    if previous.material_request_type == "Purchase":
        previous.update_prevdoc_status()
    previous.docstatus = 2
    previous.update_requested_qty_in_production_plan()


def _check_workflow_permission(doc):
    workflow_name = get_workflow_name(doc.doctype)
    if not workflow_name:
        return
    workflow = frappe.get_doc("Workflow", workflow_name)
    roles = frappe.get_roles()
    if not any(state.state == doc.get(workflow.workflow_state_field)
               and (not state.allow_edit or state.allow_edit in roles) for state in workflow.states):
        frappe.throw(_("You are not allowed to edit this Material Request in its current workflow state."),
                     frappe.PermissionError)


def _work_order_warning(doc, changes):
    messages = []
    labels = {"qty": _("Quantity"), "uom": _("UOM"), "conversion_factor": _("Conversion Factor"),
              "schedule_date": _("Required By"), "custom_item_specifics": _("Item Specifics"),
              "custom_particulars": _("Particulars")}
    for row, before, changed in changes:
        fields = [field for field in changed if field in labels]
        if not fields:
            continue
        names = set()
        for links in (
            {"material_request": doc.name, "material_request_item": row.name},
            {"custom_document": "Material Request", "custom_document_id": doc.name,
             "custom_document_item_id": row.name},
        ):
            names.update(frappe.get_all("Work Order", filters={**links, "docstatus": ["<", 2]}, pluck="name"))
        if names:
            details = "<br>".join(
                "{0}: {1} &rarr; {2}".format(escape(labels[field]), escape(cstr(before[field])),
                                             escape(cstr(row.get(field)))) for field in fields
            )
            messages.append("<b>{0}</b> — {1}<br>{2}".format(
                escape(", ".join(sorted(names))), escape(row.item_code), details))
    if messages:
        return _("These changes affect linked Work Orders. Contact their authors to update them:") + "<br><br>" + "<br><br>".join(messages) + "<br><br>" + _("Continue updating the Material Request?")
