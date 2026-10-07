from unittest import TestCase, TestSuite, TextTestRunner, defaultTestLoader
from unittest.mock import MagicMock, patch
from datetime import date

import frappe

from cardmasters_app.cardmasters_app.api import delivery_backlog as backlog


class TestDeliveryBacklog(TestCase):
    def test_header_update_does_not_save_or_unlock_submitted_item_fields(self):
        order = MagicMock()
        row = frappe._dict(name="SOI-TEST", idx=1, custom_item_specifics="  Legacy specifics  ", custom_particulars=" Details ")
        order.items = [row]
        with patch.object(backlog, "_payment_method", return_value="Cash"), \
                patch.object(backlog.frappe.db, "set_value") as set_value, \
                patch.object(backlog.frappe, "get_meta") as get_meta:
            backlog._update_order_header(order)
        order.db_set.assert_called_once_with({"custom_payment_method": "Cash", "custom_production_branch": backlog.BRANCH})
        order.save.assert_not_called()
        get_meta.assert_not_called()
        set_value.assert_called_once_with("Sales Order Item", "SOI-TEST",
                                         {"custom_item_specifics": "Legacy specifics", "custom_particulars": "Details"},
                                         update_modified=False)
        self.assertEqual(order.add_comment.call_count, 2)

    def test_payment_method_preserves_existing_value(self):
        order = frappe._dict(custom_payment_method="Credit")
        with patch.object(backlog.frappe.db, "sql") as sql:
            self.assertEqual(backlog._payment_method(order), "Credit")
        sql.assert_not_called()

    def test_receipt_types_and_ambiguous_payments(self):
        order = frappe._dict(name="SO-TEST", customer="CUSTOMER", company="COMPANY")
        for receipt, expected in backlog.PAYMENT_METHODS.items():
            with patch.object(backlog.frappe.db, "sql", return_value=[(receipt,)]):
                self.assertEqual(backlog._payment_method(order), expected)
        for receipts in ([], [("Acknowledgement Receipt",), ("Collection Receipt",)], [("Other",)]):
            with patch.object(backlog.frappe.db, "sql", return_value=receipts), \
                    patch.object(backlog.frappe, "throw", side_effect=frappe.ValidationError):
                with self.assertRaises(frappe.ValidationError):
                    backlog._payment_method(order)

    def test_system_manager_is_required_server_side(self):
        with patch.object(backlog.frappe, "only_for", side_effect=frappe.PermissionError), \
                patch.object(backlog.frappe, "get_doc") as get_doc:
            with self.assertRaises(frappe.PermissionError):
                backlog._authorize("SO-TEST")
        get_doc.assert_not_called()

    def test_ambiguous_active_boms_are_rejected(self):
        with patch.object(backlog.frappe, "get_all", return_value=[
            frappe._dict(name="BOM-A", is_default=0), frappe._dict(name="BOM-B", is_default=0)
        ]), patch.object(backlog.frappe, "throw", side_effect=frappe.ValidationError):
            with self.assertRaises(frappe.ValidationError):
                backlog._active_bom("FG", "COMPANY")

    def test_default_active_bom_is_selected(self):
        with patch.object(backlog.frappe, "get_all", return_value=[
            frappe._dict(name="BOM-A", is_default=0), frappe._dict(name="BOM-B", is_default=1)
        ]):
            self.assertEqual(backlog._active_bom("FG", "COMPANY"), "BOM-B")

    def test_submission_failure_rolls_back_all_changes(self):
        order = MagicMock()
        order.name = "SO-TEST"
        order.docstatus = 1
        order.status = "To Deliver and Bill"
        with patch.object(backlog, "_authorize", return_value=order), \
                patch.object(backlog, "_submit", side_effect=frappe.ValidationError), \
                patch.object(backlog.frappe.db, "sql"), \
                patch.object(backlog.frappe.db, "savepoint") as savepoint, \
                patch.object(backlog, "getdate", return_value=date(2026, 10, 7)), \
                patch.object(backlog.frappe.db, "rollback") as rollback:
            with self.assertRaises(frappe.ValidationError):
                backlog.submit_delivery_backlog("SO-TEST", '["DN-TEST"]', "2026-09-24")
        savepoint.assert_called_once_with("delivery_backlog")
        rollback.assert_called_once_with(save_point="delivery_backlog")


def run_unit_tests():
    suite = TestSuite([defaultTestLoader.loadTestsFromTestCase(TestDeliveryBacklog)])
    result = TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Delivery backlog tests failed")
    return {"tests": result.testsRun, "success": True}


def rollback_smoke_test(sales_order, delivery_note, target_month):
    """Exercise real local ERP controllers without committing business records."""
    try:
        order = frappe.get_doc("Sales Order", sales_order)
        descriptions = [(row.name, str(row.custom_item_specifics).strip() if row.custom_item_specifics else row.custom_item_specifics,
                         str(row.custom_particulars).strip() if row.custom_particulars else row.custom_particulars) for row in order.items]
        result = backlog.submit_delivery_backlog(sales_order, frappe.as_json([delivery_note]), target_month)
        assert frappe.db.get_value("Delivery Note", delivery_note, "docstatus") == 1
        order.reload()
        assert descriptions == [(row.name, row.custom_item_specifics, row.custom_particulars) for row in order.items]
        stock_count = frappe.db.count("Stock Entry")
        try:
            backlog.submit_delivery_backlog(sales_order, frappe.as_json([delivery_note]), target_month)
        except frappe.ValidationError:
            pass
        else:
            raise AssertionError("A second click must reject an already submitted Delivery Note")
        assert frappe.db.count("Stock Entry") == stock_count
        return result
    finally:
        frappe.db.rollback()
