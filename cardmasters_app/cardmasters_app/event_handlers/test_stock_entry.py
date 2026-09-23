from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from cardmasters_app import hooks
from cardmasters_app.cardmasters_app.event_handlers.stock_entry import apply_material_request_reason_account


class TestMaterialRequestReasonAccount(TestCase):
	def setUp(self):
		translation_patch = patch(
			"cardmasters_app.cardmasters_app.event_handlers.stock_entry._", side_effect=lambda text: text
		)
		translation_patch.start()
		self.addCleanup(translation_patch.stop)
		self.doc = SimpleNamespace(company="Company", purpose="Material Issue")
		self.doc.items = [frappe._dict(material_request="MR-1", expense_account="Old")]
		self.values = {
			("Material Request", "MR-1"): "Reason-1",
			("Material Request", "MR-2"): "Reason-2",
			("Material Request Reason", "Reason-1"): "Account-1",
			("Material Request Reason", "Reason-2"): "Account-2",
			("Account", "Account-1"): frappe._dict(company="Company", is_group=0, disabled=0),
			("Account", "Account-2"): frappe._dict(company="Company", is_group=0, disabled=0),
		}
		database_patch = patch("frappe.db", new=MagicMock())
		self.lookup = database_patch.start().get_value
		self.lookup.side_effect = lambda dt, name, *args, **kwargs: self.values.get((dt, name))
		self.addCleanup(database_patch.stop)

	def test_each_request_uses_its_own_account_and_overrides_manual_account(self):
		self.doc.items.extend([
			frappe._dict(material_request="MR-1", expense_account="Manual"),
			frappe._dict(material_request="MR-2"),
			frappe._dict(expense_account="Unlinked"),
		])
		apply_material_request_reason_account(self.doc)
		self.assertEqual([r.expense_account for r in self.doc.items],
			["Account-1", "Account-1", "Account-2", "Unlinked"])
		self.assertEqual(self.lookup.call_count, 6)
		self.values[("Material Request Reason", "Reason-1")] = "Account-2"
		apply_material_request_reason_account(self.doc)
		self.assertEqual(self.doc.items[0].expense_account, "Account-2")

	def test_legacy_request_without_reason_keeps_default(self):
		self.values[("Material Request", "MR-1")] = None
		apply_material_request_reason_account(self.doc)
		self.assertEqual(self.doc.items[0].expense_account, "Old")

	def test_other_purposes_are_unchanged(self):
		for purpose in ("Material Transfer", "Manufacture", "Material Receipt"):
			self.doc.purpose = purpose
			apply_material_request_reason_account(self.doc)
		self.lookup.assert_not_called()

	def test_missing_mapping_and_invalid_accounts_are_rejected(self):
		for details in (None, frappe._dict(company="Other"),
			frappe._dict(company="Company", is_group=1),
			frappe._dict(company="Company", disabled=1)):
			with self.subTest(details=details):
				self.values[("Account", "Account-1")] = details
				with patch("frappe.throw", side_effect=frappe.ValidationError), self.assertRaises(frappe.ValidationError):
					apply_material_request_reason_account(self.doc)
		self.values[("Material Request Reason", "Reason-1")] = None
		with patch("frappe.throw", side_effect=frappe.ValidationError), self.assertRaises(frappe.ValidationError):
			apply_material_request_reason_account(self.doc)

	def test_registered_before_core_validation_on_save_and_submit(self):
		self.assertIn(
			"cardmasters_app.cardmasters_app.event_handlers.stock_entry.apply_material_request_reason_account",
			hooks.doc_events["Stock Entry"]["before_validate"],
		)
