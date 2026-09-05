from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from cardmasters_app.cardmasters_app.services.material_request import (
    _check_workflow_permission,
    _validate_row_removal,
    _work_order_warning,
    update_material_request_details,
)


MODULE = "cardmasters_app.cardmasters_app.services.material_request"


class TestUpdateMaterialRequestDetails(TestCase):
    def setUp(self):
        self.row = frappe.get_doc({
            "doctype": "Material Request Item", "name": "MRI-1", "idx": 1,
            "item_code": "ITEM-1", "qty": 10, "stock_qty": 20, "rate": 5,
            "uom": "Box", "stock_uom": "Nos", "conversion_factor": 2,
            "schedule_date": "2026-09-10", "ordered_qty": 6, "received_qty": 4,
            "custom_item_specifics": "Old", "custom_particulars": "Details",
        })
        self.doc = MagicMock(doctype="Material Request", docstatus=1, status="Pending",
                             modified="2026-09-05 10:00:00", material_request_type="Purchase")
        self.doc.name = "MR-1"
        self.doc.items = [self.row]
        self.doc.remove.side_effect = self.doc.items.remove
        self.data = [{"docname": "MRI-1", "custom_item_specifics": "  New  "}]
        self.get_doc = self.enterContext(patch(f"{MODULE}.frappe.get_doc", return_value=self.doc))
        self.enterContext(patch(f"{MODULE}.get_workflow_name", return_value=None))
        self.work_orders = self.enterContext(patch(f"{MODULE}.frappe.get_all", return_value=[]))
        self.enterContext(patch.object(type(self.row), "precision", return_value=6))

    def update(self, **kwargs):
        return update_material_request_details("MR-1", self.data, self.doc.modified, **kwargs)

    def test_updates_custom_fields_with_document_validation(self):
        self.assertEqual(self.update(), {"updated": True})
        self.assertEqual(self.row.custom_item_specifics, "New")
        self.doc.check_permission.assert_called_once_with("write")
        self.doc.run_method.assert_called_once_with("validate")
        self.doc.save.assert_called_once()
        self.doc.update_requested_qty.assert_not_called()

    def test_quantity_change_updates_stock_amount_and_upstream_totals(self):
        self.data[0].update(qty=12, rate=7)
        self.update()
        self.assertEqual(self.row.stock_qty, 24)
        self.assertEqual(self.row.amount, 84)
        self.doc.update_requested_qty.assert_called_once()
        self.doc.update_requested_qty_in_production_plan.assert_called_once()
        self.doc.update_prevdoc_status.assert_called_once()
        self.doc.validate_budget.assert_called_once()
        self.assertEqual(self.doc._update_percent_field.call_count, 2)

    def test_manufacture_recalculates_completed_quantity(self):
        self.doc.material_request_type = "Manufacture"
        self.data[0]["qty"] = 12
        self.update()
        self.doc.update_completed_qty.assert_called_once()
        self.doc.update_prevdoc_status.assert_not_called()

    def test_rejects_reduction_below_fulfilled_stock_quantity(self):
        self.data[0]["qty"] = 2
        with self.assertRaises(frappe.ValidationError):
            self.update()
        self.doc.save.assert_not_called()

    def test_rejects_changed_conversion_below_fulfilled_quantity(self):
        self.data[0]["conversion_factor"] = 0.5
        with self.assertRaises(frappe.ValidationError):
            self.update()

    def test_rejects_invalid_numbers(self):
        for field, value in (("qty", 0), ("rate", -1), ("qty", "nan"), ("conversion_factor", "inf")):
            with self.subTest(field=field, value=value):
                self.data[0] = {"docname": "MRI-1", field: value}
                with self.assertRaises(frappe.ValidationError):
                    self.update()
                self.row.update({"qty": 10, "rate": 5, "conversion_factor": 2})
        self.doc.save.assert_not_called()

    def test_rejects_foreign_missing_and_duplicate_rows(self):
        for data in ([{"docname": "FOREIGN"}], [], [{"docname": "MRI-1"}] * 2):
            with self.subTest(data=data):
                self.data = data
                with self.assertRaises(frappe.ValidationError):
                    self.update()
        self.doc.save.assert_not_called()

    def test_rejects_item_replacement(self):
        self.data[0]["item_code"] = "OTHER-ITEM"
        with self.assertRaises(frappe.ValidationError):
            self.update()

    def test_adds_new_row_and_refreshes_totals(self):
        new_row = self.row.__class__({**self.row.as_dict(), "name": None, "ordered_qty": 0, "received_qty": 0})
        self.data.append({"item_code": "ITEM-1", "qty": 3, "custom_particulars": "New row"})
        with patch(f"{MODULE}._append_item", return_value=new_row) as append:
            self.update()
        append.assert_called_once_with(self.doc, self.data[1])
        self.assertEqual(new_row.qty, 3)
        self.assertEqual(new_row.custom_particulars, "New row")
        self.assertEqual(new_row.stock_qty, 6)
        self.doc.check_permission.assert_any_call("create")
        self.doc.save.assert_called_once()
        self.doc.update_requested_qty.assert_called_once()

    def test_add_requires_create_permission(self):
        self.data.append({"item_code": "ITEM-1"})
        self.doc.check_permission.side_effect = [None, frappe.PermissionError]
        with self.assertRaises(frappe.PermissionError):
            self.update()
        self.doc.save.assert_not_called()

    def test_removes_unlinked_row_and_refreshes_its_old_totals(self):
        removed = self.row.__class__({**self.row.as_dict(), "name": "MRI-2", "ordered_qty": 0, "received_qty": 0})
        self.doc.items.append(removed)
        with patch(f"{MODULE}._validate_row_removal") as validate, \
             patch(f"{MODULE}._refresh_removed_row_totals") as refresh:
            self.update()
        validate.assert_called_once_with(self.doc, removed)
        refresh.assert_called_once_with(self.doc, [removed])
        self.assertEqual(self.doc.items, [self.row])
        self.doc.save.assert_called_once()

    def test_blocks_removing_fulfilled_row(self):
        with self.assertRaises(frappe.ValidationError):
            _validate_row_removal(self.doc, self.row)

    def test_blocks_removing_row_referenced_by_draft_document(self):
        self.row.ordered_qty = self.row.received_qty = 0
        with patch(f"{MODULE}.frappe.db.exists", side_effect=lambda dt, filters: dt == "Purchase Order Item"):
            with self.assertRaises(frappe.ValidationError):
                _validate_row_removal(self.doc, self.row)

    def test_blocks_removing_row_referenced_by_custom_work_order(self):
        self.row.ordered_qty = self.row.received_qty = 0
        with patch(f"{MODULE}.frappe.db.exists", side_effect=lambda dt, filters: "custom_document_item_id" in filters):
            with self.assertRaises(frappe.ValidationError):
                _validate_row_removal(self.doc, self.row)

    def test_unlinked_row_passes_standard_and_dynamic_link_checks(self):
        self.row.ordered_qty = self.row.received_qty = 0
        with patch(f"{MODULE}.frappe.db.exists", return_value=False), \
             patch(f"{MODULE}.check_if_doc_is_linked") as linked, \
             patch(f"{MODULE}.check_if_doc_is_dynamically_linked") as dynamic:
            _validate_row_removal(self.doc, self.row)
        linked.assert_called_once_with(self.row)
        dynamic.assert_called_once_with(self.row)

    def test_rejects_stale_edit(self):
        with self.assertRaises(frappe.TimestampMismatchError):
            update_material_request_details("MR-1", self.data, "2026-09-04 10:00:00")
        self.doc.save.assert_not_called()

    def test_rejects_draft_cancelled_and_stopped(self):
        for docstatus, status in ((0, "Draft"), (2, "Cancelled"), (1, "Stopped")):
            self.doc.docstatus, self.doc.status = docstatus, status
            with self.assertRaises(frappe.ValidationError):
                self.update()
        self.doc.save.assert_not_called()

    def test_enforces_write_permission(self):
        self.doc.check_permission.side_effect = frappe.PermissionError
        with self.assertRaises(frappe.PermissionError):
            self.update()
        self.doc.save.assert_not_called()

    def test_requires_confirmation_before_writing_linked_work_order_changes(self):
        self.work_orders.return_value = ["WO-1"]
        result = self.update()
        self.assertTrue(result["confirmation_required"])
        self.assertIn("WO-1", result["message"])
        self.assertEqual(len(self.work_orders.call_args_list), 2)
        self.doc.save.assert_not_called()

    def test_confirmed_update_saves(self):
        self.work_orders.return_value = ["WO-1"]
        self.assertEqual(self.update(confirm_work_orders=True), {"updated": True})
        self.doc.save.assert_called_once()

    def test_warning_escapes_user_content_and_deduplicates_work_orders(self):
        self.work_orders.return_value = ["WO-1"]
        self.row.custom_item_specifics = "<script>alert(1)</script>"
        warning = _work_order_warning(self.doc, [(self.row, {"custom_item_specifics": "Old"},
                                                  ["custom_item_specifics"])])
        self.assertNotIn("<script>", warning)
        self.assertIn("&lt;script&gt;", warning)
        self.assertEqual(warning.count("WO-1"), 1)

    def test_enforces_workflow_edit_role(self):
        workflow = frappe._dict(workflow_state_field="workflow_state", states=[
            frappe._dict(state="Approved", allow_edit="Stock Manager")])
        self.doc.get.return_value = "Approved"
        with patch(f"{MODULE}.get_workflow_name", return_value="MR Workflow"), \
             patch(f"{MODULE}.frappe.get_doc", return_value=workflow), \
             patch(f"{MODULE}.frappe.get_roles", return_value=["Stock User"]):
            with self.assertRaises(frappe.PermissionError):
                _check_workflow_permission(self.doc)
