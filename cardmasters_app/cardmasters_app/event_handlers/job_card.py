import frappe
from frappe.model.workflow import apply_workflow, get_transitions

# Check if the Job Card status is changed to "Work In Progress"
def on_job_card_create_handler(doc, method):
	if doc.status == "Work In Progress" and doc.work_order:
		# Fetch Work Order's current status
		work_order_status = frappe.db.get_value("Work Order", doc.work_order, "status")
		if work_order_status == "Not Started":
			frappe.db.set_value("Work Order", doc.work_order, "status", "In Process")

def before_job_card_save(doc, method):
	if doc.work_order:
		# directly fetch the sales_order field from the Work Order doctype
		doc.custom_item = frappe.db.get_value(
			"Work Order",
			doc.work_order,
			"item_name"
		)

		doc.custom_item_specifics = frappe.db.get_value(
			"Work Order",
			doc.work_order,
			"custom_item_specifics"
		)

		doc.custom_particulars = frappe.db.get_value(
			"Work Order",
			doc.work_order,
			"custom_particulars"
		)

		doc.custom_sales_order = frappe.db.get_value(
			"Work Order", 
			doc.work_order, 
			"sales_order"
		)

		doc.custom_deadline = frappe.db.get_value(
			"Work Order",
			doc.work_order,
			"custom_deadline"
		)


def check_all_job_cards_submitted(doc, method):

	cards = frappe.get_all(
		"Job Card",
		filters={"work_order": doc.work_order},
		fields=["name", "status"]
	)
	
	pending = [c.name for c in cards if c.status != 'Completed']
	print(pending)
	if (pending.length == 0):

		doc = frappe.get_doc("Work Order", doc.work_order)
		doc = apply_workflow(doc, "Finish Item")
		doc.save(ignore_permissions=True)