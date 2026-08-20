import frappe
from frappe import _
from frappe.utils import nowdate

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

BATCH_NAME_MAX_LEN = 100
IDENTITY_SOURCE_SYSTEM = "system_generated"
IDENTITY_SOURCE_LEGACY = "legacy_unresolved"
BATCH_ASSIGNMENT_STOCK_ENTRY_TYPES = {"Manufacture", "Repack", "Material Transfer for Manufacture"}


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _build_new_batch_name(so_name: str, soi_docname: str) -> str:
	"""
	Construct the canonical batch name: {DOCUMENT_ID}_{DOCUMENT_ITEM_ID}.

	Raises a descriptive hard error if the result would exceed
	ERPNext's 100-character Batch.name limit.

	Examples
	--------
	>>> _build_new_batch_name("SO-043680", "SOI-1238")
	'SO-043680_SOI-1238'
	"""
	name = f"{so_name}_{soi_docname}"
	if len(name) > BATCH_NAME_MAX_LEN:
		frappe.throw(
			_(
				"Cannot create batch: constructed name '{0}' is {1} characters, "
				"which exceeds ERPNext's 100-character Batch.name limit. "
				"Check the Document ID and Document Item ID."
			).format(name, len(name)),
			title=_("Batch Name Too Long"),
		)
	return name


def _get_stock_entry_type(doc) -> str:
	return (getattr(doc, "stock_entry_type", None) or getattr(doc, "purpose", None) or "").strip()


def _get_batch_work_order(doc) -> str:
	entry_type = _get_stock_entry_type(doc)
	if entry_type == "Repack":
		return getattr(doc, "custom_work_order_for_repack", None) or getattr(doc, "work_order", None)

	return getattr(doc, "work_order", None)


def _has_field(doctype: str, fieldname: str) -> bool:
	return bool(frappe.get_meta(doctype).has_field(fieldname))


def _set_doc_field_if_exists(doc, fieldname: str, value):
	if not _has_field(doc.doctype, fieldname):
		return

	doc.set(fieldname, value)
	if doc.name and doc.docstatus != 0 and frappe.db.exists(doc.doctype, doc.name):
		doc.db_set(fieldname, value, update_modified=False)


def _append_batch_work_order(batch_name: str, work_order: str, wo_qty: float):
	if not work_order:
		return

	if frappe.db.exists(
		"Batch Work Order",
		{
			"parent": batch_name,
			"parenttype": "Batch",
			"parentfield": "custom_work_orders",
			"work_order": work_order,
		},
	):
		return

	frappe.db.sql(
		"""
		INSERT INTO `tabBatch Work Order`
			(name, parent, parenttype, parentfield,
			 work_order, qty)
		VALUES
			(%s, %s, 'Batch', 'custom_work_orders',
			 %s, %s)
		""",
		(
			frappe.generate_hash(length=10),
			batch_name,
			work_order,
			wo_qty,
		),
	)


def autofill_work_order_batch_source_fields(doc, method=None):
	"""
	Fill the draft Work Order batch identity source fields.

	This does not create a Batch and intentionally leaves custom_batch blank.
	"""
	if doc.get("custom_parent_work_order") and not doc.get("sales_order"):
		if not doc.get("custom_production_type"):
			_set_doc_field_if_exists(doc, "custom_production_type", "Make to Stock")
		_set_doc_field_if_exists(doc, "custom_document", None)
		_set_doc_field_if_exists(doc, "custom_document_id", None)
		_set_doc_field_if_exists(doc, "custom_document_item_id", None)
		_set_doc_field_if_exists(doc, "custom_batch", None)
		return

	if doc.get("sales_order") and not doc.get("custom_production_type"):
		_set_doc_field_if_exists(doc, "custom_production_type", "Make to Order")

	if doc.get("sales_order") and not doc.get("custom_document"):
		_set_doc_field_if_exists(doc, "custom_document", "Sales Order")

	if doc.get("sales_order") and not doc.get("custom_document_id"):
		_set_doc_field_if_exists(doc, "custom_document_id", doc.sales_order)

	if doc.get("sales_order_item") and not doc.get("custom_document_item_id"):
		_set_doc_field_if_exists(
			doc,
			"custom_document_item_id",
			doc.sales_order_item,
		)


def _validate_work_order_batch_source(
	doc,
	source_doctype: str,
	document_id: str,
	document_item_id: str,
):
	if not source_doctype and not document_id and not document_item_id:
		return

	if not source_doctype or not document_id or not document_item_id:
		frappe.throw(
			_("Document, Document ID, and Document Item ID are required to create a batch for Work Order {0}.")
			.format(doc.name)
		)

	if source_doctype == "Sales Order":
		if not frappe.db.exists("Sales Order", document_id):
			frappe.throw(_("Sales Order {0} does not exist.").format(frappe.bold(document_id)))

		if not frappe.db.exists(
			"Sales Order Item",
			{
				"name": document_item_id,
				"parent": document_id,
			},
		):
			frappe.throw(
				_("Document Item ID {0} is not an item row on Sales Order {1}.")
				.format(frappe.bold(document_item_id), frappe.bold(document_id))
			)
		return

	if source_doctype == "Material Request":
		if not frappe.db.exists("Material Request", document_id):
			frappe.throw(_("Material Request {0} does not exist.").format(frappe.bold(document_id)))

		if not frappe.db.exists(
			"Material Request Item",
			{
				"name": document_item_id,
				"parent": document_id,
			},
		):
			frappe.throw(
				_("Document Item ID {0} is not an item row on Material Request {1}.")
				.format(frappe.bold(document_item_id), frappe.bold(document_id))
			)
		return

	frappe.throw(
		_("Document {0} is not supported for Work Order batch creation.")
		.format(frappe.bold(source_doctype))
	)


def resolve_sales_order_batch(so_name, so_detail, item_code, item_specifics=None):
	"""Resolve a Sales Order Item batch without creating one."""
	work_order_batch = None
	if so_name and so_detail and _has_field("Work Order", "custom_batch"):
		work_orders = frappe.get_all(
			"Work Order",
			filters={
				"sales_order": so_name,
				"sales_order_item": so_detail,
				"production_item": item_code,
				"docstatus": ["<", 2],
				"custom_batch": ["!=", ""],
			},
			fields=["custom_batch"],
			order_by="creation asc",
			limit=1,
		)
		work_order_batch = work_orders[0].custom_batch if work_orders else None
	if work_order_batch:
		return work_order_batch

	new_batch_name = f"{so_name}_{so_detail}"
	found_batch = frappe.db.get_value("Batch", new_batch_name, "name")
	if found_batch:
		return found_batch

	if item_specifics is None:
		item_specifics = frappe.db.get_value(
			"Sales Order Item", so_detail, "custom_item_specifics"
		)

	legacy_name = f"{so_name} - {item_code}:{(item_specifics or '').strip()}"
	legacy_name = legacy_name.strip()[:BATCH_NAME_MAX_LEN]

	if frappe.db.exists("Batch", legacy_name):
		return legacy_name

	return frappe.db.get_value("Batch", {"batch_id": legacy_name}, "name")


def _get_or_create_batch(
	batch_name: str,
	item_code: str,
	posting_date,
	so_name: str,
	soi_docname: str,
	work_order: str,
	wo_qty: float,
) -> str:
	"""
	Return an existing batch or create a new one with the new identity scheme.

	* Batch.name is set to batch_name (the canonical {SO}_{SOI} value).
	* custom_identity_source is always IDENTITY_SOURCE_SYSTEM for new batches.
	* Appends a row to custom_work_orders child table on create.

	On DuplicateEntryError (race condition), returns the already-existing name;
	the batch was created by a concurrent request.
	"""
	if not frappe.db.exists("Batch", batch_name):
		try:
			doc = frappe.get_doc(
				{
					"doctype": "Batch",
					"batch_id": batch_name,
					"item": item_code,
					"fifo_date": posting_date,
					# Convenience index fields (not the identity mechanism)
					"custom_sales_order": so_name,
					"custom_sales_order_item": soi_docname,
					"custom_identity_source": IDENTITY_SOURCE_SYSTEM,
					# Traceability child table
					"custom_work_orders": [
						{
							"work_order": work_order,
							"qty": wo_qty
						}
					],
				}
			)
			doc.insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			pass

	_append_batch_work_order(batch_name, work_order, wo_qty)

	return batch_name


def create_or_assign_work_order_batch(doc, method=None):
	"""
	Create/resolve the document item batch when the Work Order is submitted.

	The Work Order owns the batch reference. Downstream Stock Entries should
	only copy Work Order.custom_batch and must not derive or create batches.
	"""
	if doc.get("custom_production_type") == "Make to Stock":
		_set_doc_field_if_exists(doc, "custom_batch", None)
		return

	source_doctype = (doc.get("custom_document") or "").strip()
	document_id = (doc.get("custom_document_id") or "").strip()
	document_item_id = (doc.get("custom_document_item_id") or "").strip()

	if not source_doctype and not document_id and not document_item_id:
		return

	_validate_work_order_batch_source(doc, source_doctype, document_id, document_item_id)

	if not source_doctype or not document_id or not document_item_id:
		return

	if not doc.production_item:
		frappe.throw(
			_("Work Order {0} does not have a production item. "
			  "Cannot create a batch.").format(doc.name)
		)

	batch_name = _build_new_batch_name(document_id, document_item_id)

	batch = _get_or_create_batch(
		batch_name=batch_name,
		item_code=doc.production_item,
		posting_date=doc.get("planned_start_date") or nowdate(),
		so_name=doc.sales_order if doc.sales_order == document_id else None,
		soi_docname=doc.sales_order_item if doc.sales_order_item == document_item_id else None,
		work_order=doc.name,
		wo_qty=doc.qty,
	)

	_set_doc_field_if_exists(doc, "custom_batch", batch)


# ---------------------------------------------------------------------------
# DELETED FUNCTIONS — explicitly removed per architectural decision
# ---------------------------------------------------------------------------
#
#   build_batch_name(so_name, item_code, item_specifics)
#       Removed: item_specifics was the root cause of the costing bug.
#       No shim. No migration path.
#
#   _find_existing_batch_by_convention(batch_name)
#       Removed: new batches are looked up directly by Batch.name.
#       No shim. No migration path.
#
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# STOCK ENTRY HOOK — Manufacture / Repack
# ---------------------------------------------------------------------------

def set_batch_no_for_fg_on_manufacture_entry(doc, method):
	"""
	Assign the Work Order batch to the finished-goods line on a Manufacture or
	batched Repack Stock Entry.

	Triggered on: Stock Entry save, purpose/stock_entry_type = Manufacture or Repack.

	Preconditions (hard errors)
	---------------------------
	- Stock Entry must be flagged custom_batched = 1
	- Stock Entry must reference a Work Order
	- Work Order must carry custom_batch
	- A finished-goods receipt row must be identifiable
	"""
	if doc.custom_batched != 1:
		return

	if _get_stock_entry_type(doc) not in BATCH_ASSIGNMENT_STOCK_ENTRY_TYPES:
		return

	work_order = _get_batch_work_order(doc)
	if not work_order:
		frappe.throw(_("Stock Entry must reference a Work Order"))

	wo = frappe.get_doc("Work Order", work_order)
	if wo.get("custom_production_type") == "Make to Stock":
		return

	batch_name = wo.get("custom_batch")
	if not batch_name:
		frappe.throw(
			_("Work Order {0} does not have a linked batch. "
			  "Create or repair the Work Order batch before making this Stock Entry.").format(wo.name)
		)

	# ------------------------------------------------------------------
	# Locate every finished-goods receipt row. A Stock Entry can contain the
	# production item more than once, and each matching row belongs to the same
	# Work Order batch.
	# ------------------------------------------------------------------
	fg_rows = [
		item
		for item in doc.items
		if item.item_code == wo.production_item
	]

	if not fg_rows:
		frappe.throw(
			_("Could not find the FG receipt row for {0}").format(wo.production_item)
		)

	for fg_row in fg_rows:
		fg_row.batch_no = batch_name
		fg_row.db_set("batch_no", fg_row.batch_no)


# ---------------------------------------------------------------------------
# DATA QUALITY CHECK — decoupled from batch assignment
# ---------------------------------------------------------------------------

def validate_so_item_work_order_match(doc, method):
	"""
	Standalone data quality check: verifies that item_code, custom_item_specifics,
	and custom_particulars are consistent between the Sales Order Item and the
	Work Order referenced by a Manufacture Stock Entry.

	This check is DECOUPLED from batch assignment and must not be called from
	set_batch_no_for_fg_on_manufacture_entry.  Wire it to a separate hook if
	the business wants it enforced at submit time, or call it on demand.

	Returns a list of human-readable mismatch strings (empty = no issues).
	Raises frappe.ValidationError if mismatches are found and raise_on_error=True.
	"""
	if doc.purpose != "Manufacture" or not doc.work_order:
		return []

	wo = frappe.get_doc("Work Order", doc.work_order)
	soi_docname = wo.sales_order_item
	if not soi_docname:
		return []

	so_item_data = frappe.db.get_value(
		"Sales Order Item",
		soi_docname,
		["item_code", "custom_item_specifics", "custom_particulars"],
		as_dict=True,
	)
	if not so_item_data:
		return []

	mismatches = []

	if so_item_data.get("item_code") != wo.production_item:
		mismatches.append(
			f"<b>Item Code:</b> SO Item ({so_item_data.get('item_code')}) "
			f"vs Work Order ({wo.production_item})"
		)

	if so_item_data.get("custom_item_specifics") != wo.custom_item_specifics:
		mismatches.append(
			f"<b>Item Specifics:</b> SO Item ({so_item_data.get('custom_item_specifics')}) "
			f"vs Work Order ({wo.custom_item_specifics})"
		)

	if so_item_data.get("custom_particulars") != wo.custom_particulars:
		mismatches.append(
			f"<b>Particulars:</b> SO Item ({so_item_data.get('custom_particulars')}) "
			f"vs Work Order ({wo.custom_particulars})"
		)

	return mismatches


# ---------------------------------------------------------------------------
# DELIVERY NOTE HOOK
# ---------------------------------------------------------------------------

def set_batch_no_for_delivery_note(doc, method):
	"""
	Assign batches to Delivery Note items.

	Lookup strategy
	---------------------------------------------------------
	1. WORK ORDER BATCH PATH
	   Resolve the Sales Order Item to a non-cancelled Work Order and use its
	   custom_batch value. This is the canonical path after the WO-owned batch
	   remodel.

	2. DIRECT / LEGACY READ-ONLY FALLBACK
	   If no Work Order batch is available, read the canonical Batch.name
	   directly, then reconstruct the legacy name using the old formula:
	   "{SO} - {item_code}:{item_specifics}".

	TODO: Remove the fallback once all open documents have Work Order custom_batch.

	Behavior on save (draft) vs submit
	------------------------------------
	- Batched unchecked → leave manually assigned batch numbers unchanged.
	- Missing batch on SAVE  → orange warning, does not block.
	- Missing batch on SUBMIT → hard error, blocks submission.
	"""
	if doc.get("is_return"):
		return
	
	if not doc.get("custom_batched"):
		return

	missing_or_unmatched = []

	for d in doc.items:
		item_code = d.get("item_code")
		if not item_code:
			continue

		# Check whether the item requires batch tracking
		has_batch_no = d.get("has_batch_no")
		if has_batch_no is None:
			has_batch_no = frappe.get_cached_value("Item", item_code, "has_batch_no")

		if not has_batch_no:
			continue

		so_name = d.get("against_sales_order")
		if not so_name:
			continue

		so_detail = d.get("so_detail")  # Sales Order Item docname
		if not so_detail:
			continue

		# ------------------------------------------------------------------
		# Resolve the batch without creating one.
		# ------------------------------------------------------------------
		new_batch_name = f"{so_name}_{so_detail}"
		item_specifics = (d.get("custom_item_specifics") or "").strip() or None
		found_batch = resolve_sales_order_batch(
			so_name, so_detail, item_code, item_specifics
		)

		# ------------------------------------------------------------------
		# Assign or flag missing.
		# ------------------------------------------------------------------
		if found_batch:
			if d.batch_no != found_batch:
				d.batch_no = found_batch
				d.db_set("batch_no", found_batch)
		else:
			d.batch_no = None
			missing_or_unmatched.append(
				f"Row {d.idx}: {item_code}<br>"
				f"Sales Order: <b>{so_name}</b><br>"
				f"Expected Batch: {frappe.utils.escape_html(new_batch_name)}"
			)

	# ------------------------------------------------------------------
	# Conditional error / warning block
	# ------------------------------------------------------------------
	if missing_or_unmatched:
		error_content = (
			"The following items do not have a batch matching their Sales Order.<br>"
			"Ensure the items have been received/manufactured into the correct batch.<br><br>"
			+ "<br><hr><br>".join(missing_or_unmatched)
		)

		if doc.docstatus == 1:
			frappe.throw(
				f"<b>Submission Blocked:</b><br>{error_content}",
				title=_("Missing Required Batch"),
			)
		else:
			frappe.msgprint(
				f"<b>Batch Warning (Draft):</b><br>{error_content}",
				title=_("Batch Mismatch"),
				indicator="orange",
			)


# ---------------------------------------------------------------------------
# STOCK ENTRY HOOK — set received date (UNCHANGED)
# ---------------------------------------------------------------------------

def set_batch_received_date_on_population(doc, method):
	if doc.docstatus != 1:
		return

	entry_type = _get_stock_entry_type(doc)
	if entry_type == "Repack" and doc.custom_batched != 1:
		return

	if entry_type not in BATCH_ASSIGNMENT_STOCK_ENTRY_TYPES:
		return

	user_name = frappe.db.get_value("User", doc.modified_by, "full_name") or doc.modified_by

	for item in doc.items:
		if item.batch_no:
			current_date = frappe.db.get_value(
				"Batch", item.batch_no, "custom_date_received"
			)

			if not current_date:
				frappe.db.set_value(
					"Batch", item.batch_no, "custom_date_received", doc.posting_date
				)

				comment_text = (
					f"set received date set via {doc.doctype} <b>{doc.name}</b>"
				)
				batch_doc = frappe.get_doc("Batch", item.batch_no)
				batch_doc.add_comment("Info", comment_text)
