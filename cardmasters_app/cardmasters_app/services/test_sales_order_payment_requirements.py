from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.model.document import Document

from cardmasters_app import hooks
from cardmasters_app.cardmasters_app.services import sales_order_payment_requirements as requirements


class TestSalesOrderPaymentRequirements(TestCase):
	def order(self, **values):
		return Document({"doctype": "Sales Order", "name": "SO-PAYMENT-TEST", **values})

	def test_credit_memo_requires_a_non_cancelled_link(self):
		doc = self.order(custom_payment_method="Credit Memo")
		for existing in (None, "CM-TEST"):
			with self.subTest(existing=existing), patch.object(frappe.db, "exists", return_value=existing) as exists:
				self.assertEqual(bool(requirements.missing_payment_requirements(doc)), not bool(existing))
				exists.assert_called_once_with("Credit Memo", {
					"sales_order": doc.name, "docstatus": ["<", 2],
				})

	def test_credit_accepts_purchase_order_or_explicit_po_to_follow(self):
		for po_no, follow, missing in (
			(None, 0, True), ("", "0", True), (" \t", 0, True),
			("PO-123", 0, False), ("", 1, False), (None, "1", False),
		):
			with self.subTest(po_no=po_no, follow=follow):
				doc = self.order(custom_payment_method="Credit", po_no=po_no, custom_po_to_follow=follow)
				self.assertEqual(bool(requirements.missing_payment_requirements(doc)), missing)

	def test_other_payment_methods_have_no_new_requirements(self):
		with patch.object(frappe.db, "exists") as exists:
			for method in (None, "", "Cash"):
				self.assertEqual(requirements.missing_payment_requirements(
					self.order(custom_payment_method=method)), [])
			exists.assert_not_called()

	def test_submission_rejects_missing_requirement_and_accepts_valid_order(self):
		with patch.object(frappe, "throw", side_effect=frappe.ValidationError):
			with self.assertRaises(frappe.ValidationError):
				requirements.validate_payment_requirements(self.order(custom_payment_method="Credit"))
			requirements.validate_payment_requirements(self.order(custom_payment_method="Credit", po_no="PO-123"))

	def test_opening_submitted_order_only_returns_warning_and_never_blocks(self):
		doc = self.order(docstatus=1, custom_payment_method="Credit")
		doc.check_permission = Mock()
		with patch.object(frappe, "get_doc", return_value=doc), patch.object(frappe, "throw") as throw, patch.object(frappe, "msgprint") as msgprint:
			self.assertTrue(requirements.get_payment_requirement_warnings(doc.name))
			doc.check_permission.assert_called_once_with("read")
			doc.po_no = "PO-123"
			self.assertEqual(requirements.get_payment_requirement_warnings(doc.name), [])
			throw.assert_not_called()
			msgprint.assert_not_called()

	def test_draft_and_cancelled_orders_do_not_warn_or_query_credit_memos(self):
		with patch.object(frappe.db, "exists") as exists:
			for status in (0, 2):
				doc = self.order(docstatus=status, custom_payment_method="Credit Memo")
				doc.check_permission = Mock()
				with patch.object(frappe, "get_doc", return_value=doc):
					self.assertEqual(requirements.get_payment_requirement_warnings(doc.name), [])
			exists.assert_not_called()

	def test_warning_endpoint_requires_read_permission(self):
		doc = self.order(docstatus=1, custom_payment_method="Credit Memo")
		doc.check_permission = Mock(side_effect=frappe.PermissionError)
		with patch.object(frappe, "get_doc", return_value=doc), patch.object(frappe.db, "exists") as exists:
			with self.assertRaises(frappe.PermissionError):
				requirements.get_payment_requirement_warnings(doc.name)
			exists.assert_not_called()

	def test_submission_check_is_not_registered_for_other_actions(self):
		path = requirements.__name__ + ".validate_payment_requirements"
		events = [event for event, handlers in hooks.doc_events["Sales Order"].items() if path in handlers]
		self.assertEqual(events, ["before_submit"])
