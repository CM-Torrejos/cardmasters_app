# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CardmastersSettings(Document):
	def validate(self):
		enabled_companies = frappe.get_all(
			"Cardmasters Company Settings",
			filters={"enable_bom_automation": 1},
			pluck="company",
		)
		validate_default_bom_company(enabled_companies, self.default_bom_company)


def validate_default_bom_company(enabled_companies, default_company):
	if not enabled_companies:
		return
	if not default_company:
		frappe.throw(
			_("Select Default BOM Company in Cardmasters Settings before enabling BOM automation."),
			title=_("Missing Default BOM Company"),
		)
	if default_company not in enabled_companies:
		frappe.throw(
			_("Default BOM Company {0} must have BOM automation enabled. Select another enabled company in Cardmasters Settings before disabling it.").format(
				frappe.bold(default_company)
			),
			title=_("Invalid Default BOM Company"),
		)
