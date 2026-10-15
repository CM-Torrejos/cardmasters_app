# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowtime

TRANSFER_PURPOSE = "Material Transfer for Manufacture"


class Withdrawal(Document):
	def onload(self):
		self.set_onload("quantity_precision", self.quantity_precision())

	@staticmethod
	def quantity_precision():
		return min(frappe.get_precision("Stock Entry Detail", field) for field in ("qty", "transfer_qty"))

	def validate(self):
		self.calculate_allocation(strict=self.docstatus == 1)
		if self.item:
			stock_uom = frappe.db.get_value("Item", self.item, "stock_uom")
			if self.uom and self.uom != stock_uom:
				frappe.throw(_("Unit conversions are not enabled. UOM must match the item's Stock UOM."))
			self.stock_uom = self.uom = stock_uom
		if self.docstatus == 0:
			# Transfer references are created exclusively during submission.
			for row in self.work_orders:
				row.stock_entry = None
				row.allowance_stock_entry = None

	def calculate_allocation(self, strict=False):
		scale = 10 ** self.quantity_precision()

		def units(value):
			try:
				amount = Decimal(str(value or 0))
				if not amount.is_finite():
					raise InvalidOperation
				return int((amount * scale).quantize(Decimal(1), rounding=ROUND_HALF_UP))
			except (InvalidOperation, ValueError, OverflowError):
				frappe.throw(_("Material quantities must be finite numbers."))

		withdrawal_qty = units(self.planned_withdrawal_qty)
		quantities = [units(row.net_print_qty) for row in self.work_orders]
		if strict:
			if withdrawal_qty <= 0:
				frappe.throw(_("Total Withdrawal Quantity must be greater than zero."))
			if not quantities:
				frappe.throw(_("Add at least one work order."))
			for row, qty in zip(self.work_orders, quantities):
				if not row.work_order or qty <= 0:
					frappe.throw(_("Row {0}: Work Order and a positive Net Material Quantity are required.").format(row.idx))
			total = sum(quantities)
			if total > withdrawal_qty:
				frappe.throw(_("Total Net Material Quantity cannot exceed Total Withdrawal Quantity."))
		else:
			quantities = [max(0, qty) for qty in quantities]
		total = sum(quantities)
		allowance = withdrawal_qty - total
		allocations = [0] * len(quantities)
		if total and allowance >= 0:
			allocations = [allowance * qty // total for qty in quantities]
			order = sorted(range(len(quantities)), key=lambda i: -(allowance * quantities[i] % total))
			for index in order[:allowance - sum(allocations)]:
				allocations[index] += 1
		self.net_print_qty = total / scale
		self.allowance_qty = allowance / scale
		if strict:
			self.planned_withdrawal_qty = withdrawal_qty / scale
		for index, row in enumerate(self.work_orders):
			if strict:
				row.net_print_qty = quantities[index] / scale
			row.allowance_share_pct = round(quantities[index] / total * 100, 6) if total else 0
			row.allocated_allowance_qty = allocations[index] / scale
			row.withdrawal_qty = (quantities[index] + allocations[index]) / scale

	def before_submit(self):
		for field in ("item", "company", "source_warehouse", "wip_warehouse", "posting_date"):
			if not self.get(field):
				frappe.throw(_("{0} is required before submission.").format(self.meta.get_label(field)))
		self.posting_time = self.posting_time or nowtime()
		self.calculate_allocation(strict=True)
		item = frappe.get_doc("Item", self.item)
		item.check_permission("read")
		if item.disabled or not item.is_stock_item:
			frappe.throw(_("Select an enabled stock item."))
		if self.uom != item.stock_uom:
			frappe.throw(_("Unit conversions are not enabled. UOM must match the item's Stock UOM."))
		if self.source_warehouse == self.wip_warehouse:
			frappe.throw(_("Source and Target WIP Warehouse must be different."))
		for name in (self.source_warehouse, self.wip_warehouse):
			warehouse = frappe.get_doc("Warehouse", name)
			warehouse.check_permission("read")
			if warehouse.company != self.company or warehouse.is_group or warehouse.disabled:
				frappe.throw(_("Warehouse {0} must be an enabled ledger warehouse in company {1}.").format(name, self.company))
		self.flags.withdrawal_work_orders = self.get_work_orders(for_submission=True)
		if frappe.db.exists("Stock Entry", {"custom_withdrawal": self.name, "docstatus": ["<", 2]}):
			frappe.throw(_("This Withdrawal already has material transfers. Refresh the document."))
		self.check_available_stock()

	def get_work_orders(self, for_submission=False):
		orders = {}
		# Stable lock order serializes withdrawals sharing work orders.
		for name in sorted({row.work_order for row in self.work_orders if row.work_order}):
			wo = frappe.get_doc("Work Order", name, for_update=True)
			wo.check_permission("read")
			if for_submission:
				if wo.docstatus != 1 or wo.status in ("Closed", "Stopped", "Cancelled"):
					frappe.throw(_("Work Order {0} must be submitted and open.").format(name))
				if wo.company != self.company or wo.wip_warehouse != self.wip_warehouse:
					frappe.throw(_("Work Order {0} must match the company and Target WIP Warehouse.").format(name))
				if wo.skip_transfer or wo.transfer_material_against != "Work Order":
					frappe.throw(_("Work Order {0} must allow material transfers against the Work Order.").format(name))
			manufacture_qty = sum(flt(entry.fg_completed_qty) for entry in frappe.db.sql(
				"""select name, fg_completed_qty from `tabStock Entry`
				where work_order=%s and purpose='Manufacture' and docstatus in (0, 1)
				order by name for update""", name, as_dict=True))
			if flt(manufacture_qty, 6) >= flt(wo.qty, 6):
				frappe.throw(_("Work Order {0} already has Manufacture entries covering its full quantity, including drafts. Withdrawal submission or cancellation is not allowed.").format(name))
			orders[name] = wo
		return orders

	def check_available_stock(self):
		from erpnext.stock.stock_ledger import get_previous_sle

		# Do not inherit the site's allow-negative-stock setting for this workflow.
		bin_qty = frappe.db.get_value("Bin", {"item_code": self.item, "warehouse": self.source_warehouse}, "actual_qty", for_update=True) or 0
		previous = get_previous_sle(frappe._dict(item_code=self.item, warehouse=self.source_warehouse,
			posting_date=self.posting_date, posting_time=self.posting_time), for_update=True)
		available = min(flt(bin_qty), flt(previous.get("qty_after_transaction")))
		if flt(self.planned_withdrawal_qty, self.quantity_precision()) > flt(available, self.quantity_precision()):
			frappe.throw(_("Insufficient stock of {0} in {1}: available {2}, requested {3} {4}.").format(
				self.item, self.source_warehouse, available, self.planned_withdrawal_qty, self.uom))

	def on_submit(self):
		orders = self.flags.withdrawal_work_orders
		grouped = defaultdict(list)
		for row in self.work_orders:
			grouped[row.work_order].append(row)
		for name in sorted(grouped):
			wo = orders[name]
			net_qty = flt(sum(Decimal(str(row.net_print_qty)) for row in grouped[name]), self.quantity_precision())
			allowance_qty = flt(sum(Decimal(str(row.allocated_allowance_qty)) for row in grouped[name]), self.quantity_precision())
			transferred = frappe.db.sql("""select coalesce(sum(fg_completed_qty), 0)
				from `tabStock Entry` where work_order=%s and purpose=%s and docstatus=1
				for update""", (name, TRANSFER_PURPOSE))[0][0]
			entry = self.create_transfer(wo, net_qty, max(0, flt(wo.qty) - flt(transferred)), "Net Material")
			# Allowance carries material and cost, but never advances the WO's BOM quantity twice.
			allowance_entry = self.create_transfer(wo, allowance_qty, 0, "Allowance") if allowance_qty else None
			for row in grouped[name]:
				row.db_set("stock_entry", entry.name, update_modified=False)
				row.db_set("allowance_stock_entry", allowance_entry.name if allowance_entry else None, update_modified=False)

	def create_transfer(self, wo, qty, fg_completed_qty, component):
		entry = frappe.new_doc("Stock Entry")
		entry.update({"stock_entry_type": TRANSFER_PURPOSE, "purpose": TRANSFER_PURPOSE,
			"company": self.company, "work_order": wo.name, "bom_no": wo.bom_no, "from_bom": 1,
			"fg_completed_qty": fg_completed_qty,
			"from_warehouse": self.source_warehouse, "to_warehouse": self.wip_warehouse,
			"posting_date": self.posting_date, "posting_time": self.posting_time, "set_posting_time": 1,
			"project": wo.project, "custom_withdrawal": self.name, "custom_withdrawal_component": component,
			"remarks": _("{0} transfer from Withdrawal {1}.").format(component, self.name)
				+ ("\n" + self.remarks if self.remarks else "")})
		details = entry.get_item_details(frappe._dict(item_code=self.item, qty=qty, uom=self.uom))
		details.update(item_code=self.item, qty=qty, uom=self.uom, stock_uom=self.stock_uom,
			conversion_factor=1, s_warehouse=self.source_warehouse, t_warehouse=self.wip_warehouse)
		entry.append("items", details)
		entry.flags.withdrawal_creation = self.name
		entry.insert()
		entry.submit()
		return entry

	def before_cancel(self):
		self.get_work_orders()
		entries = frappe.get_all("Stock Entry", filters={"custom_withdrawal": self.name}, fields=["name", "docstatus"], order_by="creation desc, name desc")
		linked = {row.get(field) for row in self.work_orders
			for field in ("stock_entry", "allowance_stock_entry") if row.get(field)}
		if linked != {entry.name for entry in entries}:
			frappe.throw(_("Generated material transfer links are inconsistent. Resolve them before cancellation."))
		for entry in entries:
			if entry.docstatus == 0:
				frappe.throw(_("Generated transfer {0} is unexpectedly a draft.").format(entry.name))
			if entry.docstatus == 1:
				doc = frappe.get_doc("Stock Entry", entry.name, for_update=True)
				doc.flags.withdrawal_cancellation = self.name
				doc.cancel()


def validate_generated_transfer(doc, _method=None):
	"""Generated transfers must be posted by their owning Withdrawal."""
	if doc.get("custom_withdrawal") and doc.flags.withdrawal_creation != doc.custom_withdrawal:
		frappe.throw(_("This material transfer is managed by Withdrawal {0}. Use the Withdrawal to make changes.").format(doc.custom_withdrawal))


def before_cancel_generated_transfer(doc, _method=None):
	if not doc.get("custom_withdrawal"):
		return
	if doc.flags.withdrawal_cancellation != doc.custom_withdrawal:
		frappe.throw(_("Cancel Withdrawal {0} to reverse this generated material transfer.").format(doc.custom_withdrawal))
	# Its parent's rows still refer to the transfer until parent cancellation finishes.
	doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ()) + ("Withdrawal Work Order",)
