# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CreditMemo(Document):
	def validate(self):
		self.validate_unique_sales_order()

	def validate_unique_sales_order(self):
		if not self.sales_order:
			return
			
		# Look for existing Credit Memos with the same Sales Order
		existing_cm = frappe.db.exists(
			"Credit Memo", 
			{
				"sales_order": self.sales_order,
				"name": ("!=", self.name), # Exclude the current document being saved
				"docstatus": ("<", 2)      # Ignore Cancelled documents
			}
		)
		
		if existing_cm:
			frappe.throw(f"An active Credit Memo (<b>{existing_cm}</b>) already exists for Sales Order <b>{self.sales_order}</b>.")
