import frappe
from frappe.utils import getdate, add_months, today

def process_rolling_resets():
	# 1. Find the most recent active incident date for every employee
	employees_with_active_points = frappe.db.sql("""
		SELECT employee, MAX(incident_date) as last_incident
		FROM `tabDamage Point Ledger`
		WHERE status = 'Active'
		GROUP BY employee
	""", as_dict=True)

	current_date = getdate(today())

	for row in employees_with_active_points:
		emp = row.employee
		last_incident = row.last_incident
		
		# 2. Calculate the threshold (3 months after their last incident)
		threshold_date = add_months(last_incident, 3)
		
		# 3. If today's date is past the 3-month mark, reset their points
		if current_date >= threshold_date:
			frappe.db.sql("""
				UPDATE `tabDamage Point Ledger`
				SET status = 'Reset', reset_date = %s
				WHERE employee = %s AND status = 'Active'
			""", (current_date, emp))
			
			# Log it so you know the automation worked
			frappe.logger().info(f"Automated Rolling Reset applied for Employee {emp}")
			
	# Commit the changes to the database
	frappe.db.commit()