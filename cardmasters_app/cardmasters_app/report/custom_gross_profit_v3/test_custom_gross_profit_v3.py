from unittest import TestCase
from unittest.mock import patch

import frappe

from cardmasters_app.cardmasters_app.report.custom_gross_profit_v3 import custom_gross_profit_v3 as report


class TestManufacturingCostBreakdown(TestCase):
	def item(self, code, qty, basic_amount, **values):
		return frappe._dict(
			{
				"parent": "SE-1",
				"item_code": code,
				"item_name": code,
				"transfer_qty": qty,
				"basic_amount": basic_amount,
				"amount": basic_amount,
				"additional_cost": 0,
				"stock_uom": "Nos",
				"s_warehouse": None,
				"t_warehouse": None,
				"is_finished_item": 0,
				"is_scrap_item": 0,
				**values,
			}
		)

	def entry(self, name="SE-1", qty=10, material_cost=100, extra=20, scrap=0):
		items = [
			self.item("RM", qty * 2, material_cost, s_warehouse="Stores"),
			self.item(
				"FG",
				qty,
				material_cost - scrap,
				is_finished_item=1,
				t_warehouse="FG Stores",
				amount=material_cost - scrap + extra,
				additional_cost=extra,
			),
		]
		if scrap:
			items.append(self.item("SCRAP", 1, scrap, is_scrap_item=1, t_warehouse="Scrap Stores"))
		for item in items:
			item.parent = name
		return frappe._dict(
			name=name,
			work_order="WO-1",
			posting_date="2026-10-01",
			production_items=items,
			consumption_items=[],
		)

	def breakdown(self, entries, qty=5, buying_amount=60):
		with patch.object(report, "_", side_effect=lambda text: text):
			return report.get_cost_breakdown(
				frappe._dict(item_code="FG", qty=qty, buying_amount=buying_amount), entries, "item-1", "PHP"
			)

	def test_partial_sale_scales_materials_and_extra_cost_without_gross_profit_values(self):
		rows = self.breakdown([self.entry()])
		self.assertEqual(rows[0].breakdown_cost, 60)
		self.assertEqual(rows[1].allocated_qty, 10)
		self.assertEqual(rows[1].component_rate, 5)
		self.assertEqual(rows[1].breakdown_cost, 50)
		self.assertEqual(rows[2].breakdown_cost, 10)
		self.assertTrue(all("buying_amount" not in row and "gross_profit" not in row for row in rows))

	def test_all_production_entries_use_quantity_weighted_allocation(self):
		rows = self.breakdown(
			[self.entry(extra=0), self.entry("SE-2", qty=5, material_cost=100, extra=0)], buying_amount=70
		)
		headers = [row for row in rows if row.row_type == "manufacture"]
		self.assertEqual([row.manufacture_entry for row in headers], ["SE-1", "SE-2"])
		self.assertAlmostEqual(sum(row.allocated_qty for row in headers), 5)
		self.assertEqual(sum(row.breakdown_cost for row in headers), 66.666)
		self.assertEqual(rows[-1].row_type, "valuation_difference")
		self.assertEqual(rows[-1].breakdown_cost, 3.334)

	def test_scrap_credit_and_additional_cost_reconcile_to_finished_value(self):
		rows = self.breakdown([self.entry(scrap=10)], buying_amount=55)
		self.assertEqual(next(row.breakdown_cost for row in rows if row.row_type == "scrap"), -5)
		self.assertEqual(sum(row.breakdown_cost for row in rows if row.indent == 3), 55)
		self.assertFalse(any(row.row_type == "valuation_difference" for row in rows))

	def test_returns_reverse_breakdown_and_fully_returned_rows_have_zero_cost(self):
		rows = self.breakdown([self.entry()], qty=-5, buying_amount=-60)
		self.assertEqual(rows[0].breakdown_cost, -60)
		self.assertEqual(rows[1].allocated_qty, -10)
		self.assertEqual(rows[1].breakdown_cost, -50)
		rows = self.breakdown([self.entry()], qty=0, buying_amount=0)
		self.assertTrue(all(row.breakdown_cost == 0 for row in rows))

	def test_consumption_entries_supply_materials_when_manufacture_has_none(self):
		entry = self.entry()
		material = entry.production_items.pop(0)
		material.parent = "SE-CONSUMPTION"
		entry.consumption_items = [material]
		rows = self.breakdown([entry])
		self.assertEqual(rows[1].manufacture_entry, "SE-CONSUMPTION")
		self.assertEqual(rows[1].breakdown_cost, 50)

	def test_multi_output_allocates_only_selected_finished_goods_value_share(self):
		entry = self.entry(extra=0)
		entry.production_items.append(
			self.item("OTHER-FG", 10, 300, is_finished_item=1, t_warehouse="FG Stores")
		)
		entry.production_items[0].basic_amount = 400
		rows = self.breakdown([entry], buying_amount=50)
		self.assertEqual(rows[1].breakdown_cost, 50)
		self.assertFalse(any(row.row_type == "manufacturing_adjustment" for row in rows))

	def test_zero_basic_value_uses_quantity_share_and_displays_adjustment(self):
		entry = self.entry(extra=0)
		entry.production_items[1].basic_amount = entry.production_items[1].amount = 0
		entry.production_items.append(
			self.item("OTHER-FG", 10, 0, is_finished_item=1, t_warehouse="FG Stores")
		)
		rows = self.breakdown([entry], buying_amount=0)
		self.assertEqual(rows[1].breakdown_cost, 25)
		self.assertEqual(rows[-1].row_type, "manufacturing_adjustment")
		self.assertEqual(rows[-1].breakdown_cost, -25)

	def test_unexplained_manufacturing_cost_and_valuation_are_explicit(self):
		entry = self.entry()
		entry.production_items[1].amount = 150
		rows = self.breakdown([entry], buying_amount=80)
		self.assertEqual(
			next(row.breakdown_cost for row in rows if row.row_type == "manufacturing_adjustment"), 15
		)
		self.assertEqual(rows[-1].breakdown_cost, 5)

	def test_duplicate_items_have_unique_tree_ids_and_total_is_unchanged(self):
		generator = report.GrossProfitGenerator.__new__(report.GrossProfitGenerator)
		generator.currency_precision = 3
		generator.si_list = [frappe._dict(indent=0)] + [
			frappe._dict(
				indent=1, so_detail="SOI-1", item_code="FG", cost_accuracy="Costed", qty=5, buying_amount=60
			)
			for _ in range(2)
		]
		generator.production = {("SOI-1", "FG"): [self.entry()]}
		total = frappe._dict(sales_invoice="Total", selling_amount=200, buying_amount=120, gross_profit=80)
		data = [frappe._dict(indent=row.indent, currency="PHP") for row in generator.si_list] + [total]
		with patch.object(report, "_", side_effect=lambda text: text):
			rows = report.add_cost_tree(data, generator)
		ids = [row.report_row_id for row in rows[:-1]]
		self.assertEqual(len(ids), len(set(ids)))
		self.assertIs(rows[-1], total)
		self.assertEqual(rows[-1].gross_profit, 80)
		self.assertEqual(
			[row.parent_row_id for row in rows if row.row_type == "item"], ["report-0", "report-0"]
		)

	def test_disabled_breakdown_keeps_invoice_tree_without_detail_rows(self):
		generator = report.GrossProfitGenerator.__new__(report.GrossProfitGenerator)
		generator.si_list = [
			frappe._dict(indent=0),
			frappe._dict(indent=1, so_detail="SOI-1", item_code="FG"),
		]
		generator.production = {}
		data = [frappe._dict(indent=0), frappe._dict(indent=1), frappe._dict(sales_invoice="Total")]
		self.assertEqual(len(report.add_cost_tree(data, generator, False)), 3)

	def test_loader_matches_finished_item_and_filters_readable_submitted_entries(self):
		generator = report.GrossProfitGenerator.__new__(report.GrossProfitGenerator)
		generator.filters = frappe._dict(company="Company", to_date="2026-10-05")
		generator.si_list = [
			frappe._dict(so_detail="SOI-1", item_code="FG"),
			frappe._dict(so_detail="SOI-1", item_code="OTHER"),
		]
		entry = self.entry()
		entry.purpose = "Manufacture"
		with (
			patch.object(report.frappe, "has_permission", return_value=True),
			patch.object(
				report.frappe,
				"get_list",
				side_effect=[
					[frappe._dict(name="WO-1", sales_order_item="SOI-1")],
					[entry],
				],
			) as get_list,
			patch.object(report.frappe, "get_all", return_value=entry.production_items) as get_all,
		):
			generator.get_manufacture_entries()
		self.assertEqual(generator.si_list[0].manufacture_entry, "SE-1")
		self.assertIsNone(generator.si_list[1].manufacture_entry)
		filters = get_list.call_args_list[1].kwargs["filters"]
		self.assertEqual(filters["docstatus"], 1)
		self.assertEqual(filters["posting_date"], ["<=", "2026-10-05"])
		self.assertEqual(filters["company"], "Company")
		self.assertEqual(get_all.call_args.kwargs["filters"]["parent"], ["in", ["SE-1"]])

	def test_no_stock_entry_read_permission_does_not_load_materials(self):
		generator = report.GrossProfitGenerator.__new__(report.GrossProfitGenerator)
		generator.si_list = [frappe._dict(so_detail="SOI-1")]
		with (
			patch.object(report.frappe, "has_permission", side_effect=[True, False]),
			patch.object(report.frappe, "get_list") as get_list,
			patch.object(report.frappe, "get_all") as get_all,
		):
			generator.get_manufacture_entries()
		get_list.assert_not_called()
		get_all.assert_not_called()
