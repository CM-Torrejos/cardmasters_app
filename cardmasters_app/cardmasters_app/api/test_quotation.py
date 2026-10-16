from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from cardmasters_app.cardmasters_app.api.quotation import update_details


class TestQuotationUpdateDetailsPermissions(TestCase):
    def setUp(self):
        self.items = [
            frappe._dict(
                name=name, item_code="ITEM-1", qty=1, rate=10, uom="Nos", conversion_factor=1,
                flags=frappe._dict(), check_permission=MagicMock(), cancel=MagicMock(), delete=MagicMock(),
            )
            for name in ("ROW-1", "ROW-2")
        ]
        self.doc = MagicMock(
            doctype="Quotation", docstatus=1, status="Open", modified="2026-10-16 10:00:00",
            items=self.items, flags=frappe._dict(),
        )
        self.doc.has_permission.return_value = False
        self.data = [
            dict(docname=row.name, item_code=row.item_code, qty=2, rate=10, uom="Nos",
                 conversion_factor=1, custom_particulars=" Updated ")
            for row in self.items
        ]
        get_doc = patch(
            "cardmasters_app.cardmasters_app.api.quotation.frappe.get_doc", return_value=self.doc
        )
        core_update = patch("erpnext.controllers.accounts_controller.update_child_qty_rate")
        get_doc.start()
        self.addCleanup(get_doc.stop)
        self.core_update = core_update.start()
        self.addCleanup(core_update.stop)
        ordered_items = patch("erpnext.selling.doctype.quotation.quotation.get_ordered_items", return_value={})
        self.ordered_items = ordered_items.start()
        self.addCleanup(ordered_items.stop)

    def update(self, data=None):
        return update_details("QTN-1", self.data if data is None else data, self.doc.modified)

    def test_existing_rows_can_be_updated_without_cancel_or_delete_permission(self):
        self.assertEqual(self.update(), {"updated": True})
        self.doc.check_permission.assert_called_once_with("write")
        self.doc.has_permission.assert_not_called()
        self.core_update.assert_called_once_with(
            "Quotation", frappe.as_json(self.data), "QTN-1", "items"
        )
        self.assertEqual(self.items[0].custom_particulars, "Updated")
        self.doc.save.assert_called_once_with()

    def test_writers_can_remove_owned_rows_without_cancel_or_delete_permission(self):
        self.assertEqual(self.update(self.data[:1]), {"updated": True})
        self.doc.check_permission.assert_called_once_with("write")
        self.doc.has_permission.assert_not_called()
        self.assertFalse(self.doc.flags.get("ignore_permissions"))
        self.assertFalse(self.items[0].flags.get("ignore_permissions"))
        self.items[0].check_permission.assert_not_called()
        self.items[0].cancel.assert_not_called()
        self.items[0].delete.assert_not_called()
        self.items[1].check_permission.assert_called_once_with("write")
        self.assertTrue(self.items[1].flags.ignore_permissions)
        self.items[1].cancel.assert_called_once_with()
        self.items[1].delete.assert_called_once_with()
        self.core_update.assert_called_once_with(
            "Quotation", frappe.as_json(self.data[:1]), "QTN-1", "items"
        )

    def test_ordered_rows_cannot_be_removed(self):
        self.ordered_items.return_value = {"ROW-2": 1}
        with self.assertRaisesRegex(frappe.ValidationError, "Cannot delete an item which has been ordered"):
            self.update(self.data[:1])
        self.items[1].cancel.assert_not_called()
        self.items[1].delete.assert_not_called()
        self.core_update.assert_not_called()
        self.doc.save.assert_not_called()

    def test_item_table_write_restrictions_are_checked_before_removal(self):
        self.items[1].check_permission.side_effect = frappe.PermissionError
        with self.assertRaises(frappe.PermissionError):
            self.update(self.data[:1])
        self.assertFalse(self.items[1].flags.get("ignore_permissions"))
        self.items[1].cancel.assert_not_called()
        self.items[1].delete.assert_not_called()
        self.core_update.assert_not_called()

    def test_link_checks_still_prevent_removal(self):
        self.items[1].cancel.side_effect = frappe.LinkExistsError("Linked to a submitted document")
        with self.assertRaisesRegex(frappe.LinkExistsError, "Linked to a submitted document"):
            self.update(self.data[:1])
        self.items[1].delete.assert_not_called()
        self.core_update.assert_not_called()
        self.doc.save.assert_not_called()

    def test_write_permission_is_required_before_any_update(self):
        self.doc.check_permission.side_effect = frappe.PermissionError
        with self.assertRaises(frappe.PermissionError):
            self.update(self.data[:1])
        self.core_update.assert_not_called()
        self.doc.save.assert_not_called()
        self.items[1].cancel.assert_not_called()
        self.items[1].delete.assert_not_called()

    def test_foreign_rows_are_rejected_before_removal(self):
        self.data[0]["docname"] = "OTHER-QUOTATION-ROW"
        with self.assertRaisesRegex(frappe.ValidationError, "does not belong to this Quotation"):
            self.update(self.data[:1])
        self.core_update.assert_not_called()
        self.items[1].cancel.assert_not_called()
        self.items[1].delete.assert_not_called()

    def test_stale_requests_are_rejected_before_removal(self):
        with self.assertRaises(frappe.TimestampMismatchError):
            update_details("QTN-1", self.data[:1], "2026-10-16 09:00:00")
        self.core_update.assert_not_called()
        self.items[1].cancel.assert_not_called()
        self.items[1].delete.assert_not_called()
