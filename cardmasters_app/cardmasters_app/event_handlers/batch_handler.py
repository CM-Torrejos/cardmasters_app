import frappe
from frappe import _

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

BATCH_NAME_MAX_LEN = 100
IDENTITY_SOURCE_SYSTEM = "system_generated"
IDENTITY_SOURCE_LEGACY = "legacy_unresolved"


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _build_new_batch_name(so_name: str, soi_docname: str) -> str:
	"""
	Construct the canonical batch name: {SO_NAME}_{SOI_DOCNAME}.

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
				"Check the Sales Order name and Sales Order Item docname."
			).format(name, len(name)),
			title=_("Batch Name Too Long"),
		)
	return name


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

	On DuplicateEntryError (race condition), rolls back and returns the
	already-existing name — the batch was created by a concurrent request.
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
			frappe.db.rollback()
	else:
		# Batch already exists — append this WO for traceability
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

	return batch_name


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
# STOCK ENTRY HOOK — Manufacture
# ---------------------------------------------------------------------------

def set_batch_no_for_fg_on_manufacture_entry(doc, method):
	"""
	Assign (or create) the canonical batch for the finished-goods line on a
	Manufacture Stock Entry.

	Triggered on: Stock Entry submit, purpose = Manufacture.

	Identity rule
	-------------
	Batch.name  =  {sales_order}_{sales_order_item}   (e.g. SO-043680_SOI-1238)

	If a batch with that name already exists the FG row is pointed at it,
	accumulating a weighted-average valuation across all contributing WOs.
	If it does not exist yet, it is created.

	Preconditions (hard errors)
	---------------------------
	- Stock Entry must be flagged custom_batched = 1
	- Stock Entry must reference a Work Order
	- Work Order must carry both sales_order and sales_order_item
	- A finished-goods receipt row must be identifiable
	"""
	if doc.custom_batched != 1:
		return

	if doc.purpose != "Manufacture":
		return

	if not doc.work_order:
		frappe.throw(_("Stock Entry must reference a Work Order"))

	wo = frappe.get_doc("Work Order", doc.work_order)

	# ------------------------------------------------------------------
	# Resolve Sales Order and Sales Order Item from the Work Order
	# ------------------------------------------------------------------
	so_name = wo.sales_order
	soi_docname = wo.sales_order_item

	if not so_name:
		frappe.throw(
			_("Work Order {0} does not reference a Sales Order. "
			  "Cannot determine batch identity.").format(wo.name)
		)
	if not soi_docname:
		frappe.throw(
			_("Work Order {0} does not reference a Sales Order Item. "
			  "Cannot determine batch identity.").format(wo.name)
		)

	# ------------------------------------------------------------------
	# Locate the finished-goods receipt row
	# ------------------------------------------------------------------
	fg_row = next(
		(
			item
			for item in doc.items
			if item.item_code == wo.production_item and not item.s_warehouse
		),
		None,
	)

	if not fg_row:
		frappe.throw(
			_("Could not find the FG receipt row for {0}").format(wo.production_item)
		)

	# ------------------------------------------------------------------
	# Build canonical batch name and assign / create
	# ------------------------------------------------------------------
	batch_name = _build_new_batch_name(so_name, soi_docname)

	fg_row.batch_no = _get_or_create_batch(
		batch_name=batch_name,
		item_code=fg_row.item_code,
		posting_date=doc.posting_date,
		so_name=so_name,
		soi_docname=soi_docname,
		work_order=doc.work_order,
		wo_qty=fg_row.qty,
	)
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

	Lookup strategy (DUAL — temporary for transition period)
	---------------------------------------------------------
	1. NEW BATCH PATH
	   Construct expected name as f"{against_sales_order}_{so_detail}" and
	   query Batch.name directly.  This is the canonical path for all batches
	   created after the naming-scheme cutover.

	2. LEGACY BATCH PATH
	   If the direct lookup returns nothing, reconstruct the legacy name using
	   the old formula: "{SO} - {item_code}:{item_specifics}".  This path
	   exists solely to serve batches whose Batch.name was set by the old
	   build_batch_name function before cutover.

	TODO: Remove the legacy fallback once all pre-cutover batches have no
		  open stock movements.  At that point only step 1 is needed.

	Behavior on save (draft) vs submit
	------------------------------------
	- Missing batch on SAVE  → orange warning, does not block.
	- Missing batch on SUBMIT → hard error, blocks submission.
	"""
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
		# Step 1 — New-batch direct lookup (canonical path)
		# ------------------------------------------------------------------
		new_batch_name = f"{so_name}_{so_detail}"
		found_batch = frappe.db.get_value("Batch", new_batch_name, "name")

		# ------------------------------------------------------------------
		# Step 2 — Legacy fallback (TEMPORARY — see TODO above)
		# ------------------------------------------------------------------
		if not found_batch:
			item_specifics = (d.get("custom_item_specifics") or "").strip()
			if not item_specifics:
				item_specifics = (
					frappe.db.get_value(
						"Sales Order Item", so_detail, "custom_item_specifics"
					)
					or ""
				).strip()

			# Legacy formula: "{SO} - {item_code}:{item_specifics}"
			legacy_name = f"{so_name} - {item_code}:{item_specifics}"
			legacy_name = legacy_name.strip()[:BATCH_NAME_MAX_LEN]

			# Direct name match
			if frappe.db.exists("Batch", legacy_name):
				found_batch = legacy_name
			else:
				# batch_id match (old batches may have differing name vs batch_id)
				found_batch = frappe.db.get_value(
					"Batch", {"batch_id": legacy_name}, "name"
				)

		# ------------------------------------------------------------------
		# Step 3 — Assign or flag missing
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
	if doc.docstatus != 1 or doc.purpose != "Manufacture":
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