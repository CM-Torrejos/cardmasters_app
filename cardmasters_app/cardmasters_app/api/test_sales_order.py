from unittest import TestCase
from unittest.mock import MagicMock, patch

from cardmasters_app.cardmasters_app.api.sales_order import (
    get_customer_dashboard_balance,
    get_customer_sales_order_outstanding,
)


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


class TestGetCustomerSalesOrderOutstanding(TestCase):
    @patch("cardmasters_app.cardmasters_app.api.sales_order.frappe.get_list")
    def test_sums_visible_submitted_sales_order_balances(self, get_list):
        get_list.return_value = [
            MagicMock(custom_outstanding_balance=100),
            MagicMock(custom_outstanding_balance=50),
        ]

        result = get_customer_sales_order_outstanding("BERNIE BUSOG BITES", "CARDMASTERS CDO")

        self.assertEqual(result, 150)
        get_list.assert_called_once_with(
            "Sales Order",
            filters={
                "customer": "BERNIE BUSOG BITES",
                "company": "CARDMASTERS CDO",
                "docstatus": 1,
                "custom_outstanding_balance": [">", 0],
            },
            fields=["custom_outstanding_balance"],
            limit_page_length=0,
        )

    @patch("cardmasters_app.cardmasters_app.api.sales_order.frappe.get_list")
    def test_no_visible_outstanding_orders_returns_zero(self, get_list):
        get_list.return_value = []

        self.assertEqual(
            get_customer_sales_order_outstanding("BERNIE BUSOG BITES", "CARDMASTERS CDO"), 0
        )

    def test_missing_customer_or_company_returns_zero(self):
        self.assertEqual(get_customer_sales_order_outstanding(None, "CARDMASTERS CDO"), 0)
        self.assertEqual(get_customer_sales_order_outstanding("BERNIE BUSOG BITES", None), 0)
