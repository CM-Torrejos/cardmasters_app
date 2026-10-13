import frappe
from frappe.model.document import Document
from frappe.utils import flt

class DamagesandReturns(Document):

	def validate(self):
		# 1. Determine if we need to recalculate charges
		needs_recalculation = False
		
		if self.is_new():
			needs_recalculation = True
		else:
			old_doc = self.get_doc_before_save()
			if old_doc:
				# Check if value of damages changed
				if flt(self.value_of_damages) != flt(old_doc.value_of_damages):
					needs_recalculation = True
				
				# Check if point_persons list changed (added or removed)
				old_persons = {row.employee for row in (old_doc.point_persons or []) if row.employee}
				new_persons = {row.employee for row in (self.point_persons or []) if row.employee}
				
				if old_persons != new_persons:
					needs_recalculation = True

		# Only sync and overwrite if a relevant trigger field actually changed
		if needs_recalculation:
			self.sync_charge_employees()

		# 2. Damage Points Logic
		if self.error_type != 'Human':
			self.damage_points = 0.0
			return

		if not self.value_of_damages or self.value_of_damages == 0:
			self.damage_points = 0.0
			return

		# 3. Fetch points from the active Damage Tier Rule.
		tier = frappe.db.sql("""
			SELECT points_to_assign
			FROM `tabDamage Tier Rule`
			WHERE %s BETWEEN minimum_amount AND maximum_amount
			  AND is_active = 1
			LIMIT 1
		""", (self.value_of_damages,))

		if tier:
			self.damage_points = float(tier[0][0])
		else:
			frappe.throw(
				f"Damage value of ₱{self.value_of_damages:,.2f} "
				"does not match any active Tier Rules."
			)

	def sync_charge_employees(self):
		"""Keep Charge Employee synchronized with Point Persons and split cost."""

		# Get unique valid employees from point_persons
		selected_employees = list(dict.fromkeys(
			row.employee for row in (self.point_persons or []) if row.employee
		))
		selected_set = set(selected_employees)

		# 1. Retain only charge rows for employees that are still selected
		existing_rows = list(self.charge_employee or [])
		retained_rows = [
			row for row in existing_rows
			if row.employee in selected_set
		]
		self.set("charge_employee", retained_rows)

		# 2. Identify employees already in the retained rows
		existing_employees = {row.employee for row in retained_rows if row.employee}

		# 3. Add newly selected employees
		for employee in selected_employees:
			if employee not in existing_employees:
				self.append("charge_employee", {
					"employee": employee
				})

		# 4. Recalculate charges equally
		rows = self.charge_employee or []
		if rows:
			# Enforce 2-decimal rounding
			split_value = flt(flt(self.value_of_damages or 0) / len(rows), 2)
			for row in rows:
				row.charge = split_value

	def on_update(self):
		# Keep the Damage Point Ledger synchronized.
		for person in (self.point_persons or []):
			if not person.employee:
				continue

			existing_ledger = frappe.db.exists(
				"Damage Point Ledger",
				{
					"reference_document": self.name,
					"employee": person.employee
				}
			)

			if existing_ledger:
				frappe.db.set_value(
					"Damage Point Ledger",
					existing_ledger,
					{
						"points": self.damage_points,
						"incident_date": self.date_of_damage_or_return
					}
				)
			elif self.damage_points > 0:
				frappe.get_doc({
					"doctype": "Damage Point Ledger",
					"employee": person.employee,
					"incident_date": self.date_of_damage_or_return,
					"reference_document": self.name,
					"points": self.damage_points,
					"status": "Active"
				}).insert(ignore_permissions=True)