import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe.utils import cint

class CustomStockEntry(StockEntry):
    def check_if_operations_completed(self):
        # Look at your custom settings checkbox
        if cint(frappe.db.get_single_value("Cardmasters Settings", "disable_job_cards")):
            return # 👈 Bypasses the validation silently!

        # Otherwise, run the native ERPNext Job Card validation checks
        super().check_if_operations_completed()