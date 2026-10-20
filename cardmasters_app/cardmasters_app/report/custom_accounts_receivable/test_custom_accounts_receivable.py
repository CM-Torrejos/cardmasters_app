from datetime import date, timedelta
from unittest import TestCase
from unittest.mock import patch

import frappe

from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport

from cardmasters_app.cardmasters_app.report.custom_accounts_receivable.custom_accounts_receivable import (
	CustomAccountsReceivable,
)


class TestCustomAccountsReceivable(TestCase):
	def report(self, selected=None, grouped=False, ranges=None):
		report = object.__new__(CustomAccountsReceivable)
		report.filters = frappe._dict(
			selected_ageing_buckets=selected,
			group_by_party=grouped,
			ageing_based_on="Due Date",
		)
		report.ranges = ranges or ["30", "60", "90", "120"]
		report.range_numbers = list(range(1, len(report.ranges) + 2))
		report.currency_precision = 2
		report.age_as_on = date(2026, 10, 20)
		report.data = []
		report.previous_party = ""
		report.total_row_map = {}
		for party in ("Young", "Mixed", "Old", "Total"):
			report.init_subtotal_row(party)
		for method in ("allocate_future_payments", "set_invoice_details", "set_party_details"):
			setattr(report, method, lambda row: None)
		with patch.object(ReceivablePayableReport, "get_columns"):
			report.get_columns()
		return report

	def row(self, age, party="Mixed", amount=100):
		return frappe._dict(
			party=party,
			posting_date=date(2026, 10, 20) - timedelta(days=age),
			due_date=date(2026, 10, 20) - timedelta(days=age),
			outstanding=amount,
			currency="PHP",
		)

	def test_bucket_boundaries(self):
		for bucket, ages in {
			"0-30": [0, 30], "31-60": [31, 60], "61-90": [61, 90],
			"91-120": [91, 120], "121+": [121, 180],
		}.items():
			with self.subTest(bucket=bucket):
				report = self.report([bucket])
				for age in [-1, 0, 30, 31, 60, 61, 90, 91, 120, 121, 180]:
					report.append_row(self.row(age))
				self.assertEqual([row.age for row in report.data], ages)

	def test_empty_selection_preserves_standard_behavior(self):
		report = self.report()
		for age in [-1, 20, 45, 150]:
			report.append_row(self.row(age))
		self.assertEqual(len(report.data), 4)

	def test_group_totals_exclude_nonmatching_customers_and_invoices(self):
		report = self.report(["31-60", "121+"], grouped=True)
		for party, age, amount in [
			("Young", 20, 500), ("Mixed", 10, 200),
			("Mixed", 40, 100), ("Old", 150, 300),
		]:
			report.append_row(self.row(age, party, amount))
		report.append_subtotal_row(report.previous_party)
		self.assertNotIn("Young", [row.get("party") for row in report.data])
		self.assertEqual(report.total_row_map["Mixed"]["outstanding"], 100)
		self.assertEqual(report.total_row_map["Total"]["outstanding"], 400)
		self.assertEqual(report.total_row_map["Total"]["range2"], 100)
		self.assertEqual(report.total_row_map["Total"]["range5"], 300)

	def test_no_matches_has_no_subtotal_rows(self):
		report = self.report(["121+"], grouped=True)
		report.append_row(self.row(20))
		report.append_subtotal_row(report.previous_party)
		self.assertEqual(report.data, [])

	def test_credits_preserved_and_zero_balances_removed(self):
		report = self.report(["31-60"])
		for amount in [-50, 0, 0.001, 100]:
			report.append_row(self.row(45, amount=amount))
		self.assertEqual([row.outstanding for row in report.data], [-50, 100])

	def test_custom_ranges_and_serialized_selection(self):
		report = self.report('["16-45", "46+"]', ranges=["15", "45"])
		for age in [15, 16, 45, 46]:
			report.append_row(self.row(age))
		self.assertEqual([row.age for row in report.data], [16, 45, 46])

	def test_stale_selection_is_rejected(self):
		with patch.object(frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				self.report(["31-60"], ranges=["15", "45"])
