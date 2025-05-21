import frappe
from frappe import _

# Helper to build or fetch batch

def _get_or_create_batch(batch_name, item_code, posting_date):
    # enforce 100-char limit
    name = batch_name[:100]
    if not frappe.db.exists("Batch", name):
        try:
            frappe.get_doc({
                "doctype": "Batch",
                "batch_id": name,
                "item": item_code,
                "fifo_date": posting_date
            }).insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            frappe.db.rollback()
    return name


def _process_batched_rows(doc, fetch_so, method):
    errors = []
    for d in doc.items:
        # only process items flagged on the Item master
        requires_batch = frappe.get_cached_value("Item", d.item_code, "custom_requires_custom_batch")
        if not requires_batch:
            continue

        # fetch sales order name via passed-in lambda or function
        so_name = fetch_so(d)
        if not so_name:
            frappe.throw(_("Row {idx}: Unable to determine linked Sales Order").format(idx=d.idx))

        details = (d.get("custom_item_specifics") or "").strip()
        if not details:
            errors.append(_("Row {idx}: Missing Item Details").format(idx=d.idx))
            continue

        batch_name = f"{so_name} : {details}"
        d.batch_no = _get_or_create_batch(batch_name, d.item_code, doc.posting_date)

    if errors:
        frappe.throw("<br>".join(errors))


# 1) Material Receipt for CLIENT items

def create_batches_on_material_receipt(doc, method):
    if not getattr(doc, "custom_batched", False) or doc.purpose != "Material Receipt":
        return

    # sales order entered by user on the Stock Entry
    fetch_so = lambda d: doc.get("custom_sales_order")
    _process_batched_rows(doc, fetch_so, method)


# 2) Transfer for Manufacture

def assign_batches_for_manufacture(doc, method):
    if not getattr(doc, "custom_batched", False) or doc.purpose != "Material Transfer for Manufacture":
        return

    if not doc.work_order:
        frappe.throw(_("Stock Entry must reference a Work Order"))
    wo = frappe.get_doc("Work Order", doc.work_order)
    fetch_so = lambda d: wo.sales_order
    _process_batched_rows(doc, fetch_so, method)


# 3) Purchase Receipt for PROCURED items

def create_batches_on_purchase_receipt(doc, method):
    if not getattr(doc, "custom_batched", False):
        return

    # derive sales order directly from each PR Item's sales_order field
    fetch_so = lambda d: d.get("sales_order") or d.get("item_code")
    _process_batched_rows(doc, fetch_so, method)


# 4) Material Consumption for Manufacture / Manufacture

def after_insert_consume(doc, method):
    # only for Manufacture entries that opted-in via custom_batched
    if not getattr(doc, "custom_batched", False) or doc.purpose != "Manufacture":
        return

    # must reference a Work Order
    if not doc.work_order:
        frappe.throw(_("Stock Entry must reference a Work Order"))

    # load the Work Order
    wo = frappe.get_doc("Work Order", doc.work_order)
    wo_spec = (wo.get("custom_item_specifics") or "").strip()

    # 1) locate the WIP‐consumption row for the production item
    wip_row = next((
        item for item in doc.items
        if item.item_code == wo.production_item
        and item.s_warehouse == wo.wip_warehouse
        and not item.t_warehouse
    ), None)
    if not wip_row:
        frappe.throw(_("Could not find the WIP consumption row for {0}").format(wo.production_item))

    # ─── Assign the WIP batch on the consumption row ───
    batch_name = f"{wo.sales_order} : {wo_spec}"
    wip_row.batch_no = _get_or_create_batch(
        batch_name,
        wip_row.item_code,
        doc.posting_date
    )

    # 2) locate the FG receipt row for the production item
    fg_row = next((
        item for item in doc.items
        if item.item_code == wo.production_item
        and item.t_warehouse == wo.fg_warehouse
        and not item.s_warehouse
    ), None)
    if not fg_row:
        frappe.throw(_("Could not find the FG receipt row for {0}").format(wo.production_item))

    # 3) copy specs and batch to FG row
    fg_row.custom_item_specifics = wo_spec
    fg_row.batch_no = wip_row.batch_no


def assign_batches_on_delivery_note(doc, method):
    # only run if the Delivery Note itself is flagged
    if not getattr(doc, "custom_batched", False):
        return

    # for each row, pull the Sales Order link (or fall back to item_code)
    fetch_so = lambda d: d.get("against_sales_order") or d.get("item_code")
    _process_batched_rows(doc, fetch_so, method)
