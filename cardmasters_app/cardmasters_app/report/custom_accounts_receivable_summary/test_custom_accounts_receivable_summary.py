from unittest import TestCase
from unittest.mock import patch

import frappe

from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	AccountsReceivableSummary,
)

from cardmasters_app.cardmasters_app.report.custom_accounts_receivable_summary.custom_accounts_receivable_summary import (
	CustomAccountsReceivableSummary,
)


class TestCustomAccountsReceivableSummary(TestCase):
	def report(self, selection=None, ranges=None):
		report = object.__new__(CustomAccountsReceivableSummary)
		report.filters = frappe._dict(selected_ageing_buckets=selection)
		report.ranges = ranges or ["30", "60", "90", "120"]
		report.currency_precision = 2
		return report

	def run_summary(self, report, rows):
		def upstream_run(instance, args):
			instance.data = rows
			return [{"fieldname": "party"}], rows

		with patch.object(AccountsReceivableSummary, "run", upstream_run):
			return report.run({})[1]

	def test_filters_customers_and_preserves_full_summary(self):
		young = frappe._dict(party="Young", range1=500, range2=0, outstanding=500)
		mixed = frappe._dict(party="Mixed", range1=200, range2=100, outstanding=300, advance=20)
		old = frappe._dict(party="Old", range5=400, outstanding=400)
		rows = self.run_summary(self.report(["31-60", "121+"]), [young, mixed, old])
		self.assertEqual([row.party for row in rows], ["Mixed", "Old"])
		self.assertIs(rows[0], mixed)
		self.assertEqual(rows[0].range1, 200)
		self.assertEqual(rows[0].advance, 20)
		self.assertEqual(sum(row.outstanding for row in rows), 700)

	def test_no_selection_preserves_all_rows(self):
		rows = [frappe._dict(party="Not yet due", outstanding=100)]
		self.assertIs(self.run_summary(self.report(), rows), rows)

	def test_zero_net_bucket_is_excluded_after_aggregation(self):
		report = self.report(["31-60"])
		report.range_numbers = list(range(1, 6))
		report.receivables = [
			frappe._dict(party="Offset", party_type="Customer", currency="PHP", range2=100, outstanding=100),
			frappe._dict(party="Offset", party_type="Customer", currency="PHP", range2=-100, outstanding=-100),
			frappe._dict(party="Offset", party_type="Customer", currency="PHP", range1=50, outstanding=50),
		]
		report.get_party_total({})
		rows = list(report.party_total.values())
		self.assertEqual(rows[0].outstanding, 50)
		self.assertEqual(self.run_summary(report, rows), [])

	def test_any_selected_bucket_matches_even_when_buckets_offset(self):
		row = frappe._dict(range2=100, range3=-100, outstanding=50)
		self.assertEqual(self.run_summary(self.report(["31-60", "61-90"]), [row]), [row])

	def test_credits_precision_and_not_due(self):
		rows = [frappe._dict(range2=value) for value in [-10, 0, 0.001, 10]]
		rows.append(frappe._dict(outstanding=500))
		self.assertEqual(self.run_summary(self.report(["31-60"]), rows), [rows[0], rows[3]])

	def test_custom_ranges_and_serialized_selection(self):
		report = self.report('["16-45", "46+"]', ["15", "45"])
		self.assertEqual(report.get_selected_ageing_fields(), ["range2", "range3"])

	def test_invalid_selection_rejected(self):
		for selection in [["31-60"], {"range2": True}, [None]]:
			with self.subTest(selection=selection):
				with patch.object(frappe, "throw", side_effect=ValueError):
					with self.assertRaises(ValueError):
						self.report(selection, ["15", "45"]).get_selected_ageing_fields()
