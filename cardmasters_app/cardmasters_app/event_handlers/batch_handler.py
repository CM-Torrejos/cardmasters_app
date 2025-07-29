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

def set_batch_no_for_purchase_receipt(doc, method):
	if not doc.custom_batched == 1:
		return

	for item in doc.items:
		if not item.has_batch_no:
			return

		item_group = frappe.db.get_value("Item", item_group, "item_group")

		# if item_group == "Expense Items"
		
		sales_order = item.get("sales_order")
		item_code = item.get("item_code")
		item_specifics = item.get("custom_item_specifics")

		# RMGEN can only be MR:Purchase request. If we are receiving one without a sales order, then its a general restock
		# General restocks are not allowed for RMGEN. 
		if item_code == "RMGEN" and sales_order == None:
			frappe.throw(_("Row {idx}: This row does not have a sales order.\
			 Receiving items for general restocking (as oppose to ad hoc SO \
			 purchases) must have the item registered first.").format(idx=d.\
			 idx))

		batch_name = build_batch_name(sales_order, item_code, item_specifics)
		get_or_create_batch(batch_name, item_code, doc.posting_date)



def set_batch_no_for_fg_on_manufacture_entry(doc, method):
	frappe.msgprint("This is a debug message")
	# Do not run if "Batched" is not checked, or purpose is not Manufacture
	if doc.purpose != "Manufacture":
		return

	# Sanity check, to make sure a manufacture stock entry is not made outside a work order
	if not doc.work_order:
		frappe.throw(_("Stock Entry must reference a Work Order"))

	# Find the finished good
	frappe.msgprint("This is a debug message")
	wo = frappe.get_doc("Work Order", doc.work_order)
	wo_spec = (wo.get("custom_item_specifics") or "").strip()
	
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
	batch_name = build_batch_name(sales_order_ref,  item_code_ref, item_specifics_ref)
	
	# Assign the batch_no field of the line item to its batch (or create one then assign)
	fg_row.batch_no = get_or_create_batch(batch_name, fg_row.item_code, doc.posting_date)
	fg_row.db_set("batch_no", fg_row.batch_no)  # Ensures it's saved
	

	# We can perhaps find the raw material soon as well
	# but, the requirements are complex (multiple RMGENs, fetching the right RMGEN)
	# Manual assigning of batches for now

# only finished goods get delivered 
# _on_delivery_note{

# }

def set_batch_no_for_delivery_note(doc, method):
	for item in doc.items:
		if not item.has_batch_no:
			return

		sales_order = item.get("sales_order")
		item_specifics_ref = fg_row.get("custom_item_specifics") or "NA"
		item_code = item.get("item_code")

		batch_name = build_batch_name(first_ref, second_ref, third_ref)
		get_or_create_batch(batch_name, item_code, doc.posting_date)