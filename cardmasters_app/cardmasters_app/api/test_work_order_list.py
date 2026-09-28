from unittest import TestCase
from unittest.mock import patch

import frappe

from cardmasters_app.cardmasters_app.api import work_order_list as api


class TestWorkOrderListProgress(TestCase):
    @patch.object(api.frappe, "get_meta")
    @patch.object(api.frappe, "get_list", return_value=["VISIBLE"])
    @patch.object(api.frappe, "get_all")
    def test_permissions_filters_and_repeated_operations(self, get_all, get_list, get_meta):
        get_all.return_value = [
            frappe._dict(parent="VISIBLE", operation="Print", custom_progress="Not Started", idx=1),
            frappe._dict(parent="VISIBLE", operation="Print", custom_progress="Done", idx=3),
        ]
        filters = [
            ["Work Order Operation", "operation", "in", ["Print", "Cut"]],
            ["Work Order Operation", "custom_progress", "!=", "On Hold"],
        ]
        result = api.get_operation_progress(["VISIBLE", "HIDDEN"], filters)
        self.assertEqual(list(result), ["VISIBLE"])
        self.assertEqual([row["progress"] for row in result["VISIBLE"]], ["Not Started", "Done"])
        self.assertEqual([row["idx"] for row in result["VISIBLE"]], [1, 3])
        query = get_all.call_args.kwargs["filters"]
        self.assertIn(["parent", "in", ["VISIBLE"]], query)
        self.assertIn(["parenttype", "=", "Work Order"], query)
        self.assertIn(["parentfield", "=", "operations"], query)
        for condition in filters:
            self.assertIn(condition, query)

    @patch.object(api.frappe, "get_meta")
    @patch.object(api.frappe, "get_list", return_value=[])
    @patch.object(api.frappe, "get_all")
    def test_no_visible_parents_or_no_filters(self, get_all, get_list, get_meta):
        self.assertEqual(api.get_operation_progress(["HIDDEN"], [
            ["Work Order Operation", "operation", "=", "Print"],
        ]), {})
        get_all.assert_not_called()
        get_list.reset_mock()
        self.assertEqual(api.get_operation_progress(["VISIBLE"], []), {})
        get_list.assert_not_called()

    @patch.object(api.frappe, "get_meta")
    @patch.object(api.frappe, "get_all")
    @patch.object(api.frappe, "throw", side_effect=ValueError)
    @patch.object(api, "_", side_effect=lambda text: text)
    def test_rejects_other_doctypes(self, translate, throw, get_all, get_meta):
        with self.assertRaises(ValueError):
            api.get_operation_progress(["WO"], [["User", "email", "=", "example"]])
        get_all.assert_not_called()
