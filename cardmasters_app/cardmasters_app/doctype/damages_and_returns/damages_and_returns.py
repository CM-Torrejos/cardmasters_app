# Copyright (c) 2025, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


SOURCE_PRODUCTION = "Production"
SOURCE_WAREHOUSE = "Warehouse"
SOURCE_CUSTOMER = "Customer"

ITEM_RAW = "Raw Material/Component"
ITEM_FINISHED_GOOD = "Finished Good"

DELIVERY_NOT_APPLICABLE = "Not Applicable"
DELIVERY_NOT_DELIVERED = "Not Delivered"
DELIVERY_DELIVERED = "Delivered"

HOLDING_STOCK_ENTRY = "Stock Entry"
HOLDING_DELIVERY_NOTE = "Delivery Note"

DISPOSITION_PROCESS_AS_DAMAGE = "Process as Damage"
DISPOSITION_CONVERT_TO_RM = "Convert to RM"
DISPOSITION_CREATE_REPLACEMENT_WORK_ORDER = "Create Replacement Work Order"
DISPOSITION_ISSUE_EXISTING_STOCK = "Issue Existing Stock"
DISPOSITION_NO_REPLACEMENT_NEEDED = "No Replacement Needed"
VALID_DISPOSITIONS = {
	DISPOSITION_PROCESS_AS_DAMAGE,
	DISPOSITION_CONVERT_TO_RM,
	DISPOSITION_CREATE_REPLACEMENT_WORK_ORDER,
	DISPOSITION_ISSUE_EXISTING_STOCK,
	DISPOSITION_NO_REPLACEMENT_NEEDED,
}


class DamagesandReturns(Document):
	def validate(self):
		route = resolve_dnr_route(self)
		validate_dnr_items(self, route)


@frappe.whitelist()
def move_to_holding(docname):
	if not docname:
		frappe.throw(_("Damages and Returns is required."))

	doc = frappe.get_doc("Damages and Returns", docname)
	doc.check_permission("write")

	if doc.docstatus != 1:
		frappe.throw(_("Submit the Damages and Returns document before moving stock to holding."))

	route = resolve_dnr_route(doc)
	validate_dnr_items(doc, route)

	if route.holding_document_type == HOLDING_DELIVERY_NOTE:
		frappe.throw(
			_(
				"Customer returns must be received through a Sales Return Delivery Note. "
				"Create the Sales Return from the original Delivery Note and link it to this DNR."
			)
		)

	if route.holding_document_type != HOLDING_STOCK_ENTRY:
		frappe.throw(_("Unsupported holding document type: {0}").format(route.holding_document_type))

	_validate_no_existing_holding_document(doc)
	stock_entry = _make_holding_stock_entry(doc, route)
	stock_entry.insert()

	for row in doc.get("damaged_or_returned_item"):
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"holding_document_type": HOLDING_STOCK_ENTRY,
				"holding_document": stock_entry.name,
			},
			update_modified=False,
		)

	doc.add_comment(
		"Info",
		text=_("Created draft holding Stock Entry {0}.").format(frappe.bold(stock_entry.name)),
	)

	return {
		"holding_document_type": HOLDING_STOCK_ENTRY,
		"holding_document": stock_entry.name,
		"route": route,
	}


@frappe.whitelist()
def set_disposition(docname, disposition, replacement_qty=None):
	if not docname:
		frappe.throw(_("Damages and Returns is required."))

	doc = frappe.get_doc("Damages and Returns", docname)
	doc.check_permission("write")

	if doc.docstatus != 1:
		frappe.throw(_("Submit the Damages and Returns document before setting disposition."))

	route = resolve_dnr_route(doc)
	validate_dnr_items(doc, route)
	_validate_all_rows_have_holding_document(doc)
	_validate_disposition_allowed(route, disposition)

	replacement_qty = flt(replacement_qty)
	if disposition == DISPOSITION_CREATE_REPLACEMENT_WORK_ORDER and replacement_qty <= 0:
		frappe.throw(_("Replacement Qty must be greater than zero."))
	if (
		disposition != DISPOSITION_CREATE_REPLACEMENT_WORK_ORDER
		and replacement_qty > 0
		and not route.allows_issue_existing_stock
	):
		frappe.throw(_("This DNR route cannot issue replacement stock."))

	for row in doc.get("damaged_or_returned_item"):
		values = {
			"disposition": disposition,
			"replacement_qty": replacement_qty,
		}

		frappe.db.set_value(row.doctype, row.name, values, update_modified=False)

	doc.add_comment(
		"Info",
		text=_("Disposition set to {0}.").format(frappe.bold(disposition)),
	)

	return {"disposition": disposition, "replacement_qty": replacement_qty}


@frappe.whitelist()
def process_damage(docname):
	if not docname:
		frappe.throw(_("Damages and Returns is required."))

	doc = frappe.get_doc("Damages and Returns", docname)
	doc.check_permission("write")

	if doc.docstatus != 1:
		frappe.throw(_("Submit the Damages and Returns document before processing damage."))

	route = resolve_dnr_route(doc)
	validate_dnr_items(doc, route)
	_validate_all_rows_have_holding_document(doc)
	_validate_all_rows_have_disposition(doc, DISPOSITION_PROCESS_AS_DAMAGE)
	_validate_no_existing_processing_document(doc)

	stock_entry = _make_damage_processing_stock_entry(doc)
	stock_entry.insert()

	for row in doc.get("damaged_or_returned_item"):
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"processing_document_type": HOLDING_STOCK_ENTRY,
				"processing_document": stock_entry.name,
			},
			update_modified=False,
		)

	doc.add_comment(
		"Info",
		text=_("Created draft damage processing Stock Entry {0}.").format(frappe.bold(stock_entry.name)),
	)

	return {
		"processing_document_type": HOLDING_STOCK_ENTRY,
		"processing_document": stock_entry.name,
	}


@frappe.whitelist()
def issue_replacement_stock(docname):
	if not docname:
		frappe.throw(_("Damages and Returns is required."))

	doc = frappe.get_doc("Damages and Returns", docname)
	doc.check_permission("write")

	if doc.docstatus != 1:
		frappe.throw(_("Submit the Damages and Returns document before issuing replacement stock."))

	route = resolve_dnr_route(doc)
	validate_dnr_items(doc, route)
	_validate_all_rows_have_holding_document(doc)
	if not route.allows_issue_existing_stock:
		frappe.throw(_("This DNR route cannot issue replacement stock."))
	_validate_replacement_quantities(doc)
	_validate_no_existing_replacement_document(doc)

	stock_entry = _make_replacement_stock_entry(doc, route)
	stock_entry.insert()

	for row in doc.get("damaged_or_returned_item"):
		if flt(row.get("replacement_qty")) <= 0:
			continue

		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"replacement_document_type": HOLDING_STOCK_ENTRY,
				"replacement_document": stock_entry.name,
			},
			update_modified=False,
		)

	doc.add_comment(
		"Info",
		text=_("Created draft replacement Stock Entry {0}.").format(frappe.bold(stock_entry.name)),
	)

	return {
		"replacement_document_type": HOLDING_STOCK_ENTRY,
		"replacement_document": stock_entry.name,
	}


def handle_dnr_stock_entry_cancel(doc, _method=None):
	if not doc.get("custom_damages_and_returns"):
		return

	rows = frappe.get_all(
		"Damages and Returns Item Table",
		filters={"parenttype": "Damages and Returns"},
		or_filters=[
			["holding_document", "=", doc.name],
			["processing_document", "=", doc.name],
			["replacement_document", "=", doc.name],
		],
		fields=[
			"name",
			"parent",
			"holding_document",
			"processing_document",
			"replacement_document",
		],
	)
	if not rows:
		return

	updated_parents = set()
	for row in rows:
		values = {}

		if row.holding_document == doc.name:
			if row.processing_document or row.replacement_document:
				frappe.throw(
					_(
						"Cancel processing and replacement Stock Entries before cancelling holding Stock Entry {0}."
					).format(frappe.bold(doc.name))
				)

			values.update(
				{
					"holding_document_type": None,
					"holding_document": None,
					"disposition": None,
					"replacement_qty": 0,
				}
			)

		if row.processing_document == doc.name:
			values.update(
				{
					"processing_document_type": None,
					"processing_document": None,
				}
			)

		if row.replacement_document == doc.name:
			values.update(
				{
					"replacement_document_type": None,
					"replacement_document": None,
				}
			)

		if not values:
			continue

		frappe.db.set_value(
			"Damages and Returns Item Table",
			row.name,
			values,
			update_modified=False,
		)
		updated_parents.add(row.parent)

	for parent in sorted(updated_parents):
		frappe.get_doc("Damages and Returns", parent).add_comment(
			"Info",
			text=_("Reopened DNR row state because Stock Entry {0} was cancelled.").format(
				frappe.bold(doc.name)
			),
		)


def resolve_dnr_route(doc):
	"""Return the holding route for a DNR without creating any downstream document."""
	source_context = doc.get("source_context")
	item_stage = doc.get("item_stage")
	delivery_state = doc.get("delivery_state")

	_validate_header_values(source_context, item_stage, delivery_state)

	if source_context == SOURCE_CUSTOMER:
		if doc.get("type") != "Return":
			frappe.throw(_("Customer-sourced DNRs must have Type set to Return."))
		if item_stage != ITEM_FINISHED_GOOD:
			frappe.throw(_("Customer-sourced DNRs must be for Finished Goods."))
		if delivery_state != DELIVERY_DELIVERED:
			frappe.throw(_("Customer-sourced Finished Goods must have Delivery State set to Delivered."))

		return frappe._dict(
			source_type="Customer Return",
			holding_action="Sales Return Delivery Note",
			holding_document_type=HOLDING_DELIVERY_NOTE,
			requires_work_order=False,
			requires_source_warehouse=False,
			requires_batch=True,
			allows_replacement_work_order=True,
			allows_issue_existing_stock=True,
			allows_damage_processing=True,
			allows_rm_conversion=True,
		)

	if source_context == SOURCE_PRODUCTION:
		if not doc.get("work_order"):
			frappe.throw(_("Production-sourced DNRs require a Work Order."))
		if delivery_state == DELIVERY_DELIVERED:
			frappe.throw(_("Delivered Finished Goods must use the Customer source context."))

		if item_stage == ITEM_RAW:
			if delivery_state != DELIVERY_NOT_APPLICABLE:
				frappe.throw(_("Raw Material/Component DNRs must use Delivery State: Not Applicable."))

			return frappe._dict(
				source_type="Production Material Damage",
				holding_action="Material Transfer for Manufacture",
				holding_document_type=HOLDING_STOCK_ENTRY,
				requires_work_order=True,
				requires_source_warehouse=True,
				requires_batch=False,
				allows_replacement_work_order=False,
				allows_issue_existing_stock=True,
				allows_damage_processing=True,
				allows_rm_conversion=True,
			)

		if item_stage == ITEM_FINISHED_GOOD:
			if delivery_state != DELIVERY_NOT_DELIVERED:
				frappe.throw(_("Undelivered Finished Goods must use Delivery State: Not Delivered."))

			return frappe._dict(
				source_type="Production FG Damage",
				holding_action="Material Transfer",
				holding_document_type=HOLDING_STOCK_ENTRY,
				requires_work_order=True,
				requires_source_warehouse=True,
				requires_batch=True,
				allows_replacement_work_order=True,
				allows_issue_existing_stock=True,
				allows_damage_processing=True,
				allows_rm_conversion=True,
			)

	if source_context == SOURCE_WAREHOUSE:
		if delivery_state == DELIVERY_DELIVERED:
			frappe.throw(_("Delivered Finished Goods must use the Customer source context."))

		if item_stage == ITEM_RAW:
			if delivery_state != DELIVERY_NOT_APPLICABLE:
				frappe.throw(_("Raw Material/Component DNRs must use Delivery State: Not Applicable."))

			return frappe._dict(
				source_type="Warehouse Stock Damage",
				holding_action="Material Transfer",
				holding_document_type=HOLDING_STOCK_ENTRY,
				requires_work_order=False,
				requires_source_warehouse=True,
				requires_batch=False,
				allows_replacement_work_order=False,
				allows_issue_existing_stock=False,
				allows_damage_processing=True,
				allows_rm_conversion=True,
			)

		if item_stage == ITEM_FINISHED_GOOD:
			if delivery_state != DELIVERY_NOT_DELIVERED:
				frappe.throw(_("Undelivered Finished Goods must use Delivery State: Not Delivered."))

			return frappe._dict(
				source_type="FG Damage Before Delivery",
				holding_action="Material Transfer",
				holding_document_type=HOLDING_STOCK_ENTRY,
				requires_work_order=False,
				requires_source_warehouse=True,
				requires_batch=True,
				allows_replacement_work_order=True,
				allows_issue_existing_stock=True,
				allows_damage_processing=True,
				allows_rm_conversion=True,
			)

	frappe.throw(_("Unable to resolve a DNR route for this source context."))


def validate_dnr_items(doc, route):
	if not doc.get("damaged_or_returned_item"):
		frappe.throw(_("Add at least one Damaged / Returned Item row."))

	for row in doc.get("damaged_or_returned_item"):
		if not row.get("item_code"):
			frappe.throw(_("Row {0}: Item Code is required.").format(row.idx))
		if flt(row.get("quantity")) <= 0:
			frappe.throw(_("Row {0}: Quantity must be greater than zero.").format(row.idx))
		if not row.get("uom"):
			frappe.throw(_("Row {0}: UOM is required.").format(row.idx))

		if route.requires_source_warehouse and not row.get("source_warehouse"):
			frappe.throw(_("Row {0}: Source Warehouse is required for {1}.").format(row.idx, route.source_type))

		if (route.requires_batch or item_requires_batch(row.item_code)) and not row.get("batch"):
			frappe.throw(_("Row {0}: Batch is required for item {1}.").format(row.idx, row.item_code))

		if row.get("holding_document") and not row.get("holding_document_type"):
			frappe.throw(_("Row {0}: Holding Document Type is required when Holding Document is set.").format(row.idx))

		if row.get("holding_document_type") and row.holding_document_type != route.holding_document_type:
			frappe.throw(
				_("Row {0}: Holding Document Type must be {1} for {2}.").format(
					row.idx,
					route.holding_document_type,
					route.source_type,
				)
			)


def _validate_no_existing_holding_document(doc):
	linked_rows = [
		(row.idx, row.holding_document)
		for row in doc.get("damaged_or_returned_item")
		if row.get("holding_document")
	]
	if linked_rows:
		first_row, holding_document = linked_rows[0]
		frappe.throw(
			_("Row {0} is already linked to holding document {1}.").format(
				first_row,
				frappe.bold(holding_document),
			)
		)


def _validate_all_rows_have_holding_document(doc):
	for row in doc.get("damaged_or_returned_item"):
		if not row.get("holding_document"):
			frappe.throw(_("Row {0}: Create the holding document before setting disposition.").format(row.idx))


def _validate_all_rows_have_disposition(doc, disposition):
	for row in doc.get("damaged_or_returned_item"):
		if row.get("disposition") != disposition:
			frappe.throw(
				_("Row {0}: Disposition must be {1} before this action.").format(row.idx, disposition)
			)


def _validate_no_existing_processing_document(doc):
	linked_rows = [
		(row.idx, row.processing_document)
		for row in doc.get("damaged_or_returned_item")
		if row.get("processing_document")
	]
	if linked_rows:
		first_row, processing_document = linked_rows[0]
		frappe.throw(
			_("Row {0} is already linked to processing document {1}.").format(
				first_row,
				frappe.bold(processing_document),
			)
		)


def _validate_replacement_quantities(doc):
	if not any(flt(row.get("replacement_qty")) > 0 for row in doc.get("damaged_or_returned_item")):
		frappe.throw(_("Set Replacement Qty before issuing replacement stock."))


def _validate_no_existing_replacement_document(doc):
	linked_rows = [
		(row.idx, row.replacement_document)
		for row in doc.get("damaged_or_returned_item")
		if row.get("replacement_document")
	]
	if linked_rows:
		first_row, replacement_document = linked_rows[0]
		frappe.throw(
			_("Row {0} is already linked to replacement document {1}.").format(
				first_row,
				frappe.bold(replacement_document),
			)
		)


def _validate_disposition_allowed(route, disposition):
	if disposition not in VALID_DISPOSITIONS:
		frappe.throw(_("Select a valid disposition."))

	if disposition == DISPOSITION_CREATE_REPLACEMENT_WORK_ORDER and not route.allows_replacement_work_order:
		frappe.throw(_("This DNR route cannot create a replacement Work Order."))

	if disposition == DISPOSITION_ISSUE_EXISTING_STOCK and not route.allows_issue_existing_stock:
		frappe.throw(_("This DNR route cannot issue replacement stock."))

	if disposition == DISPOSITION_PROCESS_AS_DAMAGE and not route.allows_damage_processing:
		frappe.throw(_("This DNR route cannot be processed as damage."))

	if disposition == DISPOSITION_CONVERT_TO_RM and not route.allows_rm_conversion:
		frappe.throw(_("This DNR route cannot be converted to RM."))


def _make_holding_stock_entry(doc, route):
	holding_warehouse = _get_holding_warehouse(doc, route)

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = route.holding_action
	stock_entry.stock_entry_type = route.holding_action
	stock_entry.company = doc.company
	stock_entry.posting_date = nowdate()
	stock_entry.custom_damages_and_returns = doc.name
	stock_entry.remarks = _("Holding movement for Damages and Returns {0} ({1}).").format(
		doc.name,
		route.source_type,
	)

	if route.requires_work_order:
		stock_entry.work_order = doc.work_order

	for row in doc.get("damaged_or_returned_item"):
		item = _get_item_details(row.item_code)
		if row.uom != item.stock_uom:
			frappe.throw(
				_("Row {0}: UOM must match stock UOM {1} for holding movement.").format(
					row.idx,
					frappe.bold(item.stock_uom),
				)
			)

		stock_entry.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.get("item_name"),
				"s_warehouse": row.source_warehouse,
				"t_warehouse": holding_warehouse,
				"qty": flt(row.quantity),
				"uom": row.uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": 1,
				"transfer_qty": flt(row.quantity),
				"batch_no": row.batch,
				"use_serial_batch_fields": 1 if row.batch else 0,
			},
		)

	if hasattr(stock_entry, "set_stock_entry_type"):
		stock_entry.set_stock_entry_type()
	stock_entry.set_missing_values()

	return stock_entry


def _make_replacement_stock_entry(doc, route):
	if route.source_type != "Production Material Damage":
		frappe.throw(_("Replacement stock issue is currently supported only for Production Material Damage."))

	work_order = frappe.get_cached_doc("Work Order", doc.work_order)
	if not work_order.wip_warehouse:
		frappe.throw(_("Work Order {0} does not have a WIP Warehouse.").format(frappe.bold(doc.work_order)))

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = "Material Transfer for Manufacture"
	stock_entry.stock_entry_type = "Material Transfer for Manufacture"
	stock_entry.company = doc.company
	stock_entry.posting_date = nowdate()
	stock_entry.work_order = doc.work_order
	stock_entry.custom_damages_and_returns = doc.name
	stock_entry.remarks = _("Replacement stock issue for Damages and Returns {0}.").format(doc.name)

	for row in doc.get("damaged_or_returned_item"):
		replacement_qty = flt(row.get("replacement_qty"))
		if replacement_qty <= 0:
			continue

		item = _get_item_details(row.item_code)
		if row.uom != item.stock_uom:
			frappe.throw(
				_("Row {0}: UOM must match stock UOM {1} for replacement stock issue.").format(
					row.idx,
					frappe.bold(item.stock_uom),
				)
			)

		stock_entry.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.get("item_name"),
				"s_warehouse": row.source_warehouse,
				"t_warehouse": work_order.wip_warehouse,
				"qty": replacement_qty,
				"uom": row.uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": 1,
				"transfer_qty": replacement_qty,
				"batch_no": row.batch,
				"use_serial_batch_fields": 1 if row.batch else 0,
			},
		)

	if hasattr(stock_entry, "set_stock_entry_type"):
		stock_entry.set_stock_entry_type()
	stock_entry.set_missing_values()

	return stock_entry


def _make_damage_processing_stock_entry(doc):
	settings = _get_company_settings(doc.company)
	if not settings.damage_warehouse:
		frappe.throw(
			_("Damage Warehouse is required in Cardmasters Company Settings for Company {0}.").format(
				frappe.bold(doc.company)
			)
		)

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = "Material Transfer"
	stock_entry.stock_entry_type = "Material Transfer"
	stock_entry.company = doc.company
	stock_entry.posting_date = nowdate()
	stock_entry.custom_damages_and_returns = doc.name
	stock_entry.remarks = _("Damage processing for Damages and Returns {0}.").format(doc.name)

	for row in doc.get("damaged_or_returned_item"):
		source_warehouse = _get_holding_source_warehouse(row)
		item = _get_item_details(row.item_code)
		stock_entry.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.get("item_name"),
				"s_warehouse": source_warehouse,
				"t_warehouse": settings.damage_warehouse,
				"qty": flt(row.quantity),
				"uom": row.uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": 1,
				"transfer_qty": flt(row.quantity),
				"batch_no": row.batch,
				"use_serial_batch_fields": 1 if row.batch else 0,
			},
		)

	if hasattr(stock_entry, "set_stock_entry_type"):
		stock_entry.set_stock_entry_type()
	stock_entry.set_missing_values()

	return stock_entry


def _get_holding_source_warehouse(row):
	if row.holding_document_type != HOLDING_STOCK_ENTRY:
		frappe.throw(_("Row {0}: Only Stock Entry holding documents are supported for damage processing.").format(row.idx))

	holding_doc = frappe.get_doc("Stock Entry", row.holding_document)
	if holding_doc.docstatus != 1:
		frappe.throw(
			_("Row {0}: Submit holding Stock Entry {1} before processing damage.").format(
				row.idx,
				frappe.bold(holding_doc.name),
			)
		)

	matches = [
		item for item in holding_doc.get("items")
		if item.item_code == row.item_code
		and (item.batch_no or "") == (row.batch or "")
		and flt(item.qty) == flt(row.quantity)
		and item.t_warehouse
	]
	if not matches:
		frappe.throw(
			_("Row {0}: Could not find a matching target warehouse in holding Stock Entry {1}.").format(
				row.idx,
				frappe.bold(holding_doc.name),
			)
		)

	return matches[0].t_warehouse


def _get_holding_warehouse(doc, route):
	if route.holding_action == "Material Transfer for Manufacture":
		work_order = frappe.get_cached_doc("Work Order", doc.work_order)
		if not work_order.wip_warehouse:
			frappe.throw(_("Work Order {0} does not have a WIP Warehouse.").format(frappe.bold(doc.work_order)))
		return work_order.wip_warehouse

	settings = _get_company_settings(doc.company)
	if not settings.dnr_holding_warehouse:
		frappe.throw(
			_("DNR Holding Warehouse is required in Cardmasters Company Settings for Company {0}.").format(
				frappe.bold(doc.company)
			)
		)
	return settings.dnr_holding_warehouse


def _get_company_settings(company):
	settings = frappe.db.get_value(
		"Cardmasters Company Settings",
		{"company": company},
		["dnr_holding_warehouse", "damage_warehouse"],
		as_dict=True,
	)
	if not settings:
		frappe.throw(
			_("Cardmasters Company Settings is required for Company {0}.").format(frappe.bold(company))
		)
	return settings


def _get_item_details(item_code):
	item = frappe.db.get_value(
		"Item",
		item_code,
		["stock_uom"],
		as_dict=True,
		cache=True,
	)
	if not item:
		frappe.throw(_("Item {0} does not exist.").format(frappe.bold(item_code)))
	if not item.stock_uom:
		frappe.throw(_("Item {0} does not have a Stock UOM.").format(frappe.bold(item_code)))
	return item


def item_requires_batch(item_code):
	if not item_code:
		return False
	return bool(frappe.get_cached_value("Item", item_code, "has_batch_no"))


def _validate_header_values(source_context, item_stage, delivery_state):
	if source_context not in {SOURCE_PRODUCTION, SOURCE_WAREHOUSE, SOURCE_CUSTOMER}:
		frappe.throw(_("Source Context is required."))

	if item_stage not in {ITEM_RAW, ITEM_FINISHED_GOOD}:
		frappe.throw(_("Item Stage is required."))

	if delivery_state not in {DELIVERY_NOT_APPLICABLE, DELIVERY_NOT_DELIVERED, DELIVERY_DELIVERED}:
		frappe.throw(_("Delivery State is required."))
