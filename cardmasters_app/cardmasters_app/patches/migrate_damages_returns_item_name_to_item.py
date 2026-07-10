import frappe


def execute():
	doctype = "Damages and Returns Item Table"
	table = f"tab{doctype}"

	if not frappe.db.table_exists(doctype):
		return

	if not frappe.db.has_column(doctype, "item_name"):
		return

	if not frappe.db.has_column(doctype, "item"):
		return

	frappe.db.sql(
		f"""
		UPDATE `{table}`
		SET `item` = `item_name`
		WHERE
			(`item` IS NULL OR `item` = '')
			AND `item_name` IS NOT NULL
			AND `item_name` != ''
		"""
	)

	#flush pending transactions safely
	frappe.db.commit()

	frappe.db.sql(f"ALTER TABLE `{table}` DROP COLUMN `item_name`")
