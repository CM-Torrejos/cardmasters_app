from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from cardmasters_app import hooks
from cardmasters_app.cardmasters_app.services.batch_handler import (
	restore_material_request_batch_on_amendment,
)

MODULE = "cardmasters_app.cardmasters_app.services.batch_handler"


class TestAmendmentBatchSelection(TestCase):
	def setUp(self):
		self.doc = SimpleNamespace(
			amended_from="STE-1", docstatus=0, purpose="Material Issue",
			stock_entry_type="Material Issue", custom_batched=0,
		)
		self.doc.get = lambda key: getattr(self.doc, key, None)
		self.doc._action = "save"
		self.row = frappe._dict(
			idx=1, item_code="FG", material_request="MR-1", material_request_item="MRI-1",
			s_warehouse="Claiming", t_warehouse="Damages", qty=3, use_serial_batch_fields=0,
		)
		self.doc.items = [self.row]
		self.db = self.enterContext(patch("frappe.db", new=MagicMock()))
		self.db.exists.return_value = True
		self.db.get_value.return_value = "FG"
		self.batched = self.enterContext(patch("frappe.get_cached_value", return_value=1))
		self.resolve = self.enterContext(patch(f"{MODULE}.resolve_material_request_batch", return_value="MR-1_MRI-1"))
		self.enterContext(patch(f"{MODULE}._", side_effect=lambda message: message))
		self.enterContext(patch("frappe.throw", side_effect=frappe.ValidationError))

	def test_restores_request_batch_for_issue_and_transfer_without_batched_flag(self):
		for purpose in ("Material Issue", "Material Transfer"):
			with self.subTest(purpose=purpose):
				self.doc.purpose = self.doc.stock_entry_type = purpose
				self.row.batch_no = None
				restore_material_request_batch_on_amendment(self.doc)
				self.assertEqual(self.row.batch_no, "MR-1_MRI-1")
				self.assertEqual(self.row.use_serial_batch_fields, 1)
				self.assertEqual((self.row.s_warehouse, self.row.t_warehouse, self.row.qty), ("Claiming", "Damages", 3))
		self.resolve.assert_called_with("MR-1", "MRI-1", "FG")

	def test_runs_on_direct_submission_before_fifo_can_run(self):
		self.doc.docstatus = 1
		self.doc._action = "submit"
		restore_material_request_batch_on_amendment(self.doc)
		self.assertEqual(self.row.batch_no, "MR-1_MRI-1")

	def test_preserves_explicit_batch_or_bundle_and_is_idempotent(self):
		for field in ("batch_no", "serial_and_batch_bundle"):
			self.row[field] = "Explicit"
			restore_material_request_batch_on_amendment(self.doc)
			self.assertEqual(self.row[field], "Explicit")
			self.row[field] = None
		self.resolve.assert_not_called()
		restore_material_request_batch_on_amendment(self.doc)
		restore_material_request_batch_on_amendment(self.doc)
		self.assertEqual(self.resolve.call_count, 1)

	def test_unresolved_or_wrong_item_batch_blocks_fifo(self):
		for batch, item in ((None, "FG"), ("BATCH", "OTHER")):
			self.resolve.return_value = batch
			self.db.get_value.return_value = item
			with self.assertRaises(frappe.ValidationError):
				restore_material_request_batch_on_amendment(self.doc)
			self.assertFalse(self.row.batch_no)

	def test_missing_or_mismatched_request_item_blocks_fifo(self):
		for request_item, exists in ((None, True), ("WRONG-ROW", False)):
			self.row.material_request_item = request_item
			self.db.exists.return_value = exists
			with self.assertRaises(frappe.ValidationError):
				restore_material_request_batch_on_amendment(self.doc)
		self.resolve.assert_not_called()
		self.db.exists.assert_called_with("Material Request Item", {
			"name": "WRONG-ROW", "parent": "MR-1", "item_code": "FG",
		})

	def test_does_not_change_unrelated_entries(self):
		for field, value in (("amended_from", None), ("stock_entry_type", "Manufacture"), ("docstatus", 1)):
			old = getattr(self.doc, field)
			setattr(self.doc, field, value)
			restore_material_request_batch_on_amendment(self.doc)
			setattr(self.doc, field, old)
		self.resolve.assert_not_called()

	def test_skips_unlinked_and_non_batched_items(self):
		self.row.material_request = None
		restore_material_request_batch_on_amendment(self.doc)
		self.row.material_request = "MR-1"
		self.batched.return_value = 0
		restore_material_request_batch_on_amendment(self.doc)
		self.resolve.assert_not_called()

	def test_repeated_item_codes_resolve_by_request_row(self):
		second = frappe._dict(self.row, idx=2, material_request_item="MRI-2")
		self.doc.items.append(second)
		self.resolve.side_effect = lambda mr, row, item: f"{mr}_{row}"
		restore_material_request_batch_on_amendment(self.doc)
		self.assertEqual([row.batch_no for row in self.doc.items], ["MR-1_MRI-1", "MR-1_MRI-2"])

	def test_registered_before_core_validation(self):
		self.assertIn(
			f"{MODULE}.restore_material_request_batch_on_amendment",
			hooks.doc_events["Stock Entry"]["before_validate"],
		)
