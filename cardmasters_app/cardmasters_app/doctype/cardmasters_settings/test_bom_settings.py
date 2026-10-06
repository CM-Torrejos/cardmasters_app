from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from cardmasters_app.cardmasters_app.doctype.cardmasters_company_settings.cardmasters_company_settings import (
	CardmastersCompanySettings,
)
from cardmasters_app.cardmasters_app.doctype.cardmasters_settings.cardmasters_settings import (
	CardmastersSettings,
	validate_default_bom_company,
)
from cardmasters_app.cardmasters_app.patches.separate_company_automation_settings import execute


class TestBOMSettings(FrappeTestCase):
	def test_default_can_be_selected_before_enabling_automation(self):
		validate_default_bom_company([], "ADMASTERS")

	def test_enabled_automation_requires_default(self):
		with self.assertRaises(frappe.ValidationError):
			validate_default_bom_company(["ADMASTERS"], None)

	def test_default_must_be_an_enabled_company(self):
		with self.assertRaises(frappe.ValidationError):
			validate_default_bom_company(["ADMASTERS"], "CARDMASTERS CDO")

	@patch("frappe.db.get_single_value", return_value="ADMASTERS")
	@patch("frappe.get_all", return_value=[])
	def test_enabling_selected_company_uses_unsaved_switch(self, get_all, get_single_value):
		doc = frappe._dict(company="ADMASTERS", enable_bom_automation=1)
		CardmastersCompanySettings.validate_shared_bom_default(doc)

	@patch("frappe.db.get_single_value", return_value="ADMASTERS")
	@patch("frappe.get_all", return_value=["CARDMASTERS CDO"])
	def test_disabling_default_company_is_rejected_while_other_company_enabled(self, get_all, get_value):
		doc = frappe._dict(company="ADMASTERS", enable_bom_automation=0)
		with self.assertRaises(frappe.ValidationError):
			CardmastersCompanySettings.validate_shared_bom_default(doc)

	@patch("frappe.db.get_single_value", return_value="ADMASTERS")
	@patch("frappe.get_all", return_value=["CARDMASTERS CDO"])
	def test_removing_default_company_is_rejected(self, get_all, get_value):
		doc = frappe._dict(company="ADMASTERS", enable_bom_automation=1)
		with self.assertRaises(frappe.ValidationError):
			CardmastersCompanySettings.validate_shared_bom_default(doc, removing=True)

	@patch("frappe.get_all", return_value=["ADMASTERS", "CARDMASTERS CDO"])
	def test_shared_selector_can_switch_between_enabled_companies(self, get_all):
		CardmastersSettings.validate(frappe._dict(default_bom_company="ADMASTERS"))
		CardmastersSettings.validate(frappe._dict(default_bom_company="CARDMASTERS CDO"))
		with self.assertRaises(frappe.ValidationError):
			CardmastersSettings.validate(frappe._dict(default_bom_company=None))

	@patch("frappe.clear_cache")
	@patch("frappe.db.set_single_value")
	@patch("frappe.db.set_value")
	@patch("frappe.db.get_single_value", return_value=None)
	@patch("frappe.db.sql")
	@patch("frappe.db.has_column", return_value=True)
	def test_migration_preserves_effective_switches_and_default(
		self, has_column, sql, get_single, set_value, set_single, clear_cache
	):
		sql.return_value = [
			frappe._dict(name="ADMASTERS", company="ADMASTERS", disabled=1,
				enable_bom_automation=1, make_generated_bom_default=0),
			frappe._dict(name="CARDMASTERS CDO", company="CARDMASTERS CDO", disabled=0,
				enable_bom_automation=1, make_generated_bom_default=1),
		]
		execute()
		self.assertEqual(set_value.call_args_list[0].args[2], {
			"enable_item_accounting_defaults": 0, "enable_bom_automation": 0
		})
		self.assertEqual(set_value.call_args_list[1].args[2], {
			"enable_item_accounting_defaults": 1, "enable_bom_automation": 1
		})
		set_single.assert_called_once_with("Cardmasters Settings", "default_bom_company", "CARDMASTERS CDO")

	@patch("frappe.db.sql")
	@patch("frappe.db.has_column", return_value=False)
	def test_fresh_install_does_not_read_legacy_columns(self, has_column, sql):
		execute()
		sql.assert_not_called()
