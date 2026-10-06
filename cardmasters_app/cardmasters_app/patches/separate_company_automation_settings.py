import frappe
from frappe import _

from cardmasters_app.cardmasters_app.doctype.cardmasters_settings.cardmasters_settings import (
	validate_default_bom_company,
)


def execute():
	if not frappe.db.has_column("Cardmasters Company Settings", "disabled"):
		return
	# Legacy columns remain available after model sync, even though the fields are removed.
	rows = frappe.db.sql(
		"""select name, company, disabled, enable_bom_automation, make_generated_bom_default
		from `tabCardmasters Company Settings` order by company""",
		as_dict=True,
	)
	default_company = frappe.db.get_single_value("Cardmasters Settings", "default_bom_company")
	enabled = [row for row in rows if row.enable_bom_automation and not row.disabled]
	if enabled and not default_company:
		legacy_defaults = [row.company for row in enabled if row.make_generated_bom_default]
		if len(legacy_defaults) == 1:
			default_company = legacy_defaults[0]
		elif len(enabled) == 1:
			default_company = enabled[0].company
		else:
			frappe.throw(_("Cannot migrate BOM automation: select a single Default BOM Company in Cardmasters Settings, then retry migration."))

	validate_default_bom_company([row.company for row in enabled], default_company)
	for row in rows:
		frappe.db.set_value(
			"Cardmasters Company Settings",
			row.name,
			{
				"enable_item_accounting_defaults": int(not row.disabled),
				# Preserve effective legacy behavior; users can enable BOMs independently afterwards.
				"enable_bom_automation": int(bool(row.enable_bom_automation and not row.disabled)),
			},
			update_modified=False,
		)
	if default_company:
		frappe.db.set_single_value("Cardmasters Settings", "default_bom_company", default_company)
	frappe.clear_cache(doctype="Cardmasters Settings")
	frappe.clear_cache(doctype="Cardmasters Company Settings")
