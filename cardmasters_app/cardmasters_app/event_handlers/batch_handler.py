import frappe
from frappe import _

def get_or_create_batch(batch_name, item_code, posting_date):
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

def build_batch_name(so_name, item_code, item_specifics):
	return f"{so_name} - {item_code}:{item_specifics}"

# --- NEW: shared finder for existing batches by our convention ---
def _find_existing_batch_by_convention(batch_name: str) -> str | None:
	"""Return Batch.name if a batch exists matching our convention (by name or batch_id)."""
	name = (batch_name or "")[:100]
	if not name:
		return None

	# 1) Direct name match
	if frappe.db.exists("Batch", name):
		return name

	# 2) batch_id match -> get the actual document name
	found = frappe.db.get_value("Batch", {"batch_id": name}, "name")
	return found

def set_batch_no_for_purchase_receipt(doc, method):
	if not doc.custom_batched == 1:
		return

	for d in doc.items:
		if not d.has_batch_no:
			continue

		# NOTE: original line had a bug using undefined variable 'item_group'
		# item_group = frappe.db.get_value("Item", d.item_code, "item_group")

		sales_order = d.get("sales_order")
		item_code = d.get("item_code")
		item_specifics = d.get("custom_item_specifics")

		# RMGEN can only be MR:Purchase request. If we are receiving one without a sales order, then its a general restock
		# General restocks are not allowed for RMGEN. 
		if item_code == "RMGEN" and sales_order is None:
			frappe.throw(_("Row {idx}: This row does not have a sales order.\
			 Receiving items for general restocking (as oppose to ad hoc SO \
			 purchases) must have the item registered first.").format(idx=d.idx))

		batch_name = build_batch_name(sales_order, item_code, item_specifics)
		get_or_create_batch(batch_name, item_code, doc.posting_date)

def set_batch_no_for_fg_on_manufacture_entry(doc, method):
	# Do not run if "Batched" is not checked, or purpose is not Manufacture
	if doc.purpose != "Manufacture":
		return

	# Sanity check, to make sure a manufacture stock entry is not made outside a work order
	if not doc.work_order:
		frappe.throw(_("Stock Entry must reference a Work Order"))

	# Find the finished good
	wo = frappe.get_doc("Work Order", doc.work_order)
	
	fg_row = next(
		(item for item in doc.items
		 if item.item_code == wo.production_item
		 and not item.s_warehouse),
		None
	)

	if not fg_row:
		frappe.throw(_("Could not find the FG receipt row for {0}").format(wo.production_item))

	# Acquire all necessary parameters for building/assigning batch
	sales_order_ref = wo.sales_order
	item_specifics_ref = wo.get("custom_item_specifics") or "NA"
	item_code_ref = wo.production_item

	# Call the batch name builder function
	batch_name = build_batch_name(sales_order_ref, item_code_ref, item_specifics_ref)
	
	# Assign the batch_no field of the line item to its batch (or create one then assign)
	fg_row.batch_no = get_or_create_batch(batch_name, fg_row.item_code, doc.posting_date)
	fg_row.db_set("batch_no", fg_row.batch_no)  # Ensures it's saved

# --- FIXED: Delivery Note now follows the same convention and auto-fills if found ---
def set_batch_no_for_delivery_note(doc, method):
    """
    Force strict Sales Order batch mapping. 
    Overrides ERPNext FIFO if it picked a batch from a different Sales Order.
    """
    missing_or_unmatched = []

    for d in doc.items:
        item_code = d.get("item_code")
        if not item_code:
            continue

        # 1. Check if Item is batched
        has_batch_no = d.get("has_batch_no")
        if has_batch_no is None:
            has_batch_no = frappe.get_cached_value("Item", item_code, "has_batch_no")
        
        if not has_batch_no:
            continue

        # 2. Get the STRICT Sales Order (No fallbacks)
        so_name = d.get("against_sales_order")
        
        # If this line has no SO, we cannot enforce SO-specific logic. 
        # We leave whatever ERPNext did (or didn't do) alone.
        if not so_name:
            continue

        # --- CRITICAL FIX START ---
        # 3. Check if a batch is already assigned
        current_batch = d.get("batch_no")
        
        if current_batch:
            # If a batch is assigned, check if it belongs to THIS Sales Order.
            # We check if the Batch Name starts with the SO Name.
            # NOTE: This assumes your batch naming convention always starts with the SO Name.
            if not current_batch.startswith(so_name):
                frappe.msgprint(
                    f"Row {d.idx}: Overriding standard FIFO batch {current_batch} "
                    f"because it does not match Sales Order {so_name}.",
                    alert=True
                )
                d.batch_no = None # Clear it so we can find the right one below
            else:
                # The assigned batch is correct (matches this SO), so we skip.
                continue
        # --- CRITICAL FIX END ---

        # 4. Fetch Specifics
        item_specifics = (d.get("custom_item_specifics") or "").strip()
        if not item_specifics:
            so_detail = d.get("so_detail")
            if so_detail:
                item_specifics = (frappe.db.get_value("Sales Order Item", so_detail, "custom_item_specifics") or "").strip()
        
        if not item_specifics:
            item_specifics = "NA"

        # 5. Build Expected Name & Search
        expected_name_full = build_batch_name(so_name, item_code, item_specifics)
        found_batch = _find_existing_batch_by_convention(expected_name_full)

        if found_batch:
            d.batch_no = found_batch
            d.db_set("batch_no", found_batch)
        else:
            missing_or_unmatched.append(
                f"Row {d.idx}: {item_code}<br>"
                f"Target SO: <b>{so_name}</b><br>"
                f"Expected Batch: {frappe.utils.escape_html(expected_name_full[:100])}"
            )

    if missing_or_unmatched:
        # Optional: Only show this if you want to BLOCK submission when batch is missing.
        # If you want to allow manual selection of other batches, remove the msgprint.
        message = (
            "<b>Batch Mismatch / Not Found:</b><br>"
            "The system attempted to find a batch matching the Sales Order but failed.<br><br>"
            + "<br><hr><br>".join(missing_or_unmatched)
        )
        frappe.msgprint(msg=message, title="Batch Logic Check", indicator="orange")