from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from cardmasters_app.cardmasters_app.api.material_request import make_batched_material_transfer


class TestMakeBatchedMaterialTransfer(TestCase):
	@patch(
		"cardmasters_app.cardmasters_app.services.batch_handler.get_batch_source_warehouse",
		return_value="Finished Goods - CM",
	)
	@patch(
		"cardmasters_app.cardmasters_app.services.batch_handler.resolve_material_request_batch",
		return_value="MAT-MR-0001_MRI-0001",
	)
	@patch("cardmasters_app.cardmasters_app.api.material_request.get_mapped_doc")
	def test_maps_batch_warehouses_and_material_request_links(
		self,
		get_mapped_doc,
		resolve_material_request_batch,
		get_batch_source_warehouse,
	):
		mapped_item = frappe._dict()
		stock_entry = MagicMock(items=[mapped_item])
		stock_entry.meta.has_field.return_value = True

		def map_document(source_doctype, source_name, mapping, target_doc, set_defaults):
			self.assertEqual(source_doctype, "Material Request")
			self.assertEqual(source_name, "MAT-MR-0001")
			self.assertIsNone(target_doc)

			source = frappe._dict(
				name="MAT-MR-0001",
				company="CARDMASTERS CDO",
				set_warehouse="Finished Goods - CM",
				custom_sales_order="SO-0001",
			)
			source_item = frappe._dict(
				name="MRI-0001",
				item_code="BATCHED-FG",
				qty=4,
				conversion_factor=2,
				from_warehouse="Requested Source - CM",
				warehouse="Requested Target - CM",
			)

			mapping["Material Request Item"]["postprocess"](
				source_item,
				mapped_item,
				source,
			)
			set_defaults(source, stock_entry)
			return stock_entry

		get_mapped_doc.side_effect = map_document

		def get_cached_value(doctype, name, fieldname):
			if (doctype, name, fieldname) == ("Item", "BATCHED-FG", "has_batch_no"):
				return 1
			return None

		with patch(
			"cardmasters_app.cardmasters_app.api.material_request.frappe.get_cached_value",
			side_effect=get_cached_value,
		):
			result = make_batched_material_transfer.__wrapped__("MAT-MR-0001")

		self.assertIs(result, stock_entry)
		self.assertEqual(mapped_item.qty, 4)
		self.assertEqual(mapped_item.transfer_qty, 8)
		self.assertEqual(mapped_item.material_request, "MAT-MR-0001")
		self.assertEqual(mapped_item.material_request_item, "MRI-0001")
		self.assertEqual(mapped_item.batch_no, "MAT-MR-0001_MRI-0001")
		self.assertEqual(mapped_item.s_warehouse, "Finished Goods - CM")
		self.assertEqual(mapped_item.t_warehouse, "Requested Target - CM")
		self.assertEqual(mapped_item.use_serial_batch_fields, 1)
		self.assertEqual(stock_entry.purpose, "Material Transfer")
		self.assertEqual(stock_entry.company, "CARDMASTERS CDO")
		self.assertEqual(stock_entry.custom_sales_order, "SO-0001")
		resolve_material_request_batch.assert_called_once_with(
			"MAT-MR-0001",
			"MRI-0001",
			"BATCHED-FG",
		)
		get_batch_source_warehouse.assert_called_once_with(
			"MAT-MR-0001_MRI-0001",
			8,
			"CARDMASTERS CDO",
		)
