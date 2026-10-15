# Copyright (c) 2025, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

class DamagesandReturns(Document):
	def validate(self):
		# 1. Detect if we need to force a recalculation
		needs_recalc = False
		if self.is_new():
			needs_recalc = True
		else:
			old_doc = self.get_doc_before_save()
			if old_doc:
				# Check if the total value changed
				if flt(old_doc.value_of_damages) != flt(self.value_of_damages):
					needs_recalc = True
				else:
					# Check if the list of employees changed (added or removed)
					old_emps = {row.employee for row in (old_doc.point_persons or []) if row.employee}
					new_emps = {row.employee for row in (self.point_persons or []) if row.employee}
					if old_emps != new_emps:
						needs_recalc = True

		# 2. Synchronize Point Persons with Charge Employee
		self.sync_charge_employees(needs_recalc)

		# 3. Check if the error type qualifies based on Damage Point Settings
		allowed_error_types = self.get_allowed_error_types()
		if not self.error_type or self.error_type not in allowed_error_types:
			self.damage_points = 0.0
			return

		# 4. If damage value is empty or zero, points are 0
		if not self.value_of_damages or flt(self.value_of_damages) <= 0:
			self.damage_points = 0.0
			return

		# 5. Fetch points from the Damage Point Settings child table (damage_tier_rules)
		settings = frappe.get_cached_doc("Damage Point Settings")
		tier_points = None

		for rule in settings.get("damage_tier_rules") or []:
			if rule.get("is_active", 1):
				if flt(rule.minimum_amount) <= flt(self.value_of_damages) <= flt(rule.maximum_amount):
					tier_points = flt(rule.points_to_assign)
					break

		if tier_points is not None:
			self.damage_points = tier_points
		else:
			frappe.throw(
				f"Damage value of ₱{flt(self.value_of_damages):,.2f} "
				"does not match any active Tier Rules in Damage Point Settings."
			)

	def on_update(self):
		"""Handles ledger creation, updates, and cancellations based on Workflow State."""
		settings = frappe.get_cached_doc("Damage Point Settings")
		cancel_state = settings.cancel_workflow_state

		# 1. Workflow Cancellation State: Cancel all existing ledgers
		if self.workflow_state and self.workflow_state == cancel_state:
			self.cancel_all_active_ledgers("Cancelled: The parent document was cancelled via workflow.")
			return

		# 3. Trigger State Logic: Process ledgers
		valid_employees = [p.employee for p in (self.point_persons or []) if p.employee]

		active_ledgers = frappe.get_all(
			"Damage Point Ledger",
			filters={"reference_document": self.name, "docstatus": 1},
			fields=["name", "employee"]
		)
		
		active_emp_map = {ledger.employee: ledger.name for ledger in active_ledgers}

		# A. Update existing ledgers or Cancel them based on conditions
		for emp, ledger_name in active_emp_map.items():
			cancel_reason = None
			emp_name = frappe.db.get_value("Employee", emp, "employee_name") or emp
			
			if self.damage_points == 0:
				cancel_reason = "Cancelled: Error Type changed to a non-penalized type, or Damage Value became zero."
			elif emp not in valid_employees:
				cancel_reason = f"Cancelled: Point person {emp_name} ({emp}) was removed from the DNR."

			if cancel_reason:
				ledger_doc = frappe.get_doc("Damage Point Ledger", ledger_name)
				ledger_doc.cancel()
				ledger_doc.add_comment("Comment", text=cancel_reason)
			else:
				ledger_doc = frappe.get_doc("Damage Point Ledger", ledger_name)
				ledger_doc.db_set("points", self.damage_points)
				ledger_doc.db_set("incident_date", self.date_of_damage_or_return)

		# B. Add ledgers for newly added point persons
		if self.damage_points > 0:
			for emp in valid_employees:
				if emp not in active_emp_map:
					self.create_and_submit_ledger(emp)

	# --- HELPER METHODS ---

	def cancel_all_active_ledgers(self, reason: str):
		"""Cancels all submitted ledgers attached to this document."""
		active_ledgers = frappe.get_all(
			"Damage Point Ledger",
			filters={"reference_document": self.name, "docstatus": 1}
		)
		for row in active_ledgers:
			ledger_doc = frappe.get_doc("Damage Point Ledger", row.name)
			ledger_doc.cancel()
			ledger_doc.add_comment("Comment", text=reason)

	def get_allowed_error_types(self) -> set:
		"""Fetch qualifying error types from Damage Point Settings."""
		settings = frappe.get_cached_doc("Damage Point Settings")
		
		raw_keys = [
			row.error_type
			for row in (settings.get("error_type") or [])
			if row.error_type
		]
		
		if not raw_keys:
			return set()

		target_doctype = frappe.get_meta("Damages and Returns Error Type Table").get_field("error_type").options
		meta = frappe.get_meta(target_doctype)

		allowed = set(raw_keys)
		if meta.has_field("error_type"):
			records = frappe.get_all(
				target_doctype,
				filters={"name": ["in", raw_keys]},
				fields=["name", "error_type"],
			)
			for r in records:
				if r.get("error_type"):
					allowed.add(r.error_type)

		return allowed

	def sync_charge_employees(self, needs_recalc=False):
		"""Keep Charge Employee synchronized while preserving manual edits."""
		selected_employees = list(
			dict.fromkeys(
				row.employee
				for row in (self.point_persons or [])
				if row.employee
			)
		)
		selected_set = set(selected_employees)

		# 1. Remove rows for unselected employees
		existing_rows = list(self.charge_employee or [])
		retained_rows = [row for row in existing_rows if row.employee in selected_set]
		self.set("charge_employee", retained_rows)

		# 2. Add newly selected employees
		retained_employees = {row.employee for row in retained_rows if row.employee}
		for employee in selected_employees:
			if employee not in retained_employees:
				self.append("charge_employee", {
					"employee": employee,
					"charge": 0.0
				})
				retained_employees.add(employee)

		rows = self.charge_employee or []
		if not rows:
			return

		total_damage = flt(self.value_of_damages or 0)

		# 3. If value changed, or employees were added/removed, forcefully split the cost.
		# If neither changed, it respects whatever manual edits the user made.
		if needs_recalc and total_damage > 0:
			split_value = flt(total_damage / len(rows), 2)
			for row in rows:
				row.charge = split_value

		# 4. Prevent overcharging beyond total damage amount
		total_charged = sum(flt(row.charge) for row in rows)
		if total_damage > 0 and total_charged > total_damage:
			frappe.throw(
				f"Total charges across employees (₱{total_charged:,.2f}) exceed "
				f"the Total Value of Damages (₱{total_damage:,.2f})."
			)

	def create_and_submit_ledger(self, employee):
		"""Helper to create and submit a new ledger entry."""
		ledger = frappe.get_doc({
			"doctype": "Damage Point Ledger",
			"employee": employee,
			"incident_date": self.date_of_damage_or_return,
			"reference_document": self.name,
			"points": self.damage_points,
			"status": "Active"
		})
		ledger.insert(ignore_permissions=True)
		ledger.submit()