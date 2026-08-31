import frappe
from frappe import _
from frappe.utils import nowdate
from frappe.model.workflow import apply_workflow, get_transitions

def calculate_time_difference(doc, _method):
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

def assign_artist_so(doc, _method):
	if not doc.sales_order:
		return

	# 2. Directly update the field in the database
	frappe.db.set_value("Sales Order", doc.sales_order, "custom_artist", doc.artist)

def validate_submission(doc, _method):
	"""
	Prevent creating an Artist Card if its linked Sales Order or Material Request
	already has another Artist Card.
	"""
	for fieldname, label in (
		("sales_order", "Sales Order"),
		("material_request", "Material Request"),
	):
		linked_document = doc.get(fieldname)
		if not linked_document:
			continue

		existing_artist_card = frappe.db.exists(
			"Artist Card", {fieldname: linked_document}
		)
		if existing_artist_card:
			frappe.throw(
				_("{0} {1} already has an Artist Card ({2})").format(
					label, linked_document, existing_artist_card
				)
			)
			
def update_so_workflow_state(doc, _method):
	if not doc.sales_order:
		return

	so = frappe.get_doc("Sales Order", doc.sales_order)
	if (so.workflow_state and so.workflow_state == 'Pending'):
		so = apply_workflow(so, "Begin Layout")
		so.save()
