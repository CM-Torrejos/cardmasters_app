import frappe
from frappe.model.document import Document

class DamagesandReturns(Document):
	def validate(self):
		# 1. If error type is not Human, points are always 0
		if self.error_type != 'Human':
			self.damage_points = 0.0
			return
			
		# 2. If the value hasn't been inputted yet, set points to 0
		if not self.value_of_damages or self.value_of_damages == 0:
			self.damage_points = 0.0
			return
			
		# 3. If a value exists, dynamically fetch the points
		tier = frappe.db.sql("""
			SELECT points_to_assign 
			FROM `tabDamage Tier Rule` 
			WHERE %s BETWEEN minimum_amount AND maximum_amount AND is_active = 1
		""", (self.value_of_damages))
		
		if tier:
			self.damage_points = float(tier[0][0])
		else:
			frappe.throw(f"Damage value of ₱{self.value_of_damages:,.2f} does not match any active Tier Rules.")

	def on_update(self):
		# This hook runs EVERY time the document is saved.
		# It ensures the ledger is always in sync with the current value.
		
		for person in self.point_persons:
			if person.employee:
				# Check if a ledger entry already exists for this person and this document
				existing_ledger = frappe.db.exists(
					"Damage Point Ledger", 
					{"reference_document": self.name, "employee": person.employee}
				)
				
				if existing_ledger:
					# If it exists, update the points (even if it changes to 0)
					frappe.db.set_value("Damage Point Ledger", existing_ledger, "points", self.damage_points)
					frappe.db.set_value("Damage Point Ledger", existing_ledger, "incident_date", self.date_of_damage_or_return)
				else:
					# If it does not exist, only create it if points are greater than 0
					if self.damage_points > 0:
						frappe.get_doc({
							"doctype": "Damage Point Ledger",
							"employee": person.employee,
							"incident_date": self.date_of_damage_or_return,
							"reference_document": self.name,
							"points": self.damage_points,
							"status": "Active"
						}).insert(ignore_permissions=True)