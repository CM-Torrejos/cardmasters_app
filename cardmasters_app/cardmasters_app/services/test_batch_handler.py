from unittest import TestCase
from unittest.mock import MagicMock, patch

from cardmasters_app.cardmasters_app.services.batch_handler import (
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
