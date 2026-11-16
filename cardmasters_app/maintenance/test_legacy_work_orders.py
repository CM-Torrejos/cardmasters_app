"""Local integration checks. All fixture changes are rolled back.

bench --site SITE execute cardmasters_app.maintenance.test_legacy_work_orders.run_tests
Requires at least one eligible legacy order in the local test data.
"""

import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

import frappe

from cardmasters_app.maintenance import legacy_work_orders as cleanup


def row(**kwargs):
    return frappe._dict(kwargs)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.items = [row(name="a", item_code="ITEM", stock_qty=10),
                      row(name="b", item_code="ITEM", stock_qty=2)]

    def test_combined_deliveries_cover_repeated_items(self):
        deliveries = [row(so_detail="a", item_code="ITEM", stock_qty=4),
                      row(so_detail="a", item_code="ITEM", stock_qty=6),
                      row(so_detail="b", item_code="ITEM", stock_qty=2)]
        self.assertIsNone(cleanup.coverage_reason(self.items, deliveries))

    def test_quantity_on_one_row_cannot_cover_another(self):
        self.assertIsNotNone(cleanup.coverage_reason(self.items, [
            row(so_detail="a", item_code="ITEM", stock_qty=12)]))

    def test_missing_and_mismatched_references_are_rejected(self):
        for detail, item in [(None, "ITEM"), ("other", "ITEM"), ("a", "WRONG")]:
            with self.subTest(detail=detail, item=item):
                self.assertIsNotNone(cleanup.coverage_reason(self.items, [
                    row(so_detail=detail, item_code=item, stock_qty=12)]))

    def test_non_positive_quantity_is_rejected(self):
        for qty in (0, -1):
            self.assertIsNotNone(cleanup.coverage_reason(self.items, [
                row(so_detail="a", item_code="ITEM", stock_qty=qty)]))

    def test_only_exact_legacy_names_match(self):
        self.assertTrue(cleanup.LEGACY_NAME.fullmatch("SO-000007_MFG6067"))
        for name in ("MFG-WO-00001", "SO-1_MFG1-extra", "SO-A_MFG1", "SO-1xMFG1"):
            self.assertFalse(cleanup.LEGACY_NAME.fullmatch(name))


class ProgressTests(unittest.TestCase):
    def invoke(self, plan, apply=0, progress=1, failure=None):
        output = StringIO()
        with patch.object(frappe, "get_all", return_value=[row(name="SO-1_MFG1", sales_order="SO-1")]), \
             patch.object(cleanup, "inspect_order", return_value=plan), \
             patch.object(cleanup, "_apply", side_effect=failure), \
             patch.object(frappe.db, "savepoint"), \
             patch.object(frappe.db, "commit"), \
             patch.object(frappe.db, "rollback"), redirect_stderr(output):
            result = cleanup.run(apply=apply, progress=progress)
        return result, output.getvalue()

    def test_preview_reports_current_order_and_totals(self):
        result, output = self.invoke({"sales_order": "SO-1", "eligible": True})
        self.assertEqual(result["counts"]["eligible"], 1)
        for message in ("Starting PREVIEW", "[1/1] Checking SO-1", "ELIGIBLE SO-1", "Finished:"):
            self.assertIn(message, output)

    def test_apply_reports_commit_or_rollback(self):
        plan = {"sales_order": "SO-1", "eligible": True}
        result, output = self.invoke(plan, apply=1)
        self.assertEqual(result["counts"]["completed"], 1)
        self.assertIn("COMMITTED SO-1", output)
        result, output = self.invoke(plan, apply=1, failure=RuntimeError("blocked"))
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertIn("FAILED SO-1 (rolled back): RuntimeError: blocked", output)
        self.assertNotIn("COMMITTED", output)

    def test_skip_reason_and_quiet_option(self):
        plan = {"sales_order": "SO-1", "reason": "Linked Stock Entries exist"}
        result, output = self.invoke(plan)
        self.assertEqual(result["counts"]["skipped"], 1)
        self.assertIn("SKIPPED SO-1: Linked Stock Entries exist", output)
        quiet_result, output = self.invoke(plan, progress=0)
        self.assertEqual(result, quiet_result)
        self.assertEqual(output, "")


class LocalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plans = cleanup.run(limit=1)["eligible"]
        if not plans:
            raise RuntimeError("Local integration checks require an eligible legacy Sales Order")
        cls.order = plans[0]["sales_order"]

    def setUp(self):
        frappe.db.savepoint("legacy_test")
        self.plan = cleanup.inspect_order(self.order)
        self.assertTrue(self.plan.get("eligible"), self.plan)

    def tearDown(self):
        frappe.db.rollback()
        frappe.clear_document_cache("Sales Order", self.order)

    def insert_stub(self, doctype, **values):
        # Minimal DB-only fixtures exercise selectors without manufacturing stock.
        doc = frappe.get_doc({"doctype": doctype, "name": "cleanup-test-" + frappe.generate_hash(length=10),
                              **values})
        doc.db_insert()
        return doc

    def test_stock_entries_block_all_statuses_and_custom_links(self):
        for field in ("work_order", "custom_work_order_for_repack"):
            if not frappe.get_meta("Stock Entry").has_field(field):
                continue
            for status in (0, 1, 2):
                entry = self.insert_stub("Stock Entry", docstatus=status, **{field: self.plan["work_orders"][0]})
                plan = cleanup.inspect_order(self.order)
                self.assertEqual(plan.get("reason"), "Linked Stock Entries exist")
                frappe.db.delete("Stock Entry", {"name": entry.name})

    def test_job_card_stock_entry_blocks_entire_order(self):
        job = self.insert_stub("Job Card", work_order=self.plan["work_orders"][0], docstatus=1)
        self.insert_stub("Stock Entry", job_card=job.name, docstatus=0)
        result = cleanup.inspect_order(self.order)
        self.assertFalse(result.get("eligible"))
        self.assertEqual(result["reason"], "Linked Stock Entries exist")
        self.assertEqual(frappe.db.get_value("Job Card", job.name, "docstatus"), 1)
        self.assertTrue(frappe.db.exists("Work Order", self.plan["work_orders"][0]))

    def test_submitted_delivery_and_incomplete_billing_are_rejected(self):
        dn = self.plan["delivery_notes"][0]
        frappe.db.set_value("Delivery Note", dn, "docstatus", 1)
        self.assertIn("not a draft", cleanup.inspect_order(self.order)["reason"])
        frappe.db.set_value("Delivery Note", dn, "docstatus", 0)
        frappe.db.set_value("Sales Order", self.order, "per_billed", 99)
        self.assertIn("fully invoiced", cleanup.inspect_order(self.order)["reason"])

    def test_shared_delivery_is_rejected(self):
        dn = self.plan["delivery_notes"][0]
        self.insert_stub("Delivery Note Item", parent=dn, parenttype="Delivery Note",
                         parentfield="items", against_sales_order="", item_code="OTHER", qty=1, stock_qty=1)
        self.assertIn("outside", cleanup.inspect_order(self.order)["reason"])

    def test_real_lifecycle_with_draft_and_submitted_job_cards(self):
        jobs = [self.insert_stub("Job Card", work_order=self.plan["work_orders"][0], docstatus=status,
                                 production_item=frappe.db.get_value("Work Order", self.plan["work_orders"][0], "production_item"))
                for status in (0, 1)]
        plan = cleanup.inspect_order(self.order)
        cleanup._apply(plan)
        for name in plan["work_orders"]:
            self.assertFalse(frappe.db.exists("Work Order", name))
        for name in plan["delivery_notes"]:
            self.assertFalse(frappe.db.exists("Delivery Note", name))
        for job in jobs:
            self.assertFalse(frappe.db.exists("Job Card", job.name))
        self.assertEqual(frappe.db.get_value("Sales Order", self.order, "status"), "Closed")
        frappe.db.rollback(save_point="legacy_test")
        self.assertTrue(cleanup.inspect_order(self.order).get("eligible"))

    def test_failure_after_deletion_rolls_everything_back(self):
        original_apply = cleanup._apply

        def fail_after_deletion(plan, **kwargs):
            original_apply(plan, **kwargs)
            raise RuntimeError("injected failure after closing")

        with patch.object(cleanup, "_apply", side_effect=fail_after_deletion):
            result = cleanup.run(apply=1, sales_order=self.order)
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertTrue(cleanup.inspect_order(self.order).get("eligible"))
        for name in self.plan["work_orders"]:
            self.assertTrue(frappe.db.exists("Work Order", name))

    def test_preview_changes_nothing(self):
        before = frappe.get_doc("Sales Order", self.order).modified
        result = cleanup.run(sales_order=self.order)
        self.assertEqual(result["counts"]["eligible"], 1)
        self.assertEqual(frappe.get_doc("Sales Order", self.order).modified, before)


def run_tests():
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(CoverageTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(ProgressTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(LocalIntegrationTests),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Legacy cleanup tests failed")
    return {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)}


def run_progress_tests():
    """Check output using mocks; safe while a real cleanup is running."""
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(CoverageTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(ProgressTests),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Legacy cleanup progress tests failed")
    return {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)}
