
# disabled for now
import frappe
from frappe import _

# 1) Material Receipt for CLIENT - ITEM 1

def create_batches_on_material_receipt(doc, method):
    if not doc.get("custom_batched") or doc.purpose != "Material Receipt":
        return

    sales_order = doc.custom_sales_order
    if not sales_order:
        frappe.throw(_("Stock Entry must reference a Sales Order"))

    errors = []
    for d in doc.items:
        if d.item_code != "CLIENT - ITEM 1":
            continue

        details = (d.get("custom_item_details") or "").strip()
        if not details:
            errors.append(_("Row {idx}: Missing Item Details").format(idx=d.idx))
            continue

        batch_name = f"{sales_order} : {details}"[:100]
        if not frappe.db.exists("Batch", batch_name):
            try:
                frappe.get_doc({
                    "doctype": "Batch",
                    "batch_id": batch_name,
                    "item": d.item_code,
                    "fifo_date": doc.posting_date
                }).insert(ignore_permissions=True)
            except frappe.DuplicateEntryError:
                frappe.db.rollback()

        d.batch_no = batch_name

    if errors:
        frappe.throw("<br>".join(errors))


# 2) Transfer for Manufacture for CLIENT - ITEM 1

def assign_batches_for_manufacture(doc, method):
    if not doc.get("custom_batched") or doc.purpose != "Material Transfer for Manufacture":
        return

    if not doc.work_order:
        frappe.throw(_("Stock Entry must reference a Work Order"))

    wo = frappe.get_doc("Work Order", doc.work_order)
    so = wo.sales_order
    if not so:
        frappe.throw(_("Work Order must be linked to a Sales Order"))

    for d in doc.items:
        if d.item_code != "CLIENT - ITEM 1":
            continue

        details = (d.get("custom_item_details") or "").strip()
        if not details:
            frappe.throw(_("Row {idx}: Missing Item Details").format(idx=d.idx))

        batch_name = f"{so} : {details}"[:100]
        if not frappe.db.exists("Batch", batch_name):
            try:
                frappe.get_doc({
                    "doctype": "Batch",
                    "batch_id": batch_name,
                    "item": d.item_code,
                    "fifo_date": doc.posting_date
                }).insert(ignore_permissions=True)
            except frappe.DuplicateEntryError:
                frappe.db.rollback()

        d.batch_no = batch_name


# def create_batches_on_update(doc, method):
#     # """
#     # Automatically create and assign Batch records for Stock Entry items,
#     # respecting your rules:
#     #   1. Use only the `item_specifics` custom field.
#     #   2. Assume text‐only content—no extra sanitization needed.
#     #   3. Enforce that the linked Material Request comes from a Sales Order.
#     #   4. Catch race‐condition on batch creation (DuplicateEntryError).
#     #   5. Require that each Item’s Item Group be a direct child of “BASE PRODUCTS”.
#     #   6. If an Item master has `has_batch == False`, try toggling it; if that fails, throw.
#     #   7. Aggregate all row‐level errors and report them together.
#     # """

#     # Only run if the custom checkbox is checked
#     if not doc.get("custom_create_batches"):
#         return


#     # --- A) Ensure linked Material Request → Sales Order ---
    
#     sales_order = doc.custom_sales_order
#     # ensure it really is a Sales Order MR
#     if not sales_order:
#         frappe.throw(_("Stock Entry must reference a Sales Order"))

#     # --- B) Fetch “BASE PRODUCTS” once and clear cache for stability ---
#     frappe.clear_cache(doctype="Item Group")
#     base_bounds = frappe.db.get_value("Item Group", "BASE PRODUCTS", ["lft", "rgt"])
#     if not base_bounds:
#         frappe.throw(_("Item Group 'BASE PRODUCTS' not found"))
#     base_lft, base_rgt = base_bounds

#     errors = []

#     for d in doc.items:
#         # 1) Item Group must be a direct child of BASE PRODUCTS
#         ig = frappe.db.get_value("Item", d.item_code, "item_group")
#         ig_bounds = frappe.db.get_value("Item Group", ig, ["lft", "rgt"])
#         if not ig_bounds or not (base_lft < ig_bounds[0] and ig_bounds[1] < base_rgt):
#             errors.append(
#                 _("Row {idx}: Item '{item}' belongs to group '{grp}', which is not under 'BASE PRODUCTS'")
#                 .format(idx=d.idx, item=d.item_code, grp=ig)
#             )

#         # 3) Must have item_specifics filled
#         details = (d.get("custom_item_specifics") or "").strip()
#         if not details:
#             errors.append(
#                 _("Row {idx}: Missing Item Specifics, required to name the Batch")
#                 .format(idx=d.idx)
#             )
#             # skip name/creation for this row
#             continue

#         # 4) Build batch name
#         batch_name = f"{sales_order} : {details}"
#         # enforce 100-char limit
#         if len(batch_name) > 100:
#             batch_name = batch_name[:100]

#         # 5) Create Batch if not exists, catching duplicates
#         if not frappe.db.exists("Batch", batch_name):
#             try:
#                 frappe.get_doc({
#                     "doctype": "Batch",
#                     "batch_id": batch_name,
#                     "item": d.item_code,
#                     "fifo_date": doc.posting_date
#                 }).insert(ignore_permissions=True)
#             except frappe.DuplicateEntryError:
#                 # another process created it first—safe to continue
#                 frappe.db.rollback()

#         # 6) Assign batch to the Stock Entry row
#         d.batch_no = batch_name

#     # 7) If any errors accumulated, throw them all at once
#     if errors:
#         frappe.throw("<br>".join(errors))
