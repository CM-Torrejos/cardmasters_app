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
            "Delivery Note": [], "Delivery Note Item": [], "Work Order Operation": [],
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
        self.work_order(sales_order="SO-1", sales_order_item="SOI-1", custom_blue_order=0, custom_rush_order=1)
        self.records["Sales Order"] = [dict(name="SO-1", docstatus=1, customer="Customer",
            workflow_state="Production", delivery_date="2026-09-11", custom_blue_order=1, custom_rush_order=0)]
        self.records["Sales Order Item"] = [dict(name="SOI-1", parent="SO-1", item_code="ITEM",
            item_name="Item", qty=10, bom_no="BOM")]
        rows = report.execute()[1]
        self.assertEqual([row["indent"] for row in rows], [0, 1, 2, 0, 1, 2])
        self.assertEqual([row["reference_doctype"] for row in rows if row["indent"] == 0],
                         ["Sales Order", "Material Request"])
        self.assertEqual([row["completion_rate"] for row in rows if row["indent"] == 0], ["50%", "50%"])
        self.assertEqual([row["reference_name"] for row in rows if row["indent"] == 2], ["WO-1", "WO-1"])
        self.assertEqual((rows[0]["custom_blue_order"], rows[0]["custom_rush_order"]), (1, 0))
        for row in (rows[2], rows[5]):
            self.assertEqual((row["custom_blue_order"], row["custom_rush_order"]), (0, 1))
        for row in (rows[1], rows[3], rows[4]):
            self.assertIsNone(row.get("custom_blue_order"))
            self.assertIsNone(row.get("custom_rush_order"))
        columns = {column["fieldname"]: column for column in report.get_columns()}
        self.assertNotIn("is_bypass", columns)
        self.assertEqual(columns["custom_blue_order"]["fieldtype"], "Check")
        self.assertEqual(columns["custom_rush_order"]["fieldtype"], "Check")

    def filter_sources(self):
        self.records["Sales Order"] = [dict(
            name="SO-1", docstatus=1, customer="Customer", workflow_state="Production",
            company="Company A", transaction_date="2026-09-01", delivery_date="2026-09-10",
            branch="Branch A", custom_production_branch="Branch B",
        )]
        self.records["Sales Order Item"] = [dict(
            name="SOI-1", parent="SO-1", item_code="ITEM", item_name="Item", qty=10, bom_no="BOM",
        )]
        self.request(company="Company A", custom_production_branch="Branch B")
        self.item()
        self.work_order(sales_order="SO-1", sales_order_item="SOI-1")

    def test_sales_orders_are_batched_and_work_orders_keep_exact_item_links(self):
        self.filter_sources()
        self.records["Material Request"] = []
        self.records["Work Order"] = []
        self.records["Sales Order Item"].append(dict(
            self.records["Sales Order Item"][0], name="SOI-2"))
        self.work_order("First", sales_order="SO-1", sales_order_item="SOI-1", qty=4)
        self.work_order("Second", sales_order="SO-1", sales_order_item="SOI-2", qty=6)
        self.work_order("Wrong-code", sales_order="SO-1", sales_order_item="SOI-1", production_item="OTHER")
        self.work_order("Wrong-parent", sales_order="SO-OTHER", sales_order_item="SOI-1")
        self.work_order("Cancelled", sales_order="SO-1", sales_order_item="SOI-1", docstatus=2)
        rows = report.execute()[1]
        self.assertEqual([row.get("reference_name") for row in rows],
                         ["SO-1", None, "First", None, "Second"])
        self.assertEqual([row["qty"] for row in rows if row["indent"] == 1], ["4 / 10", "6 / 10"])

        # Crossing a batch boundary adds two queries, not one per order/item.
        for index in range(501):
            name = f"BATCH-{index}"
            self.records["Sales Order"].append(dict(self.records["Sales Order"][0], name=name))
            self.records["Sales Order Item"].append(dict(
                self.records["Sales Order Item"][0], name=f"ITEM-{index}", parent=name))
        report.frappe.get_all.reset_mock()
        branches = report.get_sales_order_branches(frappe._dict())
        self.assertEqual(len(branches), 502)
        self.assertEqual(report.frappe.get_all.call_count, 5)

    def test_company_and_target_date_filter_both_sources_with_complete_trees(self):
        self.filter_sources()
        for doctype in ("Sales Order", "Material Request"):
            self.records[doctype].append(dict(self.records[doctype][0], name="Other-company", company="Company B"))
        rows = report.execute({"company": "Company A", "target_date": "2026-09-10"})[1]
        self.assertEqual([row.get("reference_name") for row in rows],
                         ["SO-1", None, "WO-1", "MR-1", None, "WO-1"])
        self.assertEqual([row["indent"] for row in rows], [0, 1, 2, 0, 1, 2])
        self.assertEqual(report.execute({"company": "Missing"})[1], [])
        # Target date is the displayed delivery/schedule date, not transaction date.
        self.assertEqual(report.execute({"target_date": "2026-09-01"})[1], [])
        self.records["Material Request"][0]["schedule_date"] = "2026-09-11"
        rows = report.execute({"company": "Company A", "target_date": "2026-09-11"})[1]
        self.assertEqual(rows[0]["reference_name"], "MR-1")
        self.assertEqual(len(rows), 3)

    def test_branch_source_switches_fields_for_both_sources(self):
        self.filter_sources()
        for source, matching_branch, excluded_branch in (
            ("branch", "Branch A", "Branch B"),
            ("custom_production_branch", "Branch B", "Branch A"),
        ):
            with self.subTest(source=source):
                filters = dict(company="Company A", target_date="2026-09-10", branch_source=source)
                rows = report.execute(dict(filters, branch=matching_branch))[1]
                self.assertEqual([row["reference_name"] for row in rows if row["indent"] == 0],
                                 ["SO-1", "MR-1"])
                self.assertEqual(len(rows), 6)
                self.assertEqual(report.execute(dict(filters, branch=excluded_branch))[1], [])
                # Selecting a source alone does not restrict the report.
                self.assertEqual(len(report.execute(filters)[1]), 6)
        self.assertEqual(len(report.execute({"branch": "Branch A"})[1]), 6)
        self.assertEqual(report.execute({"branch": "Missing"})[1], [])
        # API callers cannot use branch_source to filter an arbitrary field.
        self.assertEqual(report.execute({"branch_source": "company", "branch": "Company A"})[1], [])

    def sales_return(self, name="SR-1", **values):
        self.records["Delivery Note"].append(dict(
            dict(name=name, docstatus=1, is_return=1, customer="Customer", company="Company A",
                 posting_date="2026-09-12", status="Return", branch="Branch A",
                 custom_production_branch="Branch B"), **values))

    def return_item(self, name="SRI-1", parent="SR-1", **values):
        self.records["Delivery Note Item"].append(dict(
            dict(name=name, parent=parent, item_code="ITEM", item_name="Item", qty=-10, stock_qty=-10,
                 conversion_factor=1, custom_for_backjob=1, against_sales_order="SO-1", so_detail="SOI-1"),
            **values))

    def backjob(self, name="BACKJOB-1", **values):
        self.work_order(name, **dict(dict(custom_sales_return_reference="SR-1", custom_document="Sales Order",
                        custom_document_id="SO-1", custom_document_item_id="SOI-1",
                        material_request=None, material_request_item=None), **values))

    def test_only_submitted_returns_with_checked_items_are_included_without_work_orders(self):
        self.sales_return()
        self.return_item(against_sales_order=None, so_detail=None)
        self.return_item("Unchecked", custom_for_backjob=0)
        for name, values in (("Draft", {"docstatus": 0}), ("Cancelled", {"docstatus": 2}),
                             ("Delivery", {"is_return": 0})):
            self.sales_return(name, **values)
            self.return_item(name, parent=name)
        self.sales_return("No-backjob")
        self.return_item("No-backjob", parent="No-backjob", custom_for_backjob=0)
        self.sales_return("Empty")
        rows = report.execute()[1]
        self.assertEqual([row.get("reference_name") for row in rows], ["SR-1", None])
        self.assertEqual(rows[0]["reference_doctype"], "Delivery Note")
        self.assertIn("[SR] SR-1", rows[0]["label_name"])
        self.assertEqual(rows[0]["qty"], "0 / 1")
        self.assertEqual(rows[1]["qty"], "0 / 10")
        self.assertEqual(rows[1]["planning_status"], "orphan")
        self.assertIsNone(rows[0]["date"])

    def test_backjobs_use_return_and_exact_so_item_links_without_double_counting_batch_splits(self):
        self.sales_return()
        self.return_item(qty=-2, stock_qty=-20, conversion_factor=10)
        self.return_item("Split", qty=-1, stock_qty=None, conversion_factor=10)
        self.return_item("Repeated-code", so_detail="SOI-2", stock_qty=-5)
        self.return_item("Unchecked", so_detail="SOI-3", custom_for_backjob=0)
        self.backjob(qty=30, produced_qty=15, custom_blue_order=1, custom_rush_order=0)
        self.backjob("Second-item", custom_document_item_id="SOI-2", qty=5, produced_qty=0, custom_bypass=1)
        for name, values in (
            ("Cancelled", {"docstatus": 2}), ("Other-return", {"custom_sales_return_reference": "SR-2"}),
            ("Original-WO", {"custom_sales_return_reference": None}),
            ("Other-item", {"production_item": "OTHER"}), ("Other-SO", {"custom_document_id": "SO-OTHER"}),
            ("Unchecked", {"custom_document_item_id": "SOI-3"}),
        ):
            self.backjob(name, **values)
        rows = report.execute()[1]
        self.assertEqual([row.get("reference_name") for row in rows],
                         ["SR-1", None, "BACKJOB-1", None, "Second-item"])
        self.assertEqual(rows[0]["qty"], "2 / 2")
        self.assertEqual(rows[1]["qty"], "30 / 30")
        self.assertEqual(rows[0]["completion_rate"], "57%")
        self.assertEqual(rows[2]["custom_blue_order"], 1)
        # Older records with standard SO links also match the exact return item.
        wo = self.records["Work Order"][0]
        wo.update(custom_document=None, custom_document_id=None, custom_document_item_id=None,
                  sales_order="SO-1", sales_order_item="SOI-1")
        self.assertEqual(report.execute()[1][2]["reference_name"], "BACKJOB-1")

    def test_return_filters_use_own_branches_and_linked_order_date_even_after_so_concludes(self):
        self.records["Sales Order"] = [dict(
            name="SO-1", docstatus=1, workflow_state="Production Concluded", delivery_date="2026-09-20",
            branch="Original Branch", custom_production_branch="Original Production Branch")]
        self.sales_return()
        self.return_item()
        self.backjob()
        for source, branch in (("branch", "Branch A"), ("custom_production_branch", "Branch B")):
            filters = dict(company="Company A", target_date="2026-09-20", branch_source=source, branch=branch)
            rows = report.execute(filters)[1]
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["date"], "2026-09-20")
            self.assertEqual(report.execute(dict(filters, branch="Missing"))[1], [])
            original_branch = "Original Production Branch" if source == "custom_production_branch" else "Original Branch"
            self.assertEqual(report.execute(dict(filters, branch=original_branch))[1], [])
        self.assertEqual(report.execute({"company": "Other"})[1], [])
        self.assertEqual(report.execute({"target_date": "2026-09-12"})[1], [])
        self.assertEqual(report.execute({"from_date": "2026-09-01", "to_date": "2026-09-11"})[1], [])
        self.assertEqual(len(report.execute({"workflow_state": "Return"})[1]), 3)
        self.assertEqual(report.execute({"workflow_state": "Approved"})[1], [])

    def test_return_branch_filters_work_without_linked_sales_orders(self):
        self.sales_return()
        self.return_item(against_sales_order=None, so_detail=None)
        for source, branch in (("branch", "Branch A"), ("custom_production_branch", "Branch B")):
            with self.subTest(source=source):
                rows = report.execute({"branch_source": source, "branch": branch})[1]
                self.assertEqual([row["indent"] for row in rows], [0, 1])
                self.assertEqual(rows[0]["reference_name"], "SR-1")
                self.assertIsNone(rows[0]["date"])
                self.assertEqual(report.execute({"branch_source": source, "branch": "Missing"})[1], [])
        self.assertEqual(len(report.execute({"branch": "Branch A"})[1]), 2)
        self.assertEqual(report.execute({"branch_source": "company", "branch": "Company A"})[1], [])

    def test_return_blank_branches_do_not_fall_back_to_original_order(self):
        self.records["Sales Order"] = [dict(
            name="SO-1", docstatus=1, workflow_state="Production Concluded",
            branch="Branch A", custom_production_branch="Branch B")]
        self.sales_return(branch=None, custom_production_branch=None)
        self.return_item()
        for source, branch in (("branch", "Branch A"), ("custom_production_branch", "Branch B")):
            self.assertEqual(report.execute({"branch_source": source, "branch": branch})[1], [])
            self.assertEqual(len(report.execute({"branch_source": source})[1]), 2)

    def test_return_branch_filter_keeps_all_items_from_different_original_branches(self):
        self.records["Sales Order"] = [dict(
            name="SO-1", docstatus=1, workflow_state="Production Concluded", delivery_date="2026-09-20",
            branch="Branch A", custom_production_branch="Branch B"), dict(
            name="SO-2", docstatus=1, workflow_state="Production Concluded", delivery_date="2026-09-18",
            branch="Other Branch", custom_production_branch="Other Production Branch")]
        self.sales_return()
        self.return_item()
        self.return_item("SRI-2", against_sales_order="SO-2", so_detail="SOI-2")
        self.backjob()
        self.backjob("BACKJOB-2", custom_document_id="SO-2", custom_document_item_id="SOI-2")
        for source, branch in (("branch", "Branch A"), ("custom_production_branch", "Branch B")):
            rows = report.execute({"branch_source": source, "branch": branch})[1]
            self.assertEqual([row.get("reference_name") for row in rows],
                             ["SR-1", None, "BACKJOB-1", None, "BACKJOB-2"])
            self.assertEqual(rows[0]["date"], "2026-09-18")

    def test_returns_sort_with_existing_sources_and_keep_their_own_work_orders(self):
        self.filter_sources()
        self.sales_return()
        self.return_item()
        self.backjob()
        rows = report.execute()[1]
        self.assertEqual([row["reference_name"] for row in rows if row["indent"] == 0],
                         ["SO-1", "MR-1", "SR-1"])
        self.assertEqual([row["reference_name"] for row in rows if row["indent"] == 2],
                         ["WO-1", "WO-1", "BACKJOB-1"])
        self.assertEqual([row["indent"] for row in rows], [0, 1, 2] * 3)

    def test_hide_completed_removes_complete_sources_and_can_be_disabled(self):
        self.filter_sources()
        self.sales_return()
        self.return_item()
        self.backjob(produced_qty=10)
        self.records["Work Order"][0]["produced_qty"] = 10
        original = report.execute()[1]
        self.assertEqual(len(original), 9)
        for enabled in (1, "1", True):
            self.assertEqual(report.execute({"hide_completed": enabled})[1], [])
        for disabled in (0, "0", False):
            self.assertEqual(report.execute({"hide_completed": disabled})[1], original)

    def test_hide_completed_prunes_items_and_work_orders_without_changing_totals(self):
        self.request()
        self.item()
        self.item("MRI-2")
        self.item("MRI-3")  # Unplanned demand stays visible.
        self.work_order(produced_qty=10)
        # An extra unfinished WO below a completed item must not be reparented.
        self.work_order("Extra", qty=1, produced_qty=0)
        self.work_order("Bypassed", material_request_item="MRI-2", qty=4,
                        produced_qty=0, custom_bypass=1)
        self.work_order("Partial", material_request_item="MRI-2", qty=6, produced_qty=2)
        original = report.execute()[1]
        rows = report.execute({"hide_completed": 1})[1]
        self.assertEqual([row.get("reference_name") for row in rows],
                         ["MR-1", None, "Partial", None])
        self.assertEqual([row["indent"] for row in rows], [0, 1, 2, 1])
        self.assertEqual(rows[0], original[0])
        self.assertEqual(rows[1], original[4])
        self.assertEqual(rows[1]["completion_rate"], "60%")
        self.assertEqual(rows[-1]["planning_status"], "orphan")
        self.assertFalse(any(row["completion_rate"] == "100%" for row in rows))

    def test_hide_completed_keeps_nearly_complete_and_empty_entries(self):
        self.request()
        self.item()
        self.work_order(produced_qty=9.99)
        self.request("Empty")
        original = report.execute()[1]
        self.assertEqual(original[0]["completion_rate"], "99%")
        self.assertEqual(report.execute({"hide_completed": 1})[1], original)

    def test_concluded_workflow_counts_full_quantity_for_all_sources_until_posted(self):
        self.filter_sources()
        self.sales_return()
        self.return_item()
        self.backjob()
        for state in ("Pending Consumption", "Pending Claiming", "In Claiming"):
            for posted_qty in (0, 4, 10, 12):
                with self.subTest(state=state, posted_qty=posted_qty):
                    for wo in self.records["Work Order"]:
                        wo.update(workflow_state=state, produced_qty=posted_qty)
                    rows = report.execute()[1]
                    expected = "100% (Pending Posting)" if posted_qty < 10 else "100%"
                    self.assertEqual(len(rows), 9)
                    self.assertTrue(all(row["completion_rate"] == expected for row in rows))
                    # Workflow completion never invents quantities in Produced.
                    self.assertTrue(all(row["produced_qty"] == posted_qty for row in rows if row["indent"] > 0))
                    self.assertEqual(report.execute({"hide_completed": 1})[1], [])

    def test_other_workflow_states_use_posted_quantity_and_preserve_bypass(self):
        self.request()
        self.item()
        self.work_order()
        for state in (None, "Not Started", "In Production", "Finished Consumption"):
            for posted_qty in (5, 10):
                with self.subTest(state=state, posted_qty=posted_qty):
                    self.records["Work Order"][0].update(workflow_state=state, produced_qty=posted_qty)
                    expected = "50%" if posted_qty == 5 else "100%"
                    self.assertTrue(all(row["completion_rate"] == expected for row in report.execute()[1]))
        self.records["Work Order"][0].update(custom_bypass=1, produced_qty=0, workflow_state="Pending Consumption")
        self.assertTrue(all(row["completion_rate"] == "100%" for row in report.execute()[1]))

    def test_mixed_posted_and_concluded_work_orders_roll_up_without_double_counting(self):
        self.request()
        self.item()
        self.item("MRI-2")
        self.work_order(qty=6, produced_qty=2, workflow_state="Pending Consumption")
        self.work_order("Posted", qty=4, produced_qty=4)
        self.work_order("Second-item", material_request_item="MRI-2", qty=10, produced_qty=0)
        self.work_order("Cancelled", docstatus=2, qty=100, workflow_state="Pending Consumption")
        rows = report.execute()[1]
        self.assertEqual(rows[0]["completion_rate"], "50% (Pending Posting)")
        self.assertEqual(rows[1]["completion_rate"], "100% (Pending Posting)")
        self.assertEqual(rows[1]["produced_qty"], 6)
        self.assertEqual(rows[1]["qty"], "10 / 10")
        filtered = report.execute({"hide_completed": 1})[1]
        self.assertEqual([row.get("reference_name") for row in filtered], ["MR-1", None, "Second-item"])
        self.assertEqual(filtered[0], rows[0])
        # Reverting the WO state removes its unposted progress immediately.
        self.records["Work Order"][0]["workflow_state"] = "In Production"
        rows = report.execute()[1]
        self.assertEqual(rows[0]["completion_rate"], "30%")
        self.assertEqual(rows[1]["completion_rate"], "60%")

    def test_posted_requirement_does_not_inherit_pending_label_from_extra_work_order(self):
        self.request()
        self.item()
        self.item("MRI-2")
        self.work_order(produced_qty=10)
        self.work_order("Extra", qty=10, produced_qty=0, workflow_state="Pending Consumption")
        rows = report.execute()[1]
        self.assertEqual(rows[0]["completion_rate"], "50%")
        self.assertEqual(rows[1]["completion_rate"], "100%")
        extra = next(row for row in rows if row.get("reference_name") == "Extra")
        self.assertEqual(extra["completion_rate"], "100% (Pending Posting)")

    def test_operation_leaves_use_manual_progress_without_changing_parent_totals(self):
        self.filter_sources()
        self.sales_return()
        self.return_item()
        self.backjob()
        original = report.execute()[1]
        for parent in ("WO-1", "BACKJOB-1"):
            for index, progress in enumerate(("Not Started", "In Progress", "On Hold", "Done", None)):
                self.records["Work Order Operation"].append(dict(
                    name=f"{parent}-OP-{index}", parent=parent, parenttype="Work Order",
                    parentfield="operations", operation="Cutting", custom_progress=progress,
                    planned_end_time="2026-09-20 12:30:00", completed_qty=2.5))
        rows = report.execute()[1]
        # Operation presence changes the coverage hint, not parent totals.
        for row in original:
            if row["indent"] == 2:
                self.assertTrue(row["has_no_operations"])
                row["has_no_operations"] = False
        self.assertEqual([row for row in rows if row["indent"] < 3], original)
        leaves = [row for row in rows if row["indent"] == 3]
        self.assertEqual(len(leaves), 15)  # Shared WO appears under SO and MR, plus backjob.
        current_wo = None
        for row in rows:
            if row["indent"] == 2:
                current_wo = row["reference_name"]
            if row["indent"] == 3:
                self.assertEqual(row["reference_name"], current_wo)
                self.assertEqual(row["label_name"], "Operations: Cutting")
                self.assertEqual(row["date"], "2026-09-20")
                self.assertEqual(row["produced_qty"], 2.5)
                self.assertEqual(row["qty"], 10)
        self.assertEqual([row["completion_rate"] for row in leaves[:5]],
                         ["Not Started", "In Progress", "On Hold", "Done", ""])
        visible = report.execute({"hide_completed": 1})[1]
        self.assertEqual(len([row for row in visible if row["indent"] == 3]), 12)
        self.assertFalse(any(row["completion_rate"] == "Done" for row in visible))
        for wo in self.records["Work Order"]:
            wo["produced_qty"] = 10
        self.assertEqual(report.execute({"hide_completed": 1})[1], [])

    def test_operations_only_attach_to_exact_work_order_operations_table(self):
        self.request()
        self.item()
        self.work_order()
        for parent, parenttype, parentfield in (("Other", "Work Order", "operations"),
                                               ("WO-1", "Other", "operations"),
                                               ("WO-1", "Work Order", "other")):
            self.records["Work Order Operation"].append(dict(
                parent=parent, parenttype=parenttype, parentfield=parentfield))
        self.assertEqual([row["indent"] for row in report.execute()[1]], [0, 1, 2])
