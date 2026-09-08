from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from cardmasters_app.cardmasters_app.api.sales_order import (
    get_customer_dashboard_balance,
    get_customer_sales_order_outstanding,
    get_sales_order_batch_transit,
)


class TestSalesOrderBatchTransit(TestCase):
    def setUp(self):
        self.sales_order = MagicMock(company="COMPANY")
        self.sales_order.name = "SO-001"
        self.work_orders = [
            frappe._dict(name="WO-001", custom_batch="BATCH-001", production_item="FG"),
            frappe._dict(name="BACKJOB-001", custom_batch="BATCH-001", production_item="FG"),
        ]
        self.holdings = [
            frappe._dict(batch_no="BATCH-001", warehouse="TRANSIT", qty=40),
            frappe._dict(batch_no="BATCH-001", warehouse="CLAIMING", qty=60),
        ]
        for target, kwargs in (
            ("cardmasters_app.cardmasters_app.api.sales_order.frappe.get_doc", {"return_value": self.sales_order}),
            ("cardmasters_app.cardmasters_app.api.sales_order.frappe.get_list", {"side_effect": self.get_list}),
            ("erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle.get_available_batches", {"side_effect": lambda kwargs: self.holdings}),
            ("erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle.get_stock_ledgers_batches", {"return_value": {}}),
            ("cardmasters_app.cardmasters_app.api.sales_order.frappe.get_precision", {"return_value": 6}),
        ):
            patcher = patch(target, **kwargs)
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            if target.endswith("get_available_batches"):
                self.get_batch_holdings = mocked

    def get_list(self, doctype, **kwargs):
        if doctype == "Work Order":
            self.assertEqual(kwargs["filters"], {"docstatus": ["!=", 2]})
            self.assertEqual(kwargs["or_filters"], {
                "sales_order": "SO-001", "custom_document_id": "SO-001",
            })
            return self.work_orders
        if doctype == "Warehouse":
            self.assertEqual(kwargs["filters"], {
                "company": "COMPANY", "warehouse_type": ["in", ["Transit", "Consignment"]], "is_group": 0,
            })
            return [
                frappe._dict(name="TRANSIT", warehouse_type="Transit"),
                frappe._dict(name="TRANSIT-2", warehouse_type="Transit"),
                frappe._dict(name="CONSIGNMENT", warehouse_type="Consignment"),
                frappe._dict(name="CONSIGNMENT-2", warehouse_type="Consignment"),
            ]
        if doctype == "Batch":
            return [frappe._dict(name="BATCH-001", item="FG", stock_uom="Nos")]
        self.fail(f"Unexpected doctype: {doctype}")

    def test_partial_shared_batch_is_not_allocated_or_counted_per_work_order(self):
        result = get_sales_order_batch_transit("SO-001")

        self.assertEqual(result, {
            name: {"batch_no": "BATCH-001", "qty": 40, "consignment_qty": 0, "stock_uom": "Nos"}
            for name in ("WO-001", "BACKJOB-001")
        })
        self.sales_order.check_permission.assert_called_once_with("read")
        self.get_batch_holdings.assert_called_once()
        args = self.get_batch_holdings.call_args.args[0]
        self.assertEqual(args["batch_no"], ["BATCH-001"])
        self.assertTrue(args["for_stock_levels"])
        self.assertTrue(args["ignore_reserved_stock"])
        self.assertTrue(args["do_not_check_future_batches"])
        self.assertIsNotNone(args["posting_datetime"])
        self.assertEqual(set(args["warehouse"]), {"TRANSIT", "TRANSIT-2", "CONSIGNMENT", "CONSIGNMENT-2"})
        self.assertEqual(args["company"], "COMPANY")

    def test_lookup_works_with_browser_request_type_validation(self):
        with patch.dict(frappe.flags, {"in_test": True}):
            result = get_sales_order_batch_transit("SO-001")

        self.assertEqual(result["WO-001"]["qty"], 40)

    def test_partial_receipt_reduces_transit_quantity(self):
        self.holdings[0].qty = 15
        self.holdings[1].qty = 85

        self.assertEqual(get_sales_order_batch_transit("SO-001")["WO-001"]["qty"], 15)

    def test_fully_received_batch_has_no_transit_status(self):
        self.holdings[0].qty = 0
        self.holdings[1].qty = 100

        self.assertEqual(get_sales_order_batch_transit("SO-001"), {})

    def test_sums_transit_locations_but_excludes_other_warehouses(self):
        self.holdings.extend([
            frappe._dict(batch_no="BATCH-001", warehouse="TRANSIT-2", qty=10),
            frappe._dict(batch_no="BATCH-001", warehouse="OTHER-COMPANY-TRANSIT", qty=200),
        ])

        self.assertEqual(get_sales_order_batch_transit("SO-001")["WO-001"]["qty"], 50)

    def test_missing_batch_and_mismatched_production_item_are_excluded(self):
        self.work_orders[0].custom_batch = None
        self.work_orders[1].production_item = "OTHER-FG"

        self.assertEqual(get_sales_order_batch_transit("SO-001"), {})

    def test_partial_transfer_from_transit_to_consignment_keeps_separate_totals(self):
        self.holdings = [
            frappe._dict(batch_no="BATCH-001", warehouse="TRANSIT", qty=40),
            frappe._dict(batch_no="BATCH-001", warehouse="CONSIGNMENT", qty=35),
            frappe._dict(batch_no="BATCH-001", warehouse="CONSIGNMENT-2", qty=25),
            frappe._dict(batch_no="BATCH-001", warehouse="OTHER-COMPANY-CONSIGNMENT", qty=200),
        ]

        result = get_sales_order_batch_transit("SO-001")

        self.assertEqual(result, {
            name: {"batch_no": "BATCH-001", "qty": 40, "consignment_qty": 60, "stock_uom": "Nos"}
            for name in ("WO-001", "BACKJOB-001")
        })

    def test_consignment_only_stock_remains_visible(self):
        self.holdings = [frappe._dict(batch_no="BATCH-001", warehouse="CONSIGNMENT", qty=100)]

        result = get_sales_order_batch_transit("SO-001")["WO-001"]

        self.assertEqual(result["qty"], 0)
        self.assertEqual(result["consignment_qty"], 100)

    def test_partial_consignment_release_reduces_quantity_then_clears_status(self):
        self.holdings = [frappe._dict(batch_no="BATCH-001", warehouse="CONSIGNMENT", qty=15)]
        self.assertEqual(get_sales_order_batch_transit("SO-001")["WO-001"]["consignment_qty"], 15)

        self.holdings[0].qty = 0
        self.assertEqual(get_sales_order_batch_transit("SO-001"), {})

    def test_no_batches_skips_stock_queries(self):
        self.work_orders = []

        self.assertEqual(get_sales_order_batch_transit("SO-001"), {})
        self.get_batch_holdings.assert_not_called()

    def test_sales_order_read_permission_is_required(self):
        self.sales_order.check_permission.side_effect = frappe.PermissionError

        with self.assertRaises(frappe.PermissionError):
            get_sales_order_batch_transit("SO-001")
        self.get_batch_holdings.assert_not_called()


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
