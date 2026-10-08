from unittest import TestCase, TestSuite, TextTestRunner, defaultTestLoader
from unittest.mock import MagicMock, patch
from datetime import date

import frappe

from cardmasters_app.cardmasters_app.api import delivery_backlog as backlog


class TestDeliveryBacklog(TestCase):
    def test_existing_batch_stock_still_advances_work_order_before_delivery_submission(self):
        order = MagicMock()
        order.name, order.company, order.customer = "SO-TEST", "COMPANY", "CUSTOMER"
        order.items = [frappe._dict(name="SOI-TEST", item_code="FG")]
        note = MagicMock()
        note.name, note.docstatus, note.is_return = "DN-TEST", 0, 0
        note.company, note.customer = order.company, order.customer
        note.get.return_value = []
        note.items = [frappe._dict(so_detail="SOI-TEST", against_sales_order=order.name,
                                  item_code="FG", stock_qty=5, warehouse="FG-WH", idx=1)]
        branch = frappe._dict(custom_source_warehouse="SOURCE", custom_workinprogress_warehouse="WIP")
        item = frappe._dict(is_stock_item=1, has_batch_no=1, has_serial_no=0)
        work = MagicMock()
        work.custom_batch = "SO-TEST_SOI-TEST"
        events = []
        with patch.object(backlog.frappe.db, "sql"), \
                patch.object(backlog.frappe, "get_doc", return_value=note), \
                patch.object(backlog.frappe, "get_cached_doc", side_effect=lambda doctype, name: branch if doctype == "Branch" else item), \
                patch.object(backlog.frappe.db, "get_value", return_value=frappe._dict(company=order.company, is_group=0, disabled=0)), \
                patch.object(backlog, "_update_order_header"), \
                patch.object(backlog, "_work_order", return_value=work), \
                patch("erpnext.stock.doctype.batch.batch.get_batch_qty", return_value=5), \
                patch.object(backlog, "_stock_entry") as stock_entry, \
                patch.object(backlog, "_advance_work_order_to_claiming", side_effect=lambda doc: events.append("claiming")) as advance, \
                patch.object(backlog, "_workflow_action", side_effect=lambda doc, status: events.append("delivery")):
            result = backlog._submit(order, [note.name], date(2026, 9, 1))
        stock_entry.assert_not_called()
        advance.assert_called_once_with(work)
        self.assertEqual(events, ["claiming", "delivery"])
        self.assertEqual(result["delivery_notes"], [note.name])

    def test_claiming_walks_forward_from_each_supported_state(self):
        actions = ["Start", "For Consumption", "For Claiming", "Finished Manufacture Entry"]
        for initial_state in backlog.CLAIMING_STATES:
            with self.subTest(state=initial_state):
                work = MagicMock(name="work")
                work.name = "WO-TEST"
                work.docstatus = 1
                current = [initial_state]
                work.get.side_effect = lambda field: current[0]

                def transitions(doc):
                    index = backlog.CLAIMING_STATES.index(current[0])
                    transition = frappe._dict(action=actions[index], next_state=backlog.CLAIMING_STATES[index + 1])
                    return [transition, transition]  # Same action allowed for multiple roles.

                def apply(doc, action):
                    index = backlog.CLAIMING_STATES.index(current[0])
                    self.assertEqual(action, actions[index])
                    current[0] = backlog.CLAIMING_STATES[index + 1]
                    return doc

                with patch("frappe.model.workflow.get_workflow_name", return_value="WO-WORKFLOW"), \
                        patch.object(backlog.frappe, "get_cached_doc", return_value=frappe._dict(workflow_state_field="workflow_state")), \
                        patch("frappe.model.workflow.get_transitions", side_effect=transitions), \
                        patch("frappe.model.workflow.apply_workflow", side_effect=apply) as apply_workflow:
                    self.assertIs(backlog._advance_work_order_to_claiming(work), work)
                self.assertEqual(current[0], "In Claiming")
                self.assertEqual(apply_workflow.call_count, 4 - backlog.CLAIMING_STATES.index(initial_state))
                work.reload.assert_called_once()
                self.assertEqual(work.add_comment.call_count, int(initial_state != "In Claiming"))

    def test_claiming_rejects_blocked_or_ambiguous_transitions(self):
        work = MagicMock()
        work.name = "WO-TEST"
        work.get.return_value = "In Production"
        for transitions in ([], [frappe._dict(action="A", next_state="Pending Consumption"),
                                frappe._dict(action="B", next_state="Pending Consumption")]):
            with patch("frappe.model.workflow.get_workflow_name", return_value="WO-WORKFLOW"), \
                    patch.object(backlog.frappe, "get_cached_doc", return_value=frappe._dict(workflow_state_field="workflow_state")), \
                    patch("frappe.model.workflow.get_transitions", return_value=transitions), \
                    patch("frappe.model.workflow.apply_workflow") as apply_workflow, \
                    patch.object(backlog.frappe, "throw", side_effect=frappe.ValidationError):
                with self.assertRaises(frappe.ValidationError):
                    backlog._advance_work_order_to_claiming(work)
            apply_workflow.assert_not_called()

    def test_claiming_rejects_missing_workflow_and_unsupported_state(self):
        work = MagicMock()
        work.get.return_value = "Production"
        for workflow_name in (None, "WO-WORKFLOW"):
            with patch("frappe.model.workflow.get_workflow_name", return_value=workflow_name), \
                    patch.object(backlog.frappe, "get_cached_doc", return_value=frappe._dict(workflow_state_field="workflow_state")), \
                    patch("frappe.model.workflow.apply_workflow") as apply_workflow, \
                    patch.object(backlog.frappe, "throw", side_effect=frappe.ValidationError):
                with self.assertRaises(frappe.ValidationError):
                    backlog._advance_work_order_to_claiming(work)
            apply_workflow.assert_not_called()

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
        for method in ("Cash", "Credit", "Credit Memo"):
            order = frappe._dict(custom_payment_method=method)
            with patch.object(backlog.frappe.db, "sql") as sql:
                self.assertEqual(backlog._payment_method(order), method)
            sql.assert_not_called()

    def test_receipt_types_and_cash_fallback(self):
        order = frappe._dict(name="SO-TEST", customer="CUSTOMER", company="COMPANY")
        for receipt, expected in backlog.PAYMENT_METHODS.items():
            with patch.object(backlog.frappe.db, "sql", return_value=[(receipt,)]):
                self.assertEqual(backlog._payment_method(order), expected)
        for receipts in ([], [("Acknowledgement Receipt",), ("Collection Receipt",)],
                         [("Other",)], [(None,)], [("",)], [("Collection Receipt",), ("Other",)]):
            with self.subTest(receipts=receipts), \
                    patch.object(backlog.frappe.db, "sql", return_value=receipts):
                self.assertEqual(backlog._payment_method(order), "Cash")

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
