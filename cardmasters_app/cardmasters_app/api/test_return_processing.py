from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from cardmasters_app.cardmasters_app.api.return_processing import (
	_get_value_allocation,
	_validate_damage_rows,
	get_cardmasters_return_warehouses,
)


class TestReturnProcessing(FrappeTestCase):
	@patch("cardmasters_app.cardmasters_app.api.return_processing.frappe.db.get_value")
	def test_return_warehouses_are_loaded_for_transaction_company(self, get_value):
		get_value.return_value = frappe._dict(
			return_warehouse="Returns - CM",
			master_warehouse="Main - CM",
			damage_warehouse="Damages - CM",
		)

		settings = get_cardmasters_return_warehouses(
			"Cardmasters", require_master=True, require_damage=True
		)

		self.assertEqual(settings.return_warehouse, "Returns - CM")
		get_value.assert_called_once_with(
			"Cardmasters Company Settings",
			{"company": "Cardmasters"},
			["master_warehouse", "return_warehouse", "damage_warehouse"],
			as_dict=True,
		)

	@patch("cardmasters_app.cardmasters_app.api.return_processing.frappe.db.get_value")
	def test_missing_company_return_settings_are_rejected(self, get_value):
		get_value.return_value = None

		with self.assertRaises(frappe.ValidationError):
			get_cardmasters_return_warehouses("Cardmasters")

	@patch("cardmasters_app.cardmasters_app.api.return_processing.frappe.db.get_value")
	def test_return_warehouse_is_optional_fallback(self, get_value):
		get_value.return_value = frappe._dict(
			return_warehouse=None,
			master_warehouse="Main - CM",
			damage_warehouse="Damages - CM",
		)

		settings = get_cardmasters_return_warehouses("Cardmasters")

		self.assertIsNone(settings.return_warehouse)
		self.assertEqual(settings.master_warehouse, "Main - CM")

	def test_damage_rows_are_summed(self):
		self.assertEqual(_validate_damage_rows([{"qty": 2}, {"qty": 1.5}], 10), 3.5)

	def test_damage_rows_cannot_exceed_returned_quantity(self):
		with self.assertRaises(frappe.ValidationError):
			_validate_damage_rows([{"qty": 10.1}], 10)

	def test_mixed_value_allocation_preserves_source_cost(self):
		allocation = _get_value_allocation(source_qty=10, source_valuation_rate=12.5, damage_qty=3)

		self.assertEqual(allocation.source_value, 125)
		self.assertEqual(allocation.damage_value, 37.5)
		self.assertEqual(allocation.conversion_value, 87.5)
		self.assertEqual(
			allocation.source_value,
			allocation.damage_value + allocation.conversion_value,
		)
