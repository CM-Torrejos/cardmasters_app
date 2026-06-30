# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CardmastersCompanySettings(Document):
	def validate(self):
		self.validate_company()
		self.validate_unique_item_groups()
		self.validate_accounting_dimensions()
		self.validate_bom_automation()
		self.validate_return_warehouses()

	def validate_company(self):
		if frappe.db.get_value("Company", self.company, "is_group", cache=True):
			frappe.throw(
				_("Company {0} is a group company and cannot have Item accounting defaults.").format(
					frappe.bold(self.company)
				)
			)

	def validate_unique_item_groups(self):
		seen = set()
		for row in self.item_group_account_mappings:
			if row.item_group in seen:
				frappe.throw(
					_("Item Group {0} is mapped more than once.").format(frappe.bold(row.item_group)),
					title=_("Duplicate Item Group Mapping"),
				)
			seen.add(row.item_group)

	def validate_accounting_dimensions(self):
		for row in self.item_group_account_mappings:
			_validate_warehouse(row.default_warehouse, self.company, _("Default Warehouse"))
			_validate_income_account(row.income_account, self.company, row.idx)
			_validate_cost_center(row.buying_cost_center, self.company, row.idx, _("Buying Cost Center"))
			_validate_cost_center(row.selling_cost_center, self.company, row.idx, _("Selling Cost Center"))

	def validate_return_warehouses(self):
		for fieldname, label in (
			("return_warehouse", _("Return Warehouse")),
			("dnr_holding_warehouse", _("DNR Holding Warehouse")),
			("master_warehouse", _("Master Warehouse")),
			("damage_warehouse", _("Damage Warehouse")),
		):
			warehouse = self.get(fieldname)
			if warehouse:
				_validate_warehouse(warehouse, self.company, label)

	def validate_bom_automation(self):
		if not self.enable_bom_automation:
			if self.make_generated_bom_default:
				frappe.throw(_("Enable BOM Automation before marking its generated BOM as default."))
			return

		if not self.default_bom_component:
			frappe.throw(_("Placeholder BOM Component is required when BOM Automation is enabled."))
		if not self.default_bom_source_warehouse:
			frappe.throw(_("Placeholder Source Warehouse is required when BOM Automation is enabled."))
		if flt(self.default_bom_component_qty) <= 0:
			frappe.throw(_("Placeholder Quantity must be greater than zero."))

		item_details = frappe.db.get_value(
			"Item",
			self.default_bom_component,
			["disabled", "is_stock_item", "stock_uom"],
			as_dict=True,
			cache=True,
		)
		if not item_details:
			frappe.throw(
				_("Placeholder BOM Component {0} does not exist.").format(
					frappe.bold(self.default_bom_component)
				)
			)
		if item_details.disabled or not item_details.is_stock_item or not item_details.stock_uom:
			frappe.throw(
				_("Placeholder BOM Component {0} must be an enabled stock Item with a Stock UOM.").format(
					frappe.bold(self.default_bom_component)
				)
			)

		_validate_warehouse(
			self.default_bom_source_warehouse,
			self.company,
			_("Placeholder Source Warehouse"),
		)

		if self.make_generated_bom_default:
			other_default_company = frappe.db.get_value(
				"Cardmasters Company Settings",
				{
					"name": ("!=", self.name or ""),
					"enable_bom_automation": 1,
					"make_generated_bom_default": 1,
				},
				"company",
			)
			if other_default_company:
				frappe.throw(
					_("Company {0} is already configured to generate the default BOM.").format(
						frappe.bold(other_default_company)
					),
					title=_("Duplicate Default BOM Company"),
				)


def _validate_income_account(account: str, company: str, row_number: int) -> None:
	account_details = frappe.db.get_value(
		"Account",
		account,
		["company", "root_type", "is_group", "disabled"],
		as_dict=True,
		cache=True,
	)
	if not account_details:
		frappe.throw(_("Row #{0}: Income Account {1} does not exist.").format(row_number, frappe.bold(account)))
	if account_details.company != company:
		frappe.throw(
			_("Row #{0}: Income Account {1} does not belong to Company {2}.").format(
				row_number, frappe.bold(account), frappe.bold(company)
			)
		)
	if account_details.root_type != "Income" or account_details.is_group or account_details.disabled:
		frappe.throw(
			_("Row #{0}: Income Account {1} must be an enabled, non-group Income account.").format(
				row_number, frappe.bold(account)
			)
		)


def _validate_cost_center(cost_center: str, company: str, row_number: int, label: str) -> None:
	cost_center_details = frappe.db.get_value(
		"Cost Center",
		cost_center,
		["company", "is_group", "disabled"],
		as_dict=True,
		cache=True,
	)
	if not cost_center_details:
		frappe.throw(_("Row #{0}: {1} {2} does not exist.").format(row_number, label, frappe.bold(cost_center)))
	if cost_center_details.company != company:
		frappe.throw(
			_("Row #{0}: {1} {2} does not belong to Company {3}.").format(
				row_number, label, frappe.bold(cost_center), frappe.bold(company)
			)
		)
	if cost_center_details.is_group or cost_center_details.disabled:
		frappe.throw(
			_("Row #{0}: {1} {2} must be enabled and cannot be a group.").format(
				row_number, label, frappe.bold(cost_center)
			)
		)


def _validate_warehouse(warehouse: str, company: str, label: str) -> None:
	if not warehouse:
		frappe.throw(_("{0} is required.").format(label))
	warehouse_details = frappe.db.get_value(
		"Warehouse",
		warehouse,
		["company", "is_group", "disabled"],
		as_dict=True,
		cache=True,
	)
	if not warehouse_details:
		frappe.throw(_("{0} {1} does not exist.").format(label, frappe.bold(warehouse)))
	if warehouse_details.company != company:
		frappe.throw(
			_("{0} {1} does not belong to Company {2}.").format(
				label, frappe.bold(warehouse), frappe.bold(company)
			)
		)
	if warehouse_details.is_group or warehouse_details.disabled:
		frappe.throw(
			_("{0} {1} must be enabled and cannot be a group.").format(label, frappe.bold(warehouse))
		)
