import frappe
from frappe import _


LEGACY_FIELDS = ("return_warehouse", "master_warehouse", "damage_warehouse")


def execute():
	legacy_rows = frappe.db.sql(
		"""
		select field, value
		from `tabSingles`
		where doctype = %s
			and field in (%s, %s, %s)
		""",
		("Cardmasters Settings", *LEGACY_FIELDS),
		as_dict=True,
	)
	legacy_values = {row.field: row.value for row in legacy_rows if row.value}
	if not legacy_values:
		return

	companies = set()
	for fieldname, warehouse in legacy_values.items():
		company = frappe.db.get_value("Warehouse", warehouse, "company")
		if not company:
			frappe.throw(
				_("Cannot migrate legacy {0}: Warehouse {1} does not exist or has no Company.").format(
					frappe.bold(fieldname), frappe.bold(warehouse)
				)
			)
		companies.add(company)

	if len(companies) != 1:
		frappe.throw(
			_("Legacy Sales Return warehouses belong to different companies and cannot be migrated automatically."),
			title=_("Invalid Return Warehouse Configuration"),
		)

	company = companies.pop()
	settings_name = frappe.db.exists("Cardmasters Company Settings", {"company": company})
	if settings_name:
		frappe.db.set_value(
			"Cardmasters Company Settings",
			settings_name,
			legacy_values,
			update_modified=False,
		)
	else:
		settings = frappe.new_doc("Cardmasters Company Settings")
		settings.company = company
		settings.disabled = 1
		settings.update(legacy_values)
		settings.insert(ignore_permissions=True)

	frappe.db.sql(
		"""
		delete from `tabSingles`
		where doctype = %s
			and field in (%s, %s, %s)
		""",
		("Cardmasters Settings", *LEGACY_FIELDS),
	)
	frappe.clear_cache(doctype="Cardmasters Settings")
	frappe.clear_cache(doctype="Cardmasters Company Settings")
