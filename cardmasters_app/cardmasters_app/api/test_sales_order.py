from unittest import TestCase
from unittest.mock import MagicMock, patch

from cardmasters_app.cardmasters_app.api.sales_order import get_customer_dashboard_balance


class TestGetCustomerDashboardBalance(TestCase):
    def setUp(self):
        self.customer_doc = MagicMock(loyalty_program="Test Loyalty Program")
        self.get_doc_patcher = patch(
            "cardmasters_app.cardmasters_app.api.sales_order.frappe.get_doc",
            return_value=self.customer_doc,
        )
        self.get_doc_patcher.start()
        self.addCleanup(self.get_doc_patcher.stop)

    def get_balance(self, dashboard_info, company="CARDMASTERS CDO"):
        with patch("erpnext.accounts.party.get_dashboard_info", return_value=dashboard_info):
            return get_customer_dashboard_balance("BERNIE BUSOG BITES", company)

    def test_upstream_dashboard_data_returns_a_list_item(self):
        info = {"company": "CARDMASTERS CDO", "balance_amount": 100}

        self.assertEqual(self.get_balance([info]), info)
        self.customer_doc.check_permission.assert_called_with("read")

    def test_upstream_dashboard_data_returns_none(self):
        self.assertIsNone(self.get_balance(None))

    def test_requested_company_exists(self):
        requested = {"company": "CARDMASTERS CDO", "balance_amount": 100}
        dashboard_info = [
            {"company": "OTHER COMPANY", "balance_amount": 50},
            requested,
        ]

        self.assertIs(self.get_balance(dashboard_info), requested)

    def test_requested_company_does_not_exist(self):
        dashboard_info = [{"company": "OTHER COMPANY", "balance_amount": 50}]

        self.assertIsNone(self.get_balance(dashboard_info))
