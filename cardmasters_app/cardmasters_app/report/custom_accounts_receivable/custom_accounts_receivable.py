# Copyright (c) 2026, Cardmasters and contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport


def execute(filters=None):
	return CustomAccountsReceivable(filters).run(
		{"account_type": "Receivable", "naming_by": ["Selling Settings", "cust_master_name"]}
	)


class CustomAccountsReceivable(ReceivablePayableReport):
	"""Use ERPNext's ledger calculation; filter before accumulating subtotals."""

	def get_columns(self):
		super().get_columns()
		lower = 0
		buckets = {}
		for index, limit in enumerate(self.ranges, start=1):
			buckets[f"{lower}-{limit}"] = f"range{index}"
			lower = int(limit) + 1
		buckets[f"{lower}+"] = f"range{len(self.ranges) + 1}"

		selected = self.filters.get("selected_ageing_buckets") or []
		if isinstance(selected, str):
			selected = frappe.parse_json(selected)
		if not isinstance(selected, list) or any(
			not isinstance(value, str) or value not in buckets for value in selected
		):
			frappe.throw(_("Please select ageing buckets from the current Ageing Range."))
		self.selected_ageing_fields = [buckets[value] for value in selected]

	def append_row(self, row):
		if not self.selected_ageing_fields:
			return super().append_row(row)

		# Keep the upstream preparation order, including payment-term due dates
		# and future-payment allocation. Age alone is insufficient: not-yet-due
		# entries have no balance in any ageing bucket.
		self.allocate_future_payments(row)
		self.set_invoice_details(row)
		self.set_party_details(row)
		self.set_ageing(row)
		if not any(flt(row.get(field), self.currency_precision) for field in self.selected_ageing_fields):
			return

		if self.filters.get("group_by_party"):
			self.update_sub_total_row(row, row.party)
			if self.previous_party and self.previous_party != row.party:
				self.append_subtotal_row(self.previous_party)
			self.previous_party = row.party

		self.data.append(row)
