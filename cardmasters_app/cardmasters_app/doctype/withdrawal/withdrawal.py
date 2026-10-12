# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.model.document import Document


class Withdrawal(Document):
	def validate(self):
		"""Recalculate on save so stored allocations never rely on browser values."""
		scale = 1000000

		def units(value):
			return int((Decimal(str(value or 0)) * scale).quantize(Decimal(1), rounding=ROUND_HALF_UP))

		pass_qty = units(self.planned_withdrawal_qty)
		quantities = [units(row.net_print_qty) for row in self.work_orders]
		if pass_qty <= 0:
			frappe.throw(_("Total Withdrawal Quantity must be greater than zero."))
		if any(qty <= 0 for qty in quantities):
			frappe.throw(_("Net Material Quantity must be greater than zero for every work order."))
		total = sum(quantities)
		if total > pass_qty:
			frappe.throw(_("Total Net Material Quantity cannot exceed Total Withdrawal Quantity."))
		allowance = pass_qty - total
		allocations = [allowance * qty // total for qty in quantities] if total else []
		if total:
			# Distribute rounding units by largest fractional remainder; ties use row order.
			order = sorted(range(len(quantities)), key=lambda i: -(allowance * quantities[i] % total))
			for index in order[:allowance - sum(allocations)]:
				allocations[index] += 1
		self.net_print_qty = total / scale
		self.allowance_qty = allowance / scale
		for index, row in enumerate(self.work_orders):
			row.net_print_qty = quantities[index] / scale
			row.allowance_share_pct = round(quantities[index] / total * 100, 6)
			row.allocated_allowance_qty = allocations[index] / scale
			row.withdrawal_qty = (quantities[index] + allocations[index]) / scale
