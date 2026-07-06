import frappe
from frappe import _
from frappe.utils import flt


def apply_accounting_defaults(doc, method=None):
	"""Apply enabled, company-specific accounting mappings to a new Item."""
	if not doc.item_group:
		return

	configuration_names = frappe.get_all(
		"Cardmasters Company Settings",
		filters={"disabled": 0},
		pluck="name",
		order_by="company asc",
	)
	if not configuration_names:
		return

	# Preserve ERPNext's native Item Group defaults before adding configured rows.
	# Item.validate() would otherwise skip them once this handler populates item_defaults.
	if not doc.item_defaults and hasattr(doc, "update_defaults_from_item_group"):
		doc.update_defaults_from_item_group()

	existing_defaults = _get_existing_defaults_by_company(doc)
	for configuration_name in configuration_names:
		configuration = frappe.get_doc("Cardmasters Company Settings", configuration_name)
		mapping = next(
			(
				row
				for row in configuration.item_group_account_mappings
				if row.item_group == doc.item_group
			),
			None,
		)
		if not mapping:
			frappe.throw(
				_("No Item accounting mapping exists for Item Group {0} in Company {1}.").format(
					frappe.bold(doc.item_group), frappe.bold(configuration.company)
				),
				title=_("Missing Item Accounting Mapping"),
			)

		item_default = existing_defaults.get(configuration.company)
		if not item_default:
			item_default = doc.append("item_defaults", {"company": configuration.company})
			existing_defaults[configuration.company] = item_default

		item_default.update(
			{
				"default_warehouse": mapping.default_warehouse,
				"income_account": mapping.income_account,
				"buying_cost_center": mapping.buying_cost_center,
				"selling_cost_center": mapping.selling_cost_center,
			}
		)


def _get_existing_defaults_by_company(doc):
	existing_defaults = {}
	for row in doc.item_defaults:
		if row.company in existing_defaults:
			frappe.throw(
				_("Cannot set multiple Item Defaults for Company {0}.").format(frappe.bold(row.company)),
				title=_("Duplicate Item Defaults"),
			)
		existing_defaults[row.company] = row
	return existing_defaults


def create_company_boms(doc, method=None):
	"""Create and submit one configured BOM per company for a new stock Item."""
	if not doc.is_stock_item:
		return

	configurations = frappe.get_all(
		"Cardmasters Company Settings",
		filters={"enable_bom_automation": 1},
		fields=[
			"company",
			"default_bom_component",
			"default_bom_component_qty",
			"default_bom_source_warehouse",
			"make_generated_bom_default",
		],
		order_by="company asc",
	)
	if not configurations:
		return

	default_configurations = [row for row in configurations if row.make_generated_bom_default]
	if len(default_configurations) != 1:
		frappe.throw(
			_("Exactly one BOM-enabled company must have Make Generated BOM the Default checked."),
			title=_("Invalid BOM Automation Configuration"),
		)

	# Submit the designated default last. ERPNext's default BOM is global per Item,
	# so its submission must supersede any default assigned automatically to the first BOM.
	configurations.sort(key=lambda row: bool(row.make_generated_bom_default))
	for configuration in configurations:
		if configuration.default_bom_component == doc.name:
			frappe.throw(
				_("Item {0} cannot use itself as its placeholder BOM component for Company {1}.").format(
					frappe.bold(doc.name), frappe.bold(configuration.company)
				),
				title=_("Invalid Placeholder BOM Component"),
			)

		component_uom = frappe.get_cached_value(
			"Item", configuration.default_bom_component, "stock_uom"
		)
		bom = frappe.new_doc("BOM")
		bom.item = doc.name
		bom.company = configuration.company
		bom.currency = frappe.get_cached_value(
			"Company", configuration.company, "default_currency"
		)
		bom.is_active = 1
		bom.is_default = configuration.make_generated_bom_default
		bom.append(
			"items",
			{
				"item_code": configuration.default_bom_component,
				"qty": flt(configuration.default_bom_component_qty),
				"uom": component_uom,
				"source_warehouse": configuration.default_bom_source_warehouse,
			},
		)
		bom.insert(ignore_permissions=True)
		bom.submit()
