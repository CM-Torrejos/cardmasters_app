# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Grant(Document):
	pass

import frappe
from frappe.model.document import Document
from frappe.utils import flt  # Import float converter

class Grant(Document):
    def validate(self):

        # 1. Sum up all entries in the child table (The Single Source of Truth)
        total_redeemed = 0
        for entry in self.grant_entries:
            total_redeemed += entry.grand_total

        # 2. Update the parent fields
        self.redeemed_value = total_redeemed
        self.available_balance = self.grant_amount - self.redeemed_value
