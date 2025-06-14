import frappe
from frappe import _

# Helper to build or fetch batch

def _get_or_create_batch(batch_name, item_code, posting_date):
    """Fetch existing Batch or create a new one."""
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


def _process_batched_rows(doc, fetch_so, method, create_batches=True):
    """
    Loops through doc.items. For each item:
    - Determines SO (or falls back to item_code)
    - Uses _get_or_create_batch when create_batches=True
    - Otherwise only fetches an existing Batch (throws if not found)
    """
    for d in doc.items:
        # determine the Sales Order (or fallback to item_code)
        so_name = fetch_so(d)
        if not so_name:
            frappe.throw(_("Row {idx}: Unable to determine linked Sales Order").format(idx=d.idx))

        batch_name = f"{so_name} : {d.item_code}"

        if create_batches:
            d.batch_no = _get_or_create_batch(batch_name, d.item_code, doc.posting_date)
        else:
            # only fetch, do not create
            name = batch_name[:100]
            if not frappe.db.exists("Batch", name):
                frappe.throw(_("Batch {0} does not exist").format(name))
            d.batch_no = name


def create_batches_on_purchase_receipt(doc, method):
    if not getattr(doc, "custom_batched", False):
        return

    # for Purchase Receipt, sales_order is on each item
    fetch_so = lambda d: d.get("sales_order") or d.get("item_code")
    # allow create
    _process_batched_rows(doc, fetch_so, method, create_batches=True)


def after_insert_consume(doc, method):
    # only for Manufacture consumption entries when custom_batched is set
    if not getattr(doc, "custom_batched", False) or doc.purpose != "Manufacture":
        return

    if not doc.work_order:
        frappe.throw(_("Stock Entry must reference a Work Order"))

    wo = frappe.get_doc("Work Order", doc.work_order)

    # find the FG receipt row
    fg_row = next((
        item for item in doc.items
        if item.item_code == wo.production_item
        and not item.s_warehouse
    ), None)
    if not fg_row:
        frappe.throw(_("Could not find the FG receipt row for {0}").format(wo.production_item))

    so = wo.sales_order or fg_row.item_code
    batch_name = f"{so} : {fg_row.item_code}"
    # allow create
    fg_row.batch_no = _get_or_create_batch(batch_name, fg_row.item_code, doc.posting_date)


def assign_batches_on_delivery_note(doc, method):
    if not getattr(doc, "custom_batched", False):
        return

    fetch_so = lambda d: d.get("against_sales_order") or d.get("item_code")
    # only assign existing batches (no creation)
    _process_batched_rows(doc, fetch_so, method, create_batches=False)
