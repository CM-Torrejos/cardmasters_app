import frappe
from frappe.model.document import Document
from frappe.utils import flt  # Import float converter

class Grant(Document):
    def validate(self):
        # 1. Sum up child table with float safety
        total_redeemed = 0
        for entry in self.get("grant_entries") or []:
            total_redeemed += flt(entry.grand_total)
            
        # 2. Update parent fields using exact names
        self.redeemed_value = total_redeemed
        
        # We use flt() here because Currency fields can sometimes be 'None' initially
        self.available_balance = flt(self.grant_amount) - flt(self.redeemed_value)

        # 3. Status Logic
        if self.available_balance <= 0 and flt(self.grant_amount) > 0:
            self.status = "Exhausted"
        elif self.redeemed_value > 0:
            self.status = "Active"