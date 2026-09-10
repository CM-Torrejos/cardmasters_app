from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

import frappe

from cardmasters_app.cardmasters_app.report.production_tower import production_tower as report


class TestProductionTower(TestCase):
    def setUp(self):
        self.records = {
            "Sales Order": [], "Sales Order Item": [], "Material Request": [],
            "Material Request Item": [], "Work Order": [],
        }
        self.enterContext(patch.object(report.frappe, "get_all", side_effect=self.get_all))
        self.enterContext(patch.object(report, "_", side_effect=lambda text: text))

    def get_all(self, doctype, filters, fields, order_by):
        def matches(row):
            for field, condition in filters.items():
                value = row.get(field)
                if isinstance(condition, list):
                    operator, expected = condition
                    if operator == "in" and value not in expected:
                        return False
                    if operator == "not in" and value in expected:
                        return False
                    if operator == "!=" and value == expected:
                        return False
                    if operator == "between" and not expected[0] <= value <= expected[1]:
                        return False
                elif value != condition:
                    return False
            return True
        return [frappe._dict(deepcopy(row)) for row in self.records[doctype] if matches(row)]

    def request(self, name="MR-1", **values):
        row = dict(
            name=name, docstatus=1, material_request_type="Manufacture", status="Pending",
            workflow_state=None, schedule_date="2026-09-10", transaction_date="2026-09-01",
            custom_for_branch="Branch A",
        )
        row.update(values)
        self.records["Material Request"].append(row)

    def item(self, name="MRI-1", parent="MR-1", **values):
        row = dict(name=name, parent=parent, item_code="ITEM", item_name="Item", qty=10,
                   stock_qty=10, conversion_factor=1)
        row.update(values)
        self.records["Material Request Item"].append(row)

    def work_order(self, name="WO-1", **values):
        row = dict(name=name, docstatus=1, production_item="ITEM", status="In Process", qty=10,
                   produced_qty=5, custom_bypass=0, material_request="MR-1", material_request_item="MRI-1",
                   custom_document="Material Request", custom_document_id="MR-1",
                   custom_document_item_id="MRI-1")
        row.update(values)
        self.records["Work Order"].append(row)

    def test_only_active_submitted_manufacture_requests(self):
        self.request()
        for name, values in [
            ("Draft", {"docstatus": 0}), ("Cancelled", {"docstatus": 2}),
            ("Stopped", {"status": "Stopped"}), ("Purchase", {"material_request_type": "Purchase"}),
            ("Concluded", {"workflow_state": "Production Concluded"}),
            ("Ordered", {"status": "Ordered"}),
        ]:
            row = dict(self.records["Material Request"][0], name=name)
            row.update(values)
            self.records["Material Request"].append(row)
        roots = [row for row in report.execute()[1] if row["indent"] == 0]
        self.assertEqual([row["reference_name"] for row in roots], ["MR-1", "Ordered"])
        self.assertEqual(roots[0]["workflow_state"], "Pending")
        self.assertEqual(roots[0]["date"], "2026-09-10")
        self.assertIn("[MR] MR-1", roots[0]["label_name"])
        self.assertFalse(roots[0]["is_orphan_so"])

    def test_repeated_items_use_exact_rows_and_dual_links_do_not_double_count(self):
        self.request()
        self.item()
        self.item("MRI-2")
        self.work_order()
        self.work_order("WO-2", material_request_item="MRI-2", custom_document_item_id="MRI-2", qty=4)
        self.work_order("Cancelled", docstatus=2, qty=100)
        self.work_order("Wrong-item", production_item="OTHER", qty=100)
        self.work_order("No-row", material_request_item=None, custom_document_item_id=None, qty=100)
        rows = report.execute()[1]
        self.assertEqual([row.get("reference_name") for row in rows], ["MR-1", None, "WO-1", None, "WO-2"])
        self.assertEqual(rows[0]["qty"], "1 / 2")
        self.assertEqual(rows[1]["qty"], "10 / 10")
        self.assertEqual(rows[3]["qty"], "4 / 10")
        self.assertEqual(rows[3]["planning_status"], "shortfall")

    def test_stock_units_bypass_and_overproduction_use_existing_completion_rules(self):
        self.request()
        self.item(qty=2, stock_qty=20, conversion_factor=10)
        self.work_order(qty=10, produced_qty=0, custom_bypass=1)
        rows = report.execute()[1]
        self.assertEqual(rows[1]["qty"], "10 / 20")
        self.assertEqual(rows[1]["_sort_qty"], 0.5)
        self.assertEqual(rows[0]["completion_rate"], "50%")
        self.assertEqual(rows[2]["produced_qty"], 0)
        self.assertEqual(rows[2]["completion_rate"], "100%")
        self.assertTrue(rows[0]["is_bypass"])
        self.work_order("WO-2", qty=30, produced_qty=30)
        rows = report.execute()[1]
        self.assertEqual(rows[0]["completion_rate"], "100%")
        self.assertEqual(rows[1]["_sort_qty"], 2)

    def test_missing_bom_and_custom_only_work_orders_remain_visible(self):
        self.request()
        self.item()  # Deliberately no BOM: this is still manufacturing demand.
        rows = report.execute()[1]
        self.assertEqual(rows[1]["planning_status"], "orphan")
        self.assertEqual(rows[0]["qty"], "0 / 1")
        self.assertTrue(rows[0]["incomplete_coverage"])
        self.work_order(material_request=None, material_request_item=None)
        rows = report.execute()[1]
        self.assertEqual(rows[2]["reference_name"], "WO-1")
        self.assertEqual(rows[0]["qty"], "1 / 1")

    def test_standard_work_order_link_wins_over_conflicting_custom_link(self):
        self.request()
        self.item()
        self.item("MRI-2")
        self.work_order(custom_document_item_id="MRI-2")
        rows = report.execute()[1]
        self.assertEqual(rows[2]["reference_name"], "WO-1")
        self.assertEqual(rows[3]["planning_status"], "orphan")
        # A foreign standard parent cannot be reassigned via the custom fields.
        self.records["Work Order"][0]["material_request"] = "MR-OTHER"
        self.assertFalse(any(row["indent"] == 2 for row in report.execute()[1]))

    def test_filters_apply_to_material_requests(self):
        self.request()
        self.assertEqual(report.execute({"from_date": "2026-08-01", "to_date": "2026-08-31"})[1], [])
        self.assertEqual(len(report.execute({"from_date": "2026-09-01", "to_date": "2026-09-30"})[1]), 1)
        self.assertEqual(report.execute({"workflow_state": "Approved"})[1], [])
        self.records["Material Request"][0]["workflow_state"] = "Approved"
        self.assertEqual(report.execute({"workflow_state": "Approved"})[1][0]["workflow_state"], "Approved")

    def test_mixed_sources_keep_branches_and_shared_work_order_under_each_source(self):
        self.request()
        self.item()
        self.work_order(sales_order="SO-1", sales_order_item="SOI-1")
        self.records["Sales Order"] = [dict(name="SO-1", docstatus=1, customer="Customer",
            workflow_state="Production", delivery_date="2026-09-11")]
        self.records["Sales Order Item"] = [dict(name="SOI-1", parent="SO-1", item_code="ITEM",
            item_name="Item", qty=10, bom_no="BOM")]
        rows = report.execute()[1]
        self.assertEqual([row["indent"] for row in rows], [0, 1, 2, 0, 1, 2])
        self.assertEqual([row["reference_doctype"] for row in rows if row["indent"] == 0],
                         ["Sales Order", "Material Request"])
        self.assertEqual([row["completion_rate"] for row in rows if row["indent"] == 0], ["50%", "50%"])
        self.assertEqual([row["reference_name"] for row in rows if row["indent"] == 2], ["WO-1", "WO-1"])
