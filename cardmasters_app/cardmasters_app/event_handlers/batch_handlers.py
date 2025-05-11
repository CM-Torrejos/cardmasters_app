import frappe
from frappe import _

# This module assumes you've added two custom fields:
# 1. On Stock Entry and Purchase Receipt: "custom_batched" (Check)
# 2. On each item row: "custom_item_details" (Data)
# 3. On Item master: "requires_custom_batch" (Check)

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
        requires_batch = frappe.get_cached_value("Item", d.item_code, "requires_custom_batch")
        if not requires_batch:
            continue

        # fetch sales order name via passed-in lambda or function
        so_name = fetch_so(d)
        if not so_name:
            frappe.throw(_("Row {idx}: Unable to determine linked Sales Order").format(idx=d.idx))

        details = (d.get("custom_item_details") or "").strip()
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

    # derive sales order from linked Material Request
    fetch_so = lambda d: frappe.db.get_value("Material Request", d.material_request, "sales_order")
    _process_batched_rows(doc, fetch_so, method)