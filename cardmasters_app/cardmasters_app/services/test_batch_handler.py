from unittest import TestCase
from unittest.mock import MagicMock, patch

from cardmasters_app.cardmasters_app.services.batch_handler import (
	resolve_material_request_batch,
	set_batch_no_for_fg_on_manufacture_entry,
	set_batch_no_for_delivery_note,
)


class TestSetBatchNoForFinishedGoods(TestCase):
	@patch("cardmasters_app.cardmasters_app.services.batch_handler.frappe.get_doc")
	def test_assigns_batch_to_every_matching_finished_goods_row(self, get_doc):
		work_order = MagicMock()
		work_order.name = "WO-0001"
		work_order.production_item = "FG-ITEM"
		work_order.get.side_effect = {
			"custom_production_type": "Make to Order",
			"custom_batch": "BATCH-0001",
		}.get
		get_doc.return_value = work_order

		first_fg_row = MagicMock(item_code="FG-ITEM")
		component_row = MagicMock(item_code="COMPONENT")
		second_fg_row = MagicMock(item_code="FG-ITEM")
		stock_entry = MagicMock(
			custom_batched=1,
			stock_entry_type="Material Transfer for Manufacture",
			work_order="WO-0001",
			items=[first_fg_row, component_row, second_fg_row],
		)

		set_batch_no_for_fg_on_manufacture_entry(stock_entry, "validate")

		for row in (first_fg_row, second_fg_row):
			self.assertEqual(row.batch_no, "BATCH-0001")
			row.db_set.assert_called_once_with("batch_no", "BATCH-0001")
		component_row.db_set.assert_not_called()


class TestSetBatchNoForDeliveryNote(TestCase):
	def test_unchecked_batched_preserves_manual_batch_numbers(self):
		row = MagicMock()
		row.batch_no = "MANUAL-BATCH"
		delivery_note = MagicMock(items=[row])
		delivery_note.get.side_effect = {
			"is_return": 0,
			"custom_batched": 0,
		}.get

		set_batch_no_for_delivery_note(delivery_note, "validate")

		self.assertEqual(row.batch_no, "MANUAL-BATCH")
		row.set.assert_not_called()
		row.db_set.assert_not_called()


class TestResolveMaterialRequestBatch(TestCase):
	@patch("cardmasters_app.cardmasters_app.services.batch_handler._has_field", return_value=True)
	@patch("cardmasters_app.cardmasters_app.services.batch_handler.frappe.get_all")
	def test_prefers_linked_work_order_batch(self, get_all, _has_field):
		get_all.return_value = [MagicMock(custom_batch="MR-BATCH-0001")]

		result = resolve_material_request_batch("MAT-MR-0001", "MRI-0001", "FG-ITEM")

		self.assertEqual(result, "MR-BATCH-0001")
		get_all.assert_called_once_with(
			"Work Order",
			filters={
				"material_request": "MAT-MR-0001",
				"material_request_item": "MRI-0001",
				"production_item": "FG-ITEM",
				"docstatus": ["<", 2],
				"custom_batch": ["!=", ""],
			},
			fields=["custom_batch"],
			order_by="creation asc",
			limit=1,
		)

	@patch("cardmasters_app.cardmasters_app.services.batch_handler._has_field", return_value=True)
	@patch("cardmasters_app.cardmasters_app.services.batch_handler.frappe")
	def test_falls_back_to_canonical_batch_name(self, frappe_mock, _has_field):
		frappe_mock.get_all.return_value = []
		frappe_mock.db.get_value.return_value = "MAT-MR-0001_MRI-0001"

		result = resolve_material_request_batch("MAT-MR-0001", "MRI-0001", "FG-ITEM")

		self.assertEqual(result, "MAT-MR-0001_MRI-0001")
		frappe_mock.db.get_value.assert_called_once_with(
			"Batch",
			"MAT-MR-0001_MRI-0001",
			"name",
		)
