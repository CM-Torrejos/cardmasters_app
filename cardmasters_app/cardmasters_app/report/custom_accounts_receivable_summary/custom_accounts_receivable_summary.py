# Copyright (c) 2026, Cardmasters and contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	AccountsReceivableSummary,
)


def execute(filters=None):
	return CustomAccountsReceivableSummary(filters).run(
		{"account_type": "Receivable", "naming_by": ["Selling Settings", "cust_master_name"]}
	)


class CustomAccountsReceivableSummary(AccountsReceivableSummary):
	"""Filter complete customer summaries, after ERPNext aggregates their balances."""

	def run(self, args):
		fields = self.get_selected_ageing_fields()
		columns, data = super().run(args)
		if fields:
			self.data = [
				row for row in data
				if any(flt(row.get(field), self.currency_precision) for field in fields)
			]
		return columns, self.data

	def get_selected_ageing_fields(self):
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
		return [buckets[value] for value in selected]
