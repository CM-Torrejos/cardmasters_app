"""Rename the withdrawal draft and recover interrupted table renames."""

import importlib
import sys

import frappe


def execute():
	rename_draft((("Print Pass", "Withdrawal"), ("Print Pass Work Order", "Withdrawal Work Order")))


def rename_draft(pairs):
	for old, new in pairs:
		if frappe.db.exists("DocType", old) and frappe.db.exists("DocType", new):
			frappe.throw(f"Cannot rename {old}: {new} already exists.")
		# A metadata save can commit before Frappe reaches the table rename.
		if frappe.db.exists("DocType", new) and not frappe.db.table_exists(new) and frappe.db.table_exists(old):
			frappe.db.rename_table(old, new)
			frappe.db.commit()

	previous_patch_flag = frappe.flags.in_patch
	previous_import_flag = frappe.flags.in_import
	frappe.flags.in_patch = True
	frappe.flags.in_import = True
	aliases = {}
	try:
		for old, new in pairs:
			old_name, new_name = frappe.scrub(old), frappe.scrub(new)
			old_module = f"cardmasters_app.cardmasters_app.doctype.{old_name}.{old_name}"
			aliases[old_module] = sys.modules.get(old_module)
			sys.modules[old_module] = importlib.import_module(
				f"cardmasters_app.cardmasters_app.doctype.{new_name}.{new_name}"
			)
		# Parent first: its child table must still exist during parenttype updates.
		for old, new in pairs:
			if frappe.db.exists("DocType", old):
				frappe.rename_doc("DocType", old, new, force=True)
	finally:
		frappe.flags.in_patch = previous_patch_flag
		frappe.flags.in_import = previous_import_flag
		for module, previous in aliases.items():
			if previous is None:
				sys.modules.pop(module, None)
			else:
				sys.modules[module] = previous
