import frappe
from frappe.utils import add_months, cint, getdate, today

def process_rolling_resets():
	# 1. Fetch reset interval from Damage Point Settings
	settings = frappe.get_cached_doc("Damage Point Settings")
	months_required = cint(settings.get("months_required_for_reset"))

	# Guard: If not configured or disabled (<= 0), exit early
	if months_required <= 0:
		frappe.logger().info(
			"Rolling resets skipped: 'months_required_for_reset' is not configured or set to 0."
		)
		return

	# 2. Find the most recent active incident date for every employee
	employees_with_active_points = frappe.db.sql(
		"""
		SELECT employee, MAX(incident_date) as last_incident
		FROM `tabDamage Point Ledger`
		WHERE status = 'Active'
		GROUP BY employee
		""",
		as_dict=True,
	)

	current_date = getdate(today())

	for row in employees_with_active_points:
		emp = row.employee
		last_incident = getdate(row.last_incident)

		if not last_incident:
			continue

		# 3. Calculate threshold date dynamically using settings
		threshold_date = add_months(last_incident, months_required)

		# 4. If today is on or past the threshold date, reset their points
		if current_date >= threshold_date:
			frappe.db.sql(
				"""
				UPDATE `tabDamage Point Ledger`
				SET status = 'Reset', reset_date = %s
				WHERE employee = %s AND status = 'Active'
				""",
				(current_date, emp),
			)

			frappe.logger().info(
				f"Automated Rolling Reset applied for Employee {emp} after {months_required} months of clean record."
			)

	# 5. Commit database changes
	frappe.db.commit()