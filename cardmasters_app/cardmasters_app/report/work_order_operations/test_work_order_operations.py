from unittest import TestCase
from unittest.mock import patch

import frappe

from cardmasters_app.cardmasters_app.report.work_order_operations import work_order_operations as report


class TestWorkOrderOperations(TestCase):
    def test_sources_and_return_precedence(self):
        for values, expected in [
            ({"sales_order": "SO-1"}, ("Sales Order", "SO-1")),
            ({"material_request": "MR-1", "sales_order": "SO-1"}, ("Material Request", "MR-1")),
            ({"custom_document": "Material Request", "custom_document_id": "MR-2"},
             ("Material Request", "MR-2")),
            ({"custom_sales_return_reference": "RET-1", "sales_order": "SO-1"},
             ("Delivery Note", "RET-1")),
            ({}, ("", "")),
        ]:
            with self.subTest(values=values):
                self.assertEqual(report.source_order(values), expected)

    @patch.object(report, "_", side_effect=lambda value: value)
    def test_independent_lists_keep_repeated_operations_and_exact_progress(self, translate):
        orders = [{"name": "WO-1", "sales_order": "SO-1"}, {"name": "WO-2"}]
        operations = [
            {"parent": "WO-1", "operation": "Print", "custom_progress": "On Hold"},
            {"parent": "WO-1", "operation": "Print", "custom_progress": "Done"},
            {"parent": "WO-2", "operation": "Cut", "custom_progress": "In Progress"},
            {"parent": "WO-2", "operation": "Print", "custom_progress": None},
            {"parent": "UNAUTHORIZED", "operation": "Other", "custom_progress": "Done"},
        ]
        columns, rows = report.build_result(orders, operations)
        self.assertEqual(len(columns), 8)  # Three visible and one hidden per group.
        self.assertEqual(len(rows), 3)
        self.assertEqual(columns[0]["operation_group"], "Cut")
        self.assertEqual(rows[0]["operation_0_work_order"], "WO-2")
        self.assertEqual(rows[0]["operation_1_work_order"], "WO-1")
        self.assertEqual(rows[0]["operation_1_progress"], "On Hold")
        self.assertEqual(rows[1]["operation_1_progress"], "Done")
        self.assertEqual(rows[2]["operation_1_progress"], "")
        self.assertNotIn("operation_0_work_order", rows[1])
        self.assertEqual(rows[0]["operation_1_source_type"], "Sales Order")

    @patch.object(report.frappe, "get_meta")
    @patch.object(report.frappe, "get_list")
    @patch.object(report.frappe, "get_all")
    def test_only_permission_filtered_parents_are_used(self, get_all, get_list, get_meta):
        get_list.return_value = [frappe._dict(name="VISIBLE-WO")]
        get_all.return_value = []
        report.execute({"operation": "Cut", "progress": "On Hold", "company": "Example"})
        self.assertEqual(get_list.call_args.args, ("Work Order",))
        self.assertEqual(get_list.call_args.kwargs["filters"]["docstatus"], ["<", 2])
        child_filters = get_all.call_args.kwargs["filters"]
        self.assertEqual(child_filters["parent"], ["in", ["VISIBLE-WO"]])
        self.assertEqual(child_filters["operation"], "Cut")
        self.assertEqual(child_filters["custom_progress"], "On Hold")

    @patch.object(report.frappe, "get_meta")
    @patch.object(report.frappe, "get_list")
    @patch.object(report.frappe, "get_all", return_value=[])
    def test_branch_choice_and_multiple_operations(self, get_all, get_list, get_meta):
        get_list.return_value = [frappe._dict(name="VISIBLE-WO")]
        for source, expected in [
            (None, "custom_for_branch"),
            ("custom_for_branch", "custom_for_branch"),
            ("custom_production_branch", "custom_production_branch"),
            ("unexpected_field", "custom_for_branch"),
        ]:
            with self.subTest(source=source):
                report.execute({"branch": "Branch A", "branch_source": source,
                                "operation": ["Cut", "Print"]})
                self.assertEqual(get_list.call_args.kwargs["filters"], {
                    "docstatus": ["<", 2], expected: "Branch A",
                })
                self.assertEqual(get_all.call_args.kwargs["filters"]["operation"],
                                 ["in", ["Cut", "Print"]])
        report.execute({"branch_source": "custom_production_branch", "operation": []})
        self.assertEqual(get_list.call_args.kwargs["filters"], {"docstatus": ["<", 2]})
        self.assertNotIn("operation", get_all.call_args.kwargs["filters"])

    @patch.object(report.frappe, "get_meta")
    @patch.object(report.frappe, "get_list", return_value=[])
    @patch.object(report.frappe, "get_all")
    def test_empty_permissions_do_not_fetch_children(self, get_all, get_list, get_meta):
        self.assertEqual(report.execute(), ([], []))
        get_all.assert_not_called()
