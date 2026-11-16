"""Check payment requirements at submission; existing orders receive warnings only."""

import frappe
from frappe import _
from frappe.utils import cint, cstr


def missing_payment_requirements(doc):
	if doc.get("custom_payment_method") == "Credit Memo":
		if not frappe.db.exists("Credit Memo", {"sales_order": doc.name, "docstatus": ["<", 2]}):
			return [_('Create a linked Credit Memo before submitting a Sales Order with payment method "Credit Memo".')]
	elif doc.get("custom_payment_method") == "Credit":
		if not cstr(doc.get("po_no")).strip() and not cint(doc.get("custom_po_to_follow")):
			return [_('Enter the customer Purchase Order No. or check "Purchase Order to Follow" before submitting a Sales Order with payment method "Credit".')]
	return []


def validate_payment_requirements(doc, method=None):
	"""Registered only for before_submit, never for save/update/cancel."""
	messages = missing_payment_requirements(doc)
	if messages:
		frappe.throw(messages[0], title=_("Missing Payment Requirement"))


@frappe.whitelist()
def get_payment_requirement_warnings(sales_order: str):
	"""Recheck on each browser visit, including forms already cached by Desk."""
	doc = frappe.get_doc("Sales Order", sales_order)
	doc.check_permission("read")
	return missing_payment_requirements(doc) if doc.docstatus == 1 else []
