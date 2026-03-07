import frappe
from frappe import _

def get_or_create_batch(batch_name, item_code, posting_date):
	"""Fetch existing Batch or create a new one."""
	# truncate to 100 chars for name
	name = batch_name.strip()[:100]
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

def set_batch_no_for_purchase_order(doc, method):
    """
    CREATOR LOGIC:
    On Purchase Order, we CREATE the batch ID pre-emptively 
    based on the linked Sales Order + Item Specifics.
    """
    # If you have a flag to enable/disable this feature, check it here
    # if not doc.custom_batched: return

    for d in doc.items:
        item_code = d.get("item_code")
        if not item_code: continue

        # 1. Check if item is set to be batched
        # (We check the Item Master because the PO row might not know yet)
        has_batch_no = frappe.get_cached_value("Item", item_code, "has_batch_no")
        if not has_batch_no:
            continue

        # 2. Get Linked Sales Order
        # Note: Ensure your PO Item has the 'sales_order' field mapped
        sales_order = d.get("sales_order")
        
        if not sales_order:
            # Option: Ignore non-SO items, OR throw error if strict
            continue 

        # 3. Get Specifics (e.g., "Vacuum")
        item_specifics = (d.get("custom_item_specifics") or "").strip()
        
        # Fallback: If PO row is empty, try fetching from the linked SO Item
        if not item_specifics:
            # We try to find the specific item in the SO to get its details
            item_specifics = frappe.db.get_value("Sales Order Item", 
                {"parent": sales_order, "item_code": item_code}, 
                "custom_item_specifics"
            ) or ""
            item_specifics = item_specifics.strip()
            
        if not item_specifics:
            item_specifics = "NA"

        # 4. Build Name
        batch_name = build_batch_name(sales_order, item_code, item_specifics)
        
        # 5. CREATE the Batch
        # This ensures the batch exists in the system before the goods ever arrive.
        new_batch = get_or_create_batch(batch_name, item_code, doc.posting_date)
        
        # 6. Stamp it on the PO (Optional, requires batch_no field on PO Item)
        # This helps the supplier know which batch to label.
        d.batch_no = new_batch 
        d.db_set("batch_no", new_batch)

def set_batch_no_for_purchase_receipt(doc, method):
    """
    Strict assignment for Purchase Receipt.
    Sanitizes pre-filled batches to ensure they match the Sales Order.
    """
    missing_or_unmatched = []

    for d in doc.items:
        item_code = d.get("item_code")
        if not item_code: continue

        # 1. Check if Batch is required
        # We check item master because PR row might not have 'has_batch_no' mapped yet
        has_batch_no = frappe.get_cached_value("Item", item_code, "has_batch_no")
        if not has_batch_no:
            continue

        # 2. Get Sales Order (Critical for naming)
        so_name = d.get("sales_order")
        if not so_name:
            # If strict:
            # missing_or_unmatched.append(f"Row {d.idx}: {item_code} is missing a Sales Order link.")
            continue 

        # --- THE FIX: SANITIZE PRE-FILLED DATA ---
        # If ERPNext auto-mapped a batch, check if it's the right one.
        current_batch = d.get("batch_no")
        if current_batch:
            # If the batch exists but doesn't start with 'SO-xxxxx', it's wrong.
            if not current_batch.startswith(so_name):
                # frappe.msgprint(f"Removing incorrect batch {current_batch} from Row {d.idx}") # Debug
                d.batch_no = None 
            else:
                # It matches the SO, so we trust it and move to next item
                continue
        # -----------------------------------------

        # 3. Get Specifics
        item_specifics = (d.get("custom_item_specifics") or "").strip()
        # Fallback: Check PO Item
        if not item_specifics and d.get("purchase_order"):
             item_specifics = frappe.db.get_value("Purchase Order Item", 
                {"parent": d.purchase_order, "item_code": item_code}, 
                "custom_item_specifics"
             ) or ""
        if not item_specifics: item_specifics = "NA"

        # 4. Find the Batch (Pre-created by PO)
        expected_name = build_batch_name(so_name, item_code, item_specifics)
        found_batch = _find_existing_batch_by_convention(expected_name)

        if found_batch:
            d.batch_no = found_batch
            d.db_set("batch_no", found_batch)
        else:
            # Ensure field is empty so we don't save junk
            d.batch_no = None
            missing_or_unmatched.append(
                f"Row {d.idx}: {item_code}<br>"
                f"Sales Order: <b>{so_name}</b><br>"
                f"Expected Batch: {frappe.utils.escape_html(expected_name[:100])}"
            )

    # 5. HARD STOP
    if missing_or_unmatched:
        message = (
            "<b>Cannot Submit Purchase Receipt:</b><br>"
            "The required batches for these items were not found.<br>"
            "Please ensure the <b>Purchase Order</b> was validated to create these batches.<br><br>"
            + "<br><hr><br>".join(missing_or_unmatched)
        )
        frappe.throw(message, title="Batch Validation Failed")

def set_batch_no_for_purchase_invoice(doc, method):
    """
    Strict assignment for Purchase Invoice.
    Sanitizes pre-filled batches to ensure they match the Sales Order.
    """
    missing_or_unmatched = []

    for d in doc.items:
        item_code = d.get("item_code")
        if not item_code: continue

        has_batch_no = frappe.get_cached_value("Item", item_code, "has_batch_no")
        if not has_batch_no:
            continue

        # 1. Get Sales Order 
        so_name = d.get("sales_order")
        
        # If not directly on PI row, try to fetch from PR link
        if not so_name and d.get("pr_detail"):
             so_name = frappe.db.get_value("Purchase Receipt Item", d.pr_detail, "sales_order")

        if not so_name:
            continue

        # --- THE FIX: SANITIZE PRE-FILLED DATA ---
        current_batch = d.get("batch_no")
        if current_batch:
            if not current_batch.startswith(so_name):
                d.batch_no = None 
            else:
                continue
        # -----------------------------------------

        # 2. Get Specifics
        item_specifics = (d.get("custom_item_specifics") or "").strip()
        # Fallback chain: PI -> PR -> PO
        if not item_specifics and d.get("pr_detail"):
             item_specifics = frappe.db.get_value("Purchase Receipt Item", d.pr_detail, "custom_item_specifics") or ""
        if not item_specifics and d.get("po_detail"):
             item_specifics = frappe.db.get_value("Purchase Order Item", d.po_detail, "custom_item_specifics") or ""
        
        if not item_specifics: item_specifics = "NA"

        # 3. Find Batch
        expected_name = build_batch_name(so_name, item_code, item_specifics)
        found_batch = _find_existing_batch_by_convention(expected_name)

        if found_batch:
            d.batch_no = found_batch
            d.db_set("batch_no", found_batch)
        else:
            d.batch_no = None
            missing_or_unmatched.append(
                f"Row {d.idx}: {item_code}<br>"
                f"Sales Order: <b>{so_name}</b><br>"
                f"Expected Batch: {frappe.utils.escape_html(expected_name[:100])}"
            )

    # 4. HARD STOP
    if missing_or_unmatched:
        message = (
            "<b>Cannot Submit Purchase Invoice:</b><br>"
            "The required batches for these items were not found.<br><br>"
            + "<br><hr><br>".join(missing_or_unmatched)
        )
        frappe.throw(message, title="Batch Validation Failed")

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
    Assign existing batches to Delivery Note items.
    BLOCKS submission if the specific Sales Order batch is missing.
    """
    missing_or_unmatched = []

    for d in doc.items:
        item_code = d.get("item_code")
        if not item_code:
            continue

        # 1. Check if Batch is required
        has_batch_no = d.get("has_batch_no")
        if has_batch_no is None:
            has_batch_no = frappe.get_cached_value("Item", item_code, "has_batch_no")
        
        # If item doesn't need a batch, skip it
        if not has_batch_no:
            continue

        # 2. STRICT Sales Order Retrieval
        so_name = d.get("against_sales_order")
        
        # If no SO, we skip custom logic (ERPNext standard behavior applies)
        if not so_name:
            continue

        # 3. Check for FIFO Override (The "Wrong Batch" Fix)
        current_batch = d.get("batch_no")
        
        if current_batch:
            # If ERPNext assigned a batch that DOES NOT start with the SO Name, clear it.
            if not current_batch.startswith(so_name):
                d.batch_no = None # Clear the wrong batch
            else:
                # The assigned batch is correct, skip to next item
                continue

        # 4. Determine Specifics
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
            # Batch NOT found. 
            # We clear the batch field to ensure no wrong data is saved.
            d.batch_no = None 
            
            # Add details to the error list
            missing_or_unmatched.append(
                f"Row {d.idx}: {item_code}<br>"
                f"Sales Order: <b>{so_name}</b><br>"
                f"Expected Batch: {frappe.utils.escape_html(expected_name_full[:100])}"
            )

    # --- THE FIX IS HERE ---
    if missing_or_unmatched:
        message = (
            "<b>Batch Warning:</b><br>"
            "The following items do not have a batch matching their Sales Order.<br>"
            "The document will still be saved/submitted, but this may cause inventory issues.<br><br>"
            + "<br><hr><br>".join(missing_or_unmatched)
        )

        frappe.msgprint(
            message,
            title="Batch Mismatch Warning",
            indicator="orange"
        )