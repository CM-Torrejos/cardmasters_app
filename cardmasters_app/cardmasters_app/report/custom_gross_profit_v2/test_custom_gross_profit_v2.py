from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from cardmasters_app.cardmasters_app.report.custom_gross_profit_v2.custom_gross_profit_v2 import (
	GrossProfitGenerator,
)


class TestCustomGrossProfitReturnAllocation(TestCase):
	def make_generator(self, returned_invoices=None, legacy_returned_invoices=None):
		generator = GrossProfitGenerator.__new__(GrossProfitGenerator)
		generator.currency_precision = 3
		generator.filters = frappe._dict(group_by="Invoice")
		generator.returned_invoices = frappe._dict(returned_invoices or {})
		generator.legacy_returned_invoices = frappe._dict(legacy_returned_invoices or {})
		return generator

	def test_linked_return_only_changes_referenced_source_row(self):
		invoice = "SINV-RETURN-ROW-MATCH"
		first_item_row = "SII-FIRST"
		second_item_row = "SII-SECOND"
		generator = self.make_generator(
			{
				invoice: frappe._dict(
					{first_item_row: [frappe._dict(qty=-1, base_amount=-100)]}
				)
			}
		)
		first_row = frappe._dict(
			parent=invoice,
			item_code="DUPLICATE-ITEM",
			qty=2,
			base_amount=200,
			buying_rate=50,
			buying_amount=100,
		)
		second_row = frappe._dict(
			parent=invoice,
			item_code="DUPLICATE-ITEM",
			qty=3,
			base_amount=600,
			buying_rate=80,
			buying_amount=240,
		)

		generator.update_return_invoices(second_row, second_item_row)
		generator.update_return_invoices(first_row, first_item_row)

		self.assertEqual((first_row.qty, first_row.base_amount, first_row.buying_amount), (1, 100, 50))
		self.assertEqual(
			(second_row.qty, second_row.base_amount, second_row.buying_amount),
			(3, 600, 240),
		)

	def test_oversized_return_remainder_is_consumed_before_next_row(self):
		invoice = "SINV-RETURN-REMAINDER"
		item_row = "SII-RETURN-REMAINDER"
		returned_item = frappe._dict(qty=-2.5, base_amount=-250)
		generator = self.make_generator(
			{invoice: frappe._dict({item_row: [returned_item]})}
		)
		first_row = frappe._dict(
			parent=invoice,
			item_code="DUPLICATE-ITEM",
			qty=1,
			base_amount=100,
			buying_rate=50,
			buying_amount=50,
		)
		second_row = frappe._dict(
			parent=invoice,
			item_code="DUPLICATE-ITEM",
			qty=2,
			base_amount=200,
			buying_rate=50,
			buying_amount=100,
		)

		generator.update_return_invoices(first_row, item_row)
		self.assertEqual((returned_item.qty, returned_item.base_amount), (-1.5, -150))

		generator.update_return_invoices(second_row, item_row)

		self.assertEqual((returned_item.qty, returned_item.base_amount), (0, 0))
		self.assertEqual((first_row.qty, first_row.base_amount), (0, 0))
		self.assertEqual((second_row.qty, second_row.base_amount), (0.5, 50))

	def test_legacy_return_spills_across_distinct_duplicate_item_rows(self):
		invoice = "SINV-LEGACY-RETURN"
		linked_item_row = "SII-LINKED"
		unlinked_item_row = "SII-UNLINKED"
		item_code = "DUPLICATE-ITEM"
		generator = self.make_generator(
			{
				invoice: frappe._dict(
					{linked_item_row: [frappe._dict(qty=-1, base_amount=-100)]}
				)
			},
			{
				invoice: frappe._dict(
					{item_code: [frappe._dict(qty=-2, base_amount=-200)]}
				)
			},
		)
		linked_row = frappe._dict(
			parent=invoice,
			item_code=item_code,
			item_row=linked_item_row,
			is_return=False,
			qty=3,
			base_amount=300,
			buying_rate=50,
			buying_amount=150,
		)
		unlinked_row = frappe._dict(
			parent=invoice,
			item_code=item_code,
			item_row=unlinked_item_row,
			is_return=False,
			qty=1,
			base_amount=100,
			buying_rate=50,
			buying_amount=50,
		)
		generator.si_list = [unlinked_row, linked_row]

		generator.allocate_legacy_return_items()
		generator.update_return_invoices(linked_row, linked_item_row)
		generator.update_return_invoices(unlinked_row, unlinked_item_row)

		self.assertEqual((linked_row.qty, linked_row.base_amount), (1, 100))
		self.assertEqual((unlinked_row.qty, unlinked_row.base_amount), (0, 0))

	def test_monthly_group_allocates_legacy_return_before_month_is_derived(self):
		invoice = "SINV-MONTHLY-LEGACY-RETURN"
		item_row = "SII-MONTHLY"
		item_code = "DUPLICATE-ITEM"
		generator = self.make_generator(
			legacy_returned_invoices={
				invoice: frappe._dict(
					{item_code: [frappe._dict(qty=-1, base_amount=-100)]}
				)
			}
		)
		generator.filters = frappe._dict(group_by="Monthly")
		invoice_row = frappe._dict(
			parent=invoice,
			item_code=item_code,
			item_row=item_row,
			is_return=False,
			qty=1,
			base_amount=100,
			buying_rate=50,
			buying_amount=50,
		)
		generator.si_list = [invoice_row]

		generator.allocate_legacy_return_items()
		generator.update_return_invoices(invoice_row, item_row)

		self.assertEqual((invoice_row.qty, invoice_row.base_amount), (0, 0))

	def test_loader_adds_linked_return_when_source_invoice_is_not_loaded(self):
		generator = GrossProfitGenerator.__new__(GrossProfitGenerator)
		generator.filters = frappe._dict(
			company="CARDMASTERS CDO",
			from_date="2026-07-01",
			to_date="2026-07-31",
			group_by="Invoice",
			include_returned_invoices=1,
		)
		invoice_row = frappe._dict(parent="SINV-IN-PERIOD")
		return_row = frappe._dict(parent="SINV-RETURN-OUTSIDE-SOURCE")
		db = MagicMock()
		db.sql.side_effect = [[invoice_row], [return_row]]

		module = "cardmasters_app.cardmasters_app.report.custom_gross_profit_v2.custom_gross_profit_v2"
		with (
			patch.object(frappe.local, "db", db, create=True),
			patch(f"{module}.get_accounting_dimensions", return_value=[]),
			patch(f"{module}.get_match_cond", return_value=""),
		):
			generator.load_invoice_items()

		self.assertEqual(generator.si_list, [invoice_row, return_row])
		self.assertEqual(generator.filters.vouchers_to_ignore, ("SINV-IN-PERIOD",))
		return_query = db.sql.call_args_list[1].args[0]
		self.assertIn("is_return = 1 and return_against is not null", return_query)
		self.assertIn("return_against not in %(vouchers_to_ignore)s", return_query)
