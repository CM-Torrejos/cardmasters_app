import json

import frappe
from frappe import _
from frappe.utils import flt, now


PENDING_STATUS = "Pending"
CONVERTED_STATUS = "Converted to RM"
DAMAGE_STATUS = "Issued as Damage"
MIXED_STATUS = "Converted to RM and Issued as Damage"
PROCESSED_STATUSES = {CONVERTED_STATUS, DAMAGE_STATUS, MIXED_STATUS}
VALUATION_TOLERANCE = 0.01
QTY_TOLERANCE = 0.000001


def get_cardmasters_return_warehouses(require_master=False, require_damage=False):
	master_warehouse = frappe.db.get_single_value("Cardmasters Settings", "master_warehouse")
	return_warehouse = frappe.db.get_single_value("Cardmasters Settings", "return_warehouse")
	damage_warehouse = frappe.db.get_single_value("Cardmasters Settings", "damage_warehouse")

	if not return_warehouse:
		frappe.throw(
			_("Cardmasters Settings.return_warehouse is required before saving Sales Returns."),
			title=_("Missing Return Warehouse"),
		)

	if require_master and not master_warehouse:
		frappe.throw(
			_("Cardmasters Settings.master_warehouse is required before converting returned items to RM."),
			title=_("Missing Master Warehouse"),
		)

	if require_damage and not damage_warehouse:
		frappe.throw(
			_("Cardmasters Settings.damage_warehouse is required before issuing returned items as damage."),
			title=_("Missing Damage Warehouse"),
		)

	return frappe._dict(
		{
			"master_warehouse": master_warehouse,
			"return_warehouse": return_warehouse,
			"damage_warehouse": damage_warehouse,
		}
	)


def is_rm_item(item_code):
	return (item_code or "").upper().startswith("RM")


def enforce_return_master_warehouse(doc, _method=None):
	if not doc.get("is_return"):
		if _has_field(doc, "custom_return_processing_status"):
			doc.custom_return_processing_status = "Not Applicable"
		return

	validate_damages_and_returns_reference(doc)

	settings = get_cardmasters_return_warehouses()
	for row in get_processable_return_rows(doc):
		row.warehouse = settings.return_warehouse
		if _has_field(row, "custom_return_processing_status") and not row.get("custom_return_processing_status"):
			row.custom_return_processing_status = PENDING_STATUS

	update_delivery_note_return_processing_status(doc)


def validate_damages_and_returns_reference(doc):
	if not _has_field(doc, "custom_damages_and_returns"):
		return

	if not doc.get("custom_damages_and_returns"):
		frappe.throw(
			_("Damages and Returns is required for Sales Return Delivery Notes."),
			title=_("Missing Damages and Returns"),
		)

	damages_and_returns_type = frappe.db.get_value(
		"Damages and Returns", doc.custom_damages_and_returns, "type"
	)
	if damages_and_returns_type and damages_and_returns_type != "Return":
		frappe.throw(
			_("Damages and Returns {0} must have Type set to Return.").format(
				doc.custom_damages_and_returns
			),
			title=_("Invalid Damages and Returns"),
		)


def get_processable_return_rows(doc):
	rows = []
	for row in doc.get("items", []):
		if not row.get("item_code"):
			continue

		is_stock_item = row.get("is_stock_item")
		if is_stock_item is None:
			is_stock_item = frappe.get_cached_value("Item", row.item_code, "is_stock_item")

		if is_stock_item and flt(row.get("qty")):
			rows.append(row)

	return rows


def update_delivery_note_return_processing_status(doc):
	if not doc.get("is_return"):
		if _has_field(doc, "custom_return_processing_status"):
			doc.custom_return_processing_status = "Not Applicable"
		return "Not Applicable"

	rows = get_processable_return_rows(doc)
	if not rows:
		# A return without stock rows has nothing this button can process.
		if _has_field(doc, "custom_return_processing_status"):
			doc.custom_return_processing_status = "Not Applicable"
		return "Not Applicable"

	statuses = [(row.get("custom_return_processing_status") or PENDING_STATUS) for row in rows]
	if all(status == PENDING_STATUS for status in statuses):
		status = "Pending"
	elif all(status in PROCESSED_STATUSES for status in statuses):
		status = "Processed"
	else:
		status = "Partially Processed"

	if _has_field(doc, "custom_return_processing_status"):
		doc.custom_return_processing_status = status
	return status


@frappe.whitelist()
def get_return_item_processing_defaults(delivery_note, delivery_note_item, target_qty=None, damage_qty=None):
	doc, row, settings = _get_valid_return_context(delivery_note, delivery_note_item)
	source_qty = _get_source_qty(row)
	source_valuation_rate = _get_source_valuation_rate(
		row.item_code, settings.return_warehouse, row.batch_no
	)
	source_total_value = flt(source_qty * source_valuation_rate, 2)

	default_rate = 0
	if target_qty:
		conversion_qty = source_qty - flt(damage_qty)
		if conversion_qty > 0:
			allocation = _get_value_allocation(source_qty, source_valuation_rate, damage_qty)
			default_rate = flt(allocation.conversion_value / flt(target_qty), 6)

	return {
		"source_qty": source_qty,
		"source_valuation_rate": source_valuation_rate,
		"source_total_value": source_total_value,
		"default_basic_rate": default_rate,
		"return_warehouse": settings.return_warehouse,
		"master_warehouse": settings.master_warehouse,
	}


@frappe.whitelist()
def process_returned_item(
	delivery_note,
	delivery_note_item,
	outcome=None,
	target_rows=None,
	remarks=None,
	rm_rows=None,
	damage_rows=None,
):
	_enforce_processing_permission()

	rm_rows = _deserialize_rows(rm_rows)
	damage_rows = _deserialize_rows(damage_rows)

	# Keep existing integrations working while the dialog moves away from a single outcome.
	if outcome == "Convert to RM":
		rm_rows = _deserialize_rows(target_rows)
	elif outcome == "Issue as Damage":
		damage_rows = [{"qty": None, "use_full_source_qty": True}]
	elif outcome:
		frappe.throw(_("Unsupported returned item processing outcome: {0}").format(outcome))

	doc, row, settings = _get_valid_return_context(
		delivery_note,
		delivery_note_item,
		require_master=bool(rm_rows),
		require_damage=bool(damage_rows),
	)
	doc.check_permission("write")
	_validate_not_already_processed(row)
	_validate_stock_available(row, settings.return_warehouse)

	if damage_rows and damage_rows[0].get("use_full_source_qty"):
		damage_rows[0]["qty"] = _get_source_qty(row)

	damage_qty = _validate_damage_rows(damage_rows, _get_source_qty(row))
	if rm_rows and damage_qty:
		stock_entry, summary, status = _process_mixed_return(
			doc, row, settings, rm_rows, damage_qty, remarks
		)
	elif rm_rows:
		stock_entry, summary, status = _process_convert_to_rm(doc, row, settings, rm_rows, remarks)
	elif damage_qty:
		if abs(damage_qty - _get_source_qty(row)) > QTY_TOLERANCE:
			frappe.throw(_("The full returned quantity must be issued when there is no RM conversion."))
		stock_entry, summary, status = _process_issue_as_damage(doc, row, settings, remarks)
	else:
		frappe.throw(_("Add at least one RM conversion row or damage issuance row."))

	_mark_row_processed(doc, row, status, stock_entry.name, remarks, summary)

	return {
		"stock_entry": stock_entry.name,
		"status": status,
		"delivery_note_status": doc.get("custom_return_processing_status"),
	}


@frappe.whitelist()
def make_sales_return_with_damages_and_returns(source_name, target_doc=None):
	args = getattr(frappe.flags, "args", None) or frappe._dict()
	damages_and_returns = args.get("damages_and_returns")
	if not damages_and_returns:
		frappe.throw(
			_("Damages and Returns is required to create a Sales Return Delivery Note."),
			title=_("Missing Damages and Returns"),
		)

	if not frappe.db.exists("Damages and Returns", damages_and_returns):
		frappe.throw(
			_("Damages and Returns {0} does not exist.").format(damages_and_returns),
			title=_("Invalid Damages and Returns"),
		)

	damages_and_returns_type = frappe.db.get_value("Damages and Returns", damages_and_returns, "type")
	if damages_and_returns_type and damages_and_returns_type != "Return":
		frappe.throw(
			_("Damages and Returns {0} must have Type set to Return.").format(damages_and_returns),
			title=_("Invalid Damages and Returns"),
		)

	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return

	doc = make_sales_return(source_name, target_doc)
	if _has_field(doc, "custom_damages_and_returns"):
		doc.custom_damages_and_returns = damages_and_returns

	return doc


def handle_return_processing_stock_entry_cancel(doc, _method=None):
	if not doc.get("custom_return_delivery_note") or not doc.get("custom_return_delivery_note_item"):
		return

	if not frappe.db.exists("Delivery Note", doc.custom_return_delivery_note):
		return

	delivery_note = frappe.get_doc("Delivery Note", doc.custom_return_delivery_note)
	row = _get_child_row(delivery_note, doc.custom_return_delivery_note_item)
	if not row:
		return

	if not _has_field(row, "custom_return_processing_stock_entry"):
		return

	if row.get("custom_return_processing_stock_entry") != doc.name:
		return

	row.custom_return_processing_status = PENDING_STATUS
	row.custom_return_processing_stock_entry = None
	row.custom_return_processed_by = None
	row.custom_return_processed_on = None
	row.custom_target_items_json = json.dumps(
		{
			"cancelled_stock_entry": doc.name,
			"reopened_on": now(),
			"reason": "Linked return processing Stock Entry was cancelled.",
		},
		indent=2,
	)
	update_delivery_note_return_processing_status(delivery_note)
	delivery_note.save(ignore_permissions=True)


def _get_valid_return_context(delivery_note, delivery_note_item, require_master=False, require_damage=False):
	doc = frappe.get_doc("Delivery Note", delivery_note)
	doc.check_permission("read")

	if doc.docstatus != 1:
		frappe.throw(_("Returned items can only be processed from a submitted Delivery Note."))

	if not doc.is_return:
		frappe.throw(_("Delivery Note {0} is not a Sales Return.").format(doc.name))

	row = _get_child_row(doc, delivery_note_item)
	if not row:
		frappe.throw(_("Delivery Note Item row {0} was not found.").format(delivery_note_item))

	settings = get_cardmasters_return_warehouses(
		require_master=require_master,
		require_damage=require_damage,
	)
	if row.warehouse != settings.return_warehouse:
		frappe.throw(
			_("Returned item row {0} must be in the return warehouse {1}.").format(row.idx, settings.return_warehouse)
		)

	if not row.item_code or not row.batch_no or not _get_source_qty(row):
		frappe.throw(_("Returned item row {0} must have item, batch, and returned quantity.").format(row.idx))

	return doc, row, settings


def _get_child_row(doc, row_name):
	return next((row for row in doc.get("items", []) if row.name == row_name), None)


def _has_field(doc, fieldname):
	return bool(doc.meta.get_field(fieldname))


def _get_source_qty(row):
	return abs(flt(row.stock_qty or row.qty))


def _validate_not_already_processed(row):
	status = row.get("custom_return_processing_status") or PENDING_STATUS
	if row.get("custom_return_processing_stock_entry"):
		stock_entry_status = frappe.db.get_value(
			"Stock Entry", row.custom_return_processing_stock_entry, "docstatus"
		)
		if stock_entry_status in (0, 1):
			frappe.throw(
				_("Delivery Note Item row {0} has already been processed by Stock Entry {1}.").format(
					row.idx, row.custom_return_processing_stock_entry
				)
			)

	if status != PENDING_STATUS:
		frappe.throw(_("Delivery Note Item row {0} has already been processed.").format(row.idx))


def _validate_stock_available(row, warehouse):
	from erpnext.stock.doctype.batch.batch import get_batch_qty

	available_qty = flt(get_batch_qty(batch_no=row.batch_no, warehouse=warehouse, item_code=row.item_code))
	if available_qty < _get_source_qty(row):
		frappe.throw(
			_(
				"Returned batch {0} for item {1} is no longer available in {2}. "
				"It may have already been processed, transferred, or adjusted."
			).format(row.batch_no, row.item_code, warehouse)
		)


def _get_source_valuation_rate(item_code, warehouse, batch_no):
	from erpnext.stock.stock_ledger import get_valuation_rate

	return flt(
		get_valuation_rate(
			item_code=item_code,
			warehouse=warehouse,
			voucher_type="Delivery Note",
			voucher_no="",
			batch_no=batch_no,
			raise_error_if_no_rate=True,
		),
		6,
	)


def _deserialize_rows(rows):
	if isinstance(rows, str):
		rows = json.loads(rows or "[]")
	return rows or []


def _validate_damage_rows(damage_rows, source_qty):
	damage_qty = 0
	for idx, damage in enumerate(damage_rows, start=1):
		qty = flt(damage.get("qty"))
		if qty <= 0:
			frappe.throw(_("Damage issuance row {0}: Qty must be greater than zero.").format(idx))
		damage_qty += qty

	if damage_qty - source_qty > QTY_TOLERANCE:
		frappe.throw(
			_("Total damage quantity {0} cannot exceed the returned quantity {1}.").format(
				damage_qty, source_qty
			)
		)

	return damage_qty


def _get_value_allocation(source_qty, source_valuation_rate, damage_qty):
	source_value = flt(flt(source_qty) * flt(source_valuation_rate), 2)
	damage_value = flt(flt(damage_qty) * flt(source_valuation_rate), 2)
	return frappe._dict(
		{
			"source_value": source_value,
			"damage_value": damage_value,
			"conversion_value": flt(source_value - damage_value, 2),
		}
	)


def _process_convert_to_rm(doc, row, settings, target_rows, remarks):
	source_qty = _get_source_qty(row)
	source_valuation_rate = _get_source_valuation_rate(row.item_code, settings.return_warehouse, row.batch_no)
	source_total_value = flt(source_qty * source_valuation_rate, 2)
	targets = _validate_target_rows(target_rows)
	target_total_value = flt(sum(flt(target.qty) * flt(target.basic_rate) for target in targets), 2)

	if abs(source_total_value - target_total_value) > VALUATION_TOLERANCE:
		frappe.throw(
			_(
				"Target RM valuation total must equal the returned item valuation total. "
				"Source total is {0}; target total is {1}."
			).format(source_total_value, target_total_value)
		)

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = "Repack"
	stock_entry.stock_entry_type = "Repack"
	stock_entry.company = doc.company
	stock_entry.custom_return_delivery_note = doc.name
	stock_entry.custom_return_delivery_note_item = row.name
	stock_entry.remarks = _build_stock_entry_remarks(doc, row, "Convert to RM", remarks, source_total_value, target_total_value)
	stock_entry.append(
		"items",
		{
			"item_code": row.item_code,
			"batch_no": row.batch_no,
			"s_warehouse": settings.return_warehouse,
			"qty": source_qty,
			"basic_rate": source_valuation_rate,
		},
	)

	for target in targets:
		stock_entry.append(
			"items",
			{
				"item_code": target.item_code,
				"t_warehouse": settings.master_warehouse,
				"qty": flt(target.qty),
				"basic_rate": flt(target.basic_rate),
				"set_basic_rate_manually": 1,
				"is_finished_item": 1,
			},
		)

	stock_entry.insert()
	stock_entry.submit()

	summary = {
		"outcome": "Convert to RM",
		"source_item": row.item_code,
		"source_batch": row.batch_no,
		"source_warehouse": settings.return_warehouse,
		"source_qty": source_qty,
		"source_valuation_rate": source_valuation_rate,
		"source_total_value": source_total_value,
		"target_rm_rows": [dict(target) for target in targets],
		"target_total_value": target_total_value,
		"stock_entry": stock_entry.name,
	}
	return stock_entry, summary, CONVERTED_STATUS


def _process_mixed_return(doc, row, settings, target_rows, damage_qty, remarks):
	source_qty = _get_source_qty(row)
	conversion_qty = flt(source_qty - damage_qty)
	if conversion_qty <= QTY_TOLERANCE:
		frappe.throw(_("RM conversion quantity must be greater than zero after damage issuance."))

	source_valuation_rate = _get_source_valuation_rate(
		row.item_code, settings.return_warehouse, row.batch_no
	)
	allocation = _get_value_allocation(source_qty, source_valuation_rate, damage_qty)
	source_total_value = allocation.source_value
	damage_total_value = allocation.damage_value
	conversion_total_value = allocation.conversion_value
	targets = _validate_target_rows(target_rows)
	target_rm_total_value = flt(
		sum(flt(target.qty) * flt(target.basic_rate) for target in targets), 2
	)

	if abs(conversion_total_value - target_rm_total_value) > VALUATION_TOLERANCE:
		frappe.throw(
			_(
				"Target RM valuation total must equal the cost of the quantity being converted. "
				"Conversion cost is {0}; target total is {1}."
			).format(conversion_total_value, target_rm_total_value)
		)

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = "Repack"
	stock_entry.stock_entry_type = "Repack"
	stock_entry.company = doc.company
	stock_entry.custom_return_delivery_note = doc.name
	stock_entry.custom_return_delivery_note_item = row.name
	stock_entry.remarks = _build_stock_entry_remarks(
		doc,
		row,
		"Convert to RM and Issue as Damage",
		remarks,
		source_total_value,
		flt(damage_total_value + target_rm_total_value, 2),
	)
	stock_entry.append(
		"items",
		{
			"item_code": row.item_code,
			"batch_no": row.batch_no,
			"s_warehouse": settings.return_warehouse,
			"qty": source_qty,
			"basic_rate": source_valuation_rate,
		},
	)
	stock_entry.append(
		"items",
		{
			"item_code": row.item_code,
			"batch_no": row.batch_no,
			"t_warehouse": settings.damage_warehouse,
			"qty": damage_qty,
			"basic_rate": source_valuation_rate,
			"set_basic_rate_manually": 1,
			"is_finished_item": 1,
		},
	)

	for target in targets:
		stock_entry.append(
			"items",
			{
				"item_code": target.item_code,
				"t_warehouse": settings.master_warehouse,
				"qty": flt(target.qty),
				"basic_rate": flt(target.basic_rate),
				"set_basic_rate_manually": 1,
				"is_finished_item": 1,
			},
		)

	stock_entry.insert()
	stock_entry.submit()

	summary = {
		"outcome": "Convert to RM and Issue as Damage",
		"source_item": row.item_code,
		"source_batch": row.batch_no,
		"source_warehouse": settings.return_warehouse,
		"source_qty": source_qty,
		"source_valuation_rate": source_valuation_rate,
		"source_total_value": source_total_value,
		"conversion_source_qty": conversion_qty,
		"conversion_total_value": conversion_total_value,
		"target_rm_rows": [dict(target) for target in targets],
		"target_rm_total_value": target_rm_total_value,
		"damage_qty": damage_qty,
		"damage_total_value": damage_total_value,
		"damage_warehouse": settings.damage_warehouse,
		"stock_entry": stock_entry.name,
	}
	return stock_entry, summary, MIXED_STATUS


def _process_issue_as_damage(doc, row, settings, remarks):
	source_qty = _get_source_qty(row)

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = "Material Transfer"
	stock_entry.stock_entry_type = "Material Transfer"
	stock_entry.company = doc.company
	stock_entry.custom_return_delivery_note = doc.name
	stock_entry.custom_return_delivery_note_item = row.name
	stock_entry.remarks = _build_stock_entry_remarks(doc, row, "Issue as Damage", remarks)
	stock_entry.append(
		"items",
		{
			"item_code": row.item_code,
			"batch_no": row.batch_no,
			"s_warehouse": settings.return_warehouse,
			"t_warehouse": settings.damage_warehouse,
			"qty": source_qty,
		},
	)
	stock_entry.insert()
	stock_entry.submit()

	summary = {
		"outcome": "Issue as Damage",
		"source_item": row.item_code,
		"source_batch": row.batch_no,
		"source_warehouse": settings.return_warehouse,
		"source_qty": source_qty,
		"target_item": row.item_code,
		"target_batch": row.batch_no,
		"target_warehouse": settings.damage_warehouse,
		"stock_entry": stock_entry.name,
	}
	return stock_entry, summary, DAMAGE_STATUS


def _validate_target_rows(target_rows):
	if not target_rows:
		frappe.throw(_("At least one target RM row is required."))

	targets = []
	for idx, target in enumerate(target_rows, start=1):
		item_code = (target.get("item_code") or "").strip()
		qty = flt(target.get("qty"))
		basic_rate = flt(target.get("basic_rate"))

		if not item_code:
			frappe.throw(_("Target RM row {0}: Item Code is required.").format(idx))
		if not frappe.db.exists("Item", item_code):
			frappe.throw(_("Target RM row {0}: Item {1} does not exist.").format(idx, item_code))
		if not is_rm_item(item_code):
			frappe.throw(_("Target RM row {0}: Item {1} must be an RM item.").format(idx, item_code))
		if qty <= 0:
			frappe.throw(_("Target RM row {0}: Qty must be greater than zero.").format(idx))
		if basic_rate < 0:
			frappe.throw(_("Target RM row {0}: Basic Rate cannot be negative.").format(idx))

		targets.append(
			frappe._dict(
				{
					"item_code": item_code,
					"qty": qty,
					"basic_rate": basic_rate,
					"amount": flt(qty * basic_rate, 2),
				}
			)
		)

	return targets


def _mark_row_processed(doc, row, status, stock_entry_name, remarks, summary):
	_require_return_processing_fields(doc, row)

	row.custom_return_processing_status = status
	row.custom_return_processing_stock_entry = stock_entry_name
	row.custom_return_processed_by = frappe.session.user
	row.custom_return_processed_on = now()
	row.custom_return_processing_remarks = remarks
	row.custom_target_items_json = json.dumps(summary, indent=2, default=str)

	update_delivery_note_return_processing_status(doc)
	doc.save()


def _require_return_processing_fields(doc, row):
	missing_fields = []
	for fieldname in ("custom_return_processing_status",):
		if not _has_field(doc, fieldname):
			missing_fields.append(f"Delivery Note.{fieldname}")

	for fieldname in (
		"custom_return_processing_status",
		"custom_return_processing_stock_entry",
		"custom_return_processed_by",
		"custom_return_processed_on",
		"custom_return_processing_remarks",
		"custom_target_items_json",
	):
		if not _has_field(row, fieldname):
			missing_fields.append(f"Delivery Note Item.{fieldname}")

	if missing_fields:
		frappe.throw(
			_(
				"Return processing custom fields are not installed yet. Run bench migrate, then retry. Missing: {0}"
			).format(", ".join(missing_fields))
		)


def _build_stock_entry_remarks(doc, row, outcome, remarks=None, source_total=None, target_total=None):
	lines = [
		"Return Processing",
		f"Source Return Delivery Note: {doc.name}",
		f"Delivery Note Item row: {row.name}",
		f"Original item/batch: {row.item_code} / {row.batch_no}",
		f"Outcome: {outcome}",
	]
	if source_total is not None:
		lines.append(f"Source total value: {source_total}")
	if target_total is not None:
		lines.append(f"Target total value: {target_total}")
		lines.append("Valuation preserved.")
	if remarks:
		lines.append(f"Remarks: {remarks}")

	return "\n".join(lines)


def _enforce_processing_permission():
	if frappe.session.user == "Administrator":
		return

	roles = set(frappe.get_roles(frappe.session.user))
	if not roles.intersection({"Stock User", "Stock Manager"}):
		frappe.throw(_("Only users with Stock User or Stock Manager role can process returned items."))

	if not frappe.has_permission("Stock Entry", "create"):
		frappe.throw(_("You do not have permission to create Stock Entry."))

	if not frappe.has_permission("Stock Entry", "submit"):
		frappe.throw(_("You do not have permission to submit Stock Entry."))
