import json
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from cardmasters_app.cardmasters_app.doctype.cardmasters_settings import cardmasters_settings
from cardmasters_app.cardmasters_app.event_handlers import artist_card, sales_order, work_order
from cardmasters_app.cardmasters_app.services import sales_order_workflow as workflow


class TestSalesOrderWorkflowAutomation(TestCase):
    def test_checkbox_values(self):
        for value, disabled in ((None, True), (0, True), ("0", True), (1, False), ("1", False)):
            with self.subTest(value=value), patch.object(frappe.db, "get_single_value", return_value=value):
                self.assertEqual(cardmasters_settings.sales_order_workflow_automation_disabled(), disabled)

    def test_all_automatic_entry_points_skip_without_touching_sales_order(self):
        for module, handler in (
            (sales_order, sales_order.check_artist_status),
            (artist_card, artist_card.update_so_workflow_state),
            (work_order, work_order.sales_order_state_transition),
            (work_order, work_order.work_order_workflow_trigger),
        ):
            with self.subTest(handler=handler.__name__), \
                    patch.object(module, "sales_order_workflow_automation_disabled", return_value=True), \
                    patch.object(frappe, "get_doc") as get_doc, \
                    patch("frappe.model.workflow.apply_workflow") as apply:
                handler(frappe._dict(sales_order="SO-TEST", docstatus=2), "on_cancel")
            get_doc.assert_not_called()
            apply.assert_not_called()

    def test_enabled_cancellation_keeps_existing_revert_behavior(self):
        order = Mock(workflow_state="Production Concluded")
        order.name = "SO-TEST"
        order.items = [frappe._dict(name="SOI-TEST", qty=10, bom_no="BOM-TEST")]
        doc = frappe._dict(name="WO-TEST", sales_order=order.name, docstatus=2,
                           sales_order_item="SOI-TEST", qty=10, workflow_state="In Claiming")
        with patch.object(work_order, "sales_order_workflow_automation_disabled", return_value=False), \
                patch.object(frappe, "get_doc", return_value=order), \
                patch.object(frappe, "get_all", return_value=[]), \
                patch("frappe.model.workflow.get_transitions", return_value=[frappe._dict(action="Revert to Production")]), \
                patch("frappe.model.workflow.apply_workflow") as apply:
            work_order.work_order_workflow_trigger(doc, "on_cancel")
        apply.assert_called_once_with(order, "Revert to Production")

    def test_enabled_layout_automation_still_runs(self):
        doc = Mock(custom_artist="ARTIST")
        with patch.object(sales_order, "sales_order_workflow_automation_disabled", return_value=False), \
                patch("frappe.model.workflow.apply_workflow") as apply:
            sales_order.check_artist_status(doc, "after_submit")
        apply.assert_called_once_with(doc, "Begin Layout")


class TestSalesOrderWorkflowProtection(TestCase):
    def setUp(self):
        self.doc = Mock()
        self.doc.name = "SO-TEST"
        self.doc.is_new.return_value = False
        self.doc.get.return_value = "Production"
        self.doc.get_doc_before_save.return_value = frappe._dict(workflow_state="Production Concluded")
        for target, kwargs in (
            ("sales_order_workflow_automation_disabled", {"return_value": True}),
            ("get_workflow_name", {"return_value": "SO-WORKFLOW"}),
        ):
            patcher = patch.object(workflow, target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(frappe, "get_cached_doc", return_value=frappe._dict(workflow_state_field="workflow_state"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_indirect_changes_are_rejected_for_every_save_action(self):
        for event in ("before_save", "before_submit", "before_cancel", "before_update_after_submit"):
            with self.subTest(event=event), patch.object(frappe, "throw", side_effect=frappe.ValidationError), \
                    patch.dict(frappe.flags, {"manual_sales_order_workflow": None}):
                with self.assertRaises(frappe.ValidationError):
                    workflow.protect_sales_order_workflow(self.doc, event)

    def test_unrelated_updates_keep_existing_state(self):
        self.doc.get.return_value = "Production Concluded"
        with patch.object(frappe, "throw") as error:
            workflow.protect_sales_order_workflow(self.doc)
        error.assert_not_called()

    def test_new_order_can_receive_initial_state(self):
        self.doc.is_new.return_value = True
        with patch.object(frappe, "throw") as error:
            workflow.protect_sales_order_workflow(self.doc)
        error.assert_not_called()

    def test_enabled_automation_allows_state_changes(self):
        with patch.object(workflow, "sales_order_workflow_automation_disabled", return_value=False), \
                patch.object(frappe, "throw") as error:
            workflow.protect_sales_order_workflow(self.doc)
        error.assert_not_called()

    def test_manual_action_only_authorizes_its_own_sales_order(self):
        for name, allowed in (("SO-TEST", True), ("SO-OTHER", False)):
            with self.subTest(name=name), patch.dict(frappe.flags, {"manual_sales_order_workflow": name}), \
                    patch.object(frappe, "throw", side_effect=frappe.ValidationError):
                if allowed:
                    workflow.protect_sales_order_workflow(self.doc)
                else:
                    with self.assertRaises(frappe.ValidationError):
                        workflow.protect_sales_order_workflow(self.doc)

    def test_manual_endpoint_delegates_to_standard_workflow_and_restores_flag(self):
        data = {"doctype": "Sales Order", "name": "SO-TEST"}

        def apply(doc, action):
            self.assertEqual(frappe.flags.manual_sales_order_workflow, "SO-TEST")
            self.assertEqual(action, "Revert to Production")
            workflow.protect_sales_order_workflow(self.doc)
            return self.doc

        with patch.dict(frappe.flags, {"manual_sales_order_workflow": None}), \
                patch.object(workflow, "apply_workflow", side_effect=apply):
            self.assertIs(workflow.apply_manual_workflow(json.dumps(data), "Revert to Production"), self.doc)
            self.assertIsNone(frappe.flags.manual_sales_order_workflow)

    def test_failed_manual_action_clears_authorization(self):
        with patch.dict(frappe.flags, {"manual_sales_order_workflow": None}), \
                patch.object(workflow, "apply_workflow", side_effect=frappe.PermissionError):
            with self.assertRaises(frappe.PermissionError):
                workflow.apply_manual_workflow({"doctype": "Sales Order", "name": "SO-TEST"}, "Revert to Production")
            self.assertIsNone(frappe.flags.manual_sales_order_workflow)

    def test_other_doctypes_do_not_authorize_sales_orders(self):
        data = {"doctype": "Work Order", "name": "WO-TEST"}

        def apply(doc, action):
            self.assertIsNone(frappe.flags.get("manual_sales_order_workflow"))

        with patch.dict(frappe.flags, {"manual_sales_order_workflow": None}), \
                patch.object(workflow, "apply_workflow", side_effect=apply) as core:
            workflow.apply_manual_workflow(data, "Start")
        core.assert_called_once_with(data, "Start")
