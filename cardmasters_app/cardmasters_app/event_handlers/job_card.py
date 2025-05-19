import frappe

# Check if the Job Card status is changed to "Work In Progress"
def on_job_card_create_handler(doc, method):
	if doc.status == "Work In Progress" and doc.work_order:
		# Fetch Work Order's current status
		work_order_status = frappe.db.get_value("Work Order", doc.work_order, "status")
		if work_order_status == "Not Started":
			frappe.db.set_value("Work Order", doc.work_order, "status", "In Process")

