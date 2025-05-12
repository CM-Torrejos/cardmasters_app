import frappe
from frappe import _

# 1. On Stock Entry and Purchase Receipt: "custom_batched" (Check)
# 2. On each item row: "custom_item_specifics" (Data)
# 3. On Item master: "custom_requires_custom_batch" (Check)

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
    if not doc.custom_batched or doc.purpose != "Material Receipt":
        return

    # sales order entered by user on the Stock Entry
    fetch_so = lambda d: doc.get("custom_sales_order")
    _process_batched_rows(doc, fetch_so, method)


# 2) Transfer for Manufacture

def assign_batches_for_manufacture(doc, method):
    if not doc.custom_batched or doc.purpose != "Material Transfer for Manufacture":
        return

    if not doc.work_order:
        frappe.throw(_("Stock Entry must reference a Work Order"))
    wo = frappe.get_doc("Work Order", doc.work_order)
    fetch_so = lambda d: wo.sales_order
    _process_batched_rows(doc, fetch_so, method)


# 3) Purchase Receipt for PROCURED items

def create_batches_on_purchase_receipt(doc, method):
    if not doc.custom_batched:
        return

    # derive sales order directly from each PR Item's sales_order field
    fetch_so = lambda d: d.get("sales_order")
    _process_batched_rows(doc, fetch_so, method)


# 4) Material Consumption for Manufacture / Manufacture
import frappe
from frappe import _

def after_insert_consume(doc, method):
    """
    On validate of a Manufacture Stock Entry, for the “finished good” row:
      a) pull custom_item_specifics from the Work Order header
      b) pull batch_no from the consumption (WIP) row
    """
    # only for Manufacture entries that opted-in via custom_batched
    if not getattr(doc, "custom_batched", False) or doc.purpose != "Manufacture":
        return

    # must reference a Work Order
    if not doc.work_order:
        frappe.throw(_("Stock Entry must reference a Work Order"))

    # load the WO
    wo = frappe.get_doc("Work Order", doc.work_order)

    # grab the WO-level details
    wo_spec = wo.get("custom_item_specifics") or ""

    # 1) locate the WIP‐consumption row for the production item
    wip_row = next((
        item for item in doc.items
        if item.item_code == wo.production_item
        and item.s_warehouse == wo.wip_warehouse
        and not item.t_warehouse  # ensure it's the “removal” line
    ), None)

    if not wip_row:
        # dump some debug info so you can see what you're actually getting
        frappe.errprint("Looking for WIP consumption in:")
        for item in doc.items:
            frappe.errprint(f"  idx {item.idx}: code={item.item_code}, s_wh={item.s_warehouse}, t_wh={item.t_warehouse}, qty={item.qty}, actual={item.actual_qty}")
        frappe.throw(_("Could not find the WIP consumption row for {0}").format(wo.production_item))

    # 2) find the FG receipt row and apply specs + batch
    fg_row = next((
        item for item in doc.items
        if item.item_code == wo.production_item
        and item.t_warehouse == wo.fg_warehouse
        and not item.s_warehouse  # ensure it's the “addition” line
    ), None)

    if not fg_row:
        frappe.throw(_("Could not find the FG receipt row for {0}").format(wo.production_item))

    # a) copy the WO’s custom details
    fg_row.custom_item_specifics = wo_spec
    # b) use the batch from the consumption row
    fg_row.batch_no = wip_row.batch_no
