import frappe
from frappe.utils import nowdate
from frappe.model.workflow import apply_workflow, get_transitions

def calculate_time_difference(doc, method):
	"""
	Hooked into before_save of Artist Sheet.
	When workflow_state == 'Client Approved',
	set time_difference = expected_total_time - finished_total_time.
	Otherwise clear it.
	"""
	# ensure we have numeric values
	expected = doc.expected_total_time or 0
	actual   = doc.finished_total_time or 0

	if doc.workflow_state == "Client Approved":
		# assign difference
		doc.time_difference = expected - actual
	else:
		# reset (optional—drop this line if you want to preserve old values)
		doc.time_difference = None

def assign_artist_so(doc, method):
	so = frappe.get_doc("Sales Order", doc.sales_order)
	so.custom_artist = doc.artist
	so.save() 

def validate_submission(doc, method):
	"""
	Prevent submitting an Artist Card if its linked Sales Order
	already has any other Artist Card.
	"""
	if doc.sales_order:
		# find any other Artist Card with this SO
		exists = frappe.db.exists(
			"Artist Card",{"sales_order": doc.sales_order}
		)

		if exists:
			frappe.throw(
				("Sales Order {0} already has an Artist Card ({1})")
				.format(doc.sales_order, exists)
			)
			
def before_insert(doc, method):
	print('thsi runs')
	so = frappe.get_doc("Sales Order", doc.sales_order)
	if (so.workflow_state and so.workflow_state == 'Pending'):
		print('thsi runs 2')
		so = apply_workflow(so, "Begin Layout")
		so.save()

