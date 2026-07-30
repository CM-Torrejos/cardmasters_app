# Copyright (c) 2026, Shan Torrejos and contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from cardmasters_app.cardmasters_app.event_handlers.item import (
	apply_accounting_defaults,
	create_company_boms,
)


class ItemStub:
	def __init__(self, item_group, item_defaults=None):
		self.item_group = item_group
		self.item_defaults = item_defaults or []

	def append(self, fieldname, values):
		assert fieldname == "item_defaults"
		row = frappe._dict(values)
		self.item_defaults.append(row)
		return row


class TestItemAccountingDefaults(FrappeTestCase):
	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_doc")
	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_all")
	def test_applies_one_mapping_per_enabled_company(self, get_all, get_doc):
		get_all.return_value = ["Cardmasters CDO", "Cardmasters Manila"]
		get_doc.side_effect = [
			make_configuration("Cardmasters CDO", "Garments", "Sales - CDO", "Garments - CDO"),
			make_configuration("Cardmasters Manila", "Garments", "Sales - MNL", "Garments - MNL"),
		]
		item = ItemStub("Garments")

		apply_accounting_defaults(item)

		self.assertEqual(len(item.item_defaults), 2)
		self.assertEqual(item.item_defaults[0].default_warehouse, "Main - CDO")
		self.assertEqual(item.item_defaults[0].income_account, "Sales - CDO")
		self.assertEqual(item.item_defaults[1].selling_cost_center, "Garments - MNL")

	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_doc")
	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_all")
	def test_updates_existing_company_row_and_preserves_other_defaults(self, get_all, get_doc):
		get_all.return_value = ["Cardmasters CDO"]
		get_doc.return_value = make_configuration(
			"Cardmasters CDO", "Garments", "Sales - CDO", "Garments - CDO"
		)
		existing = frappe._dict(company="Cardmasters CDO", default_warehouse="Main - CDO")
		item = ItemStub("Garments", [existing])

		apply_accounting_defaults(item)

		self.assertEqual(len(item.item_defaults), 1)
		self.assertEqual(existing.default_warehouse, "Main - CDO")
		self.assertEqual(existing.income_account, "Sales - CDO")

	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_doc")
	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_all")
	def test_missing_mapping_blocks_item_creation(self, get_all, get_doc):
		get_all.return_value = ["Cardmasters CDO"]
		get_doc.return_value = frappe._dict(
			company="Cardmasters CDO",
			item_group_account_mappings=[],
		)

		with self.assertRaises(frappe.ValidationError):
			apply_accounting_defaults(ItemStub("Garments"))

	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_all")
	def test_non_stock_item_does_not_create_bom(self, get_all):
		create_company_boms(frappe._dict(name="SERVICE-001", is_stock_item=0))

		get_all.assert_not_called()

	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_cached_value")
	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.new_doc")
	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_all")
	def test_creates_company_boms_and_submits_global_default_last(
		self, get_all, new_doc, get_cached_value
	):
		get_all.return_value = [
			make_bom_configuration("Cardmasters CDO", make_default=1),
			make_bom_configuration("Cardmasters Manila", make_default=0),
		]
		created_boms = [BOMStub(), BOMStub()]
		new_doc.side_effect = created_boms
		get_cached_value.side_effect = lambda doctype, name, fieldname: (
			"Nos" if doctype == "Item" else "PHP"
		)

		create_company_boms(frappe._dict(name="FG-001", is_stock_item=1))

		self.assertEqual(created_boms[0].company, "Cardmasters Manila")
		self.assertEqual(created_boms[0].is_default, 0)
		self.assertEqual(created_boms[1].company, "Cardmasters CDO")
		self.assertEqual(created_boms[1].is_default, 1)
		self.assertEqual(created_boms[0].items[0].source_warehouse, "Stores - CM")
		self.assertTrue(all(bom.inserted and bom.submitted for bom in created_boms))

	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_all")
	def test_bom_automation_requires_one_global_default_company(self, get_all):
		get_all.return_value = [make_bom_configuration("Cardmasters CDO", make_default=0)]

		with self.assertRaises(frappe.ValidationError):
			create_company_boms(frappe._dict(name="FG-001", is_stock_item=1))

	@patch("cardmasters_app.cardmasters_app.event_handlers.item.frappe.get_all")
	def test_bom_automation_ignores_disabled_company_settings(self, get_all):
		get_all.return_value = []

		create_company_boms(frappe._dict(name="FG-001", is_stock_item=1))

		get_all.assert_called_once()
		self.assertEqual(get_all.call_args.kwargs["filters"], {"disabled": 0, "enable_bom_automation": 1})


def make_configuration(company, item_group, income_account, cost_center):
	warehouse = "Main - CDO" if company == "Cardmasters CDO" else "Main - MNL"
	return frappe._dict(
		company=company,
		item_group_account_mappings=[
			frappe._dict(
				item_group=item_group,
				default_warehouse=warehouse,
				income_account=income_account,
				buying_cost_center=cost_center,
				selling_cost_center=cost_center,
			)
		],
	)


def make_bom_configuration(company, make_default):
	return frappe._dict(
		company=company,
		default_bom_component="NEW-BOM",
		default_bom_component_qty=1,
		default_bom_source_warehouse="Stores - CM",
		make_generated_bom_default=make_default,
	)


class BOMStub:
	def __init__(self):
		self.items = []
		self.inserted = False
		self.submitted = False

	def append(self, fieldname, values):
		assert fieldname == "items"
		self.items.append(frappe._dict(values))

	def insert(self, ignore_permissions=False):
		self.inserted = ignore_permissions

	def submit(self):
		self.submitted = True
