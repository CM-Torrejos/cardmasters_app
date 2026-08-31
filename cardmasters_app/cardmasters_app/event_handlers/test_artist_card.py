from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from cardmasters_app.cardmasters_app.event_handlers.artist_card import validate_submission


class TestArtistCardValidation(FrappeTestCase):
	@patch("cardmasters_app.cardmasters_app.event_handlers.artist_card.frappe.throw")
	@patch("cardmasters_app.cardmasters_app.event_handlers.artist_card.frappe.db.exists")
	def test_rejects_duplicate_sales_order_artist_card(self, exists, throw):
		exists.return_value = "ART-CARD-0001"
		doc = self._artist_card(sales_order="SAL-ORD-0001")

		validate_submission(doc, None)

		exists.assert_called_once_with(
			"Artist Card", {"sales_order": "SAL-ORD-0001"}
		)
		throw.assert_called_once()
		self.assertIn("Sales Order SAL-ORD-0001", str(throw.call_args.args[0]))

	@patch("cardmasters_app.cardmasters_app.event_handlers.artist_card.frappe.throw")
	@patch("cardmasters_app.cardmasters_app.event_handlers.artist_card.frappe.db.exists")
	def test_rejects_duplicate_material_request_artist_card(self, exists, throw):
		exists.return_value = "ART-CARD-0002"
		doc = self._artist_card(material_request="MAT-MR-0001")

		validate_submission(doc, None)

		exists.assert_called_once_with(
			"Artist Card", {"material_request": "MAT-MR-0001"}
		)
		throw.assert_called_once()
		self.assertIn("Material Request MAT-MR-0001", str(throw.call_args.args[0]))

	@patch("cardmasters_app.cardmasters_app.event_handlers.artist_card.frappe.db.exists")
	def test_allows_unlinked_or_unique_documents(self, exists):
		exists.return_value = None

		validate_submission(self._artist_card(), None)
		validate_submission(
			self._artist_card(
				sales_order="SAL-ORD-0001",
				material_request="MAT-MR-0001",
			),
			None,
		)

		self.assertEqual(
			exists.call_args_list,
			[
				(("Artist Card", {"sales_order": "SAL-ORD-0001"}),),
				(("Artist Card", {"material_request": "MAT-MR-0001"}),),
			],
		)

	@staticmethod
	def _artist_card(sales_order=None, material_request=None):
		values = {
			"sales_order": sales_order,
			"material_request": material_request,
		}
		return SimpleNamespace(get=values.get)
