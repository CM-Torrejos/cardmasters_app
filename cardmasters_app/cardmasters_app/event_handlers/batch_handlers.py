import frappe
from frappe import _

# Helper to build or fetch batch

def _get_or_create_batch(batch_name, item_code, posting_date):
    """Fetch existing Batch or create a new one."""
    # truncate to 100 chars for name
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


def _build_batch_name(so_name, item_code, item_specifics):
    """
    Construct batch name in the format:
        SO Name - Item Code:Item Specifics
    """
    specifics = item_specifics or ""
    return f"{so_name} - {item_code}:{specifics}"


def _process_batched_rows(doc, fetch_so, method, create_batches=True):
    """
    Loops through doc.items. For each item:
    - Determines SO (or falls back to item_code)
    - Builds batch name with specifics
    - Creates or fetches based on create_batches flag
    """
    for d in doc.items:
        so_name = fetch_so(d)
        if not so_name:
            frappe.throw(_("Row {idx}: Unable to determine linked Sales Order").format(idx=d.idx))

        # pull item specifics field (adjust field name if different)
        specifics = d.get("item_specifics") or ""
        batch_name = _build_batch_name(so_name, d.item_code, specifics)

        if create_batches:
            d.batch_no = _get_or_create_batch(batch_name, d.item_code, doc.posting_date)
        else:
            name = batch_name[:100]
            if not frappe.db.exists("Batch", name):
                frappe.throw(_("Batch {0} does not exist").format(name))
            d.batch_no = name


def create_batches_on_purchase_receipt(doc, method):
    if not getattr(doc, "custom_batched", False):
        return

    # Sales Order field on each item, fallback to item_code
    fetch_so = lambda d: d.get("sales_order") or d.get("item_code")
    _process_batched_rows(doc, fetch_so, method, create_batches=True)


def after_insert_consume(doc, method):
    if not getattr(doc, "custom_batched", False) or doc.purpose != "Manufacture":
        return

    if not doc.work_order:
        frappe.throw(_("Stock Entry must reference a Work Order"))

    wo = frappe.get_doc("Work Order", doc.work_order)

    # find the FG receipt row (no source warehouse)
    fg_row = next(
        (item for item in doc.items
         if item.item_code == wo.production_item
         and not item.s_warehouse),
        None
    )
    if not fg_row:
        frappe.throw(_("Could not find the FG receipt row for {0}").format(wo.production_item))

    so = wo.sales_order or fg_row.item_code
    specifics = fg_row.get("item_specifics") or ""
    batch_name = _build_batch_name(so, fg_row.item_code, specifics)
    fg_row.batch_no = _get_or_create_batch(batch_name, fg_row.item_code, doc.posting_date)


def assign_batches_on_delivery_note(doc, method):
    if not getattr(doc, "custom_batched", False):
        return

    fetch_so = lambda d: d.get("against_sales_order") or d.get("item_code")
    _process_batched_rows(doc, fetch_so, method, create_batches=False)
