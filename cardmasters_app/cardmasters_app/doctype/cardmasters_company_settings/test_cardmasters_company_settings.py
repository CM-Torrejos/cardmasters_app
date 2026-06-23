# Copyright (c) 2026, Shan Torrejos and contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from cardmasters_app.cardmasters_app.doctype.cardmasters_company_settings.cardmasters_company_settings import (
	CardmastersCompanySettings,
	_validate_cost_center,
	_validate_income_account,
	_validate_warehouse,
)


class TestCardmastersCompanySettings(FrappeTestCase):
	def test_duplicate_item_group_mapping_is_rejected(self):
		settings = frappe._dict(
			item_group_account_mappings=[
				frappe._dict(item_group="Garments"),
				frappe._dict(item_group="Garments"),
			]
		)

		with self.assertRaises(frappe.ValidationError):
			CardmastersCompanySettings.validate_unique_item_groups(settings)

	@patch("frappe.db.get_value")
	def test_income_account_must_belong_to_company(self, get_value):
		get_value.return_value = frappe._dict(
			company="Another Company",
			root_type="Income",
			is_group=0,
			disabled=0,
		)

		with self.assertRaises(frappe.ValidationError):
			_validate_income_account("Sales - AC", "Cardmasters", 1)

	@patch("frappe.db.get_value")
	def test_group_cost_center_is_rejected(self, get_value):
		get_value.return_value = frappe._dict(company="Cardmasters", is_group=1, disabled=0)

		with self.assertRaises(frappe.ValidationError):
			_validate_cost_center("Main - CM", "Cardmasters", 1, "Buying Cost Center")

	@patch("frappe.db.get_value")
	def test_return_warehouse_must_belong_to_company(self, get_value):
		get_value.return_value = frappe._dict(company="Another Company", is_group=0, disabled=0)

		with self.assertRaises(frappe.ValidationError):
			_validate_warehouse("Returns - AC", "Cardmasters", "Return Warehouse")
