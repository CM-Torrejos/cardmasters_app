import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe.utils import cint


class CustomStockEntry(StockEntry):
	def check_if_operations_completed(self):
		"""Skip Job Card completion checks when Job Cards are disabled."""
		if cint(frappe.db.get_single_value("Cardmasters Settings", "disable_job_cards")):
			return

		return super().check_if_operations_completed()
