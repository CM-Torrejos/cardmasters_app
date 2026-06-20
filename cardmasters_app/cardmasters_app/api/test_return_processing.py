import frappe
from frappe.tests.utils import FrappeTestCase

from cardmasters_app.cardmasters_app.api.return_processing import (
	_get_value_allocation,
	_validate_damage_rows,
)


class TestReturnProcessing(FrappeTestCase):
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
