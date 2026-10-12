from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from cardmasters_app.cardmasters_app.doctype.withdrawal.withdrawal import (
	Withdrawal, before_cancel_generated_transfer, validate_generated_transfer,
)


class TestWithdrawal(TestCase):
	def setUp(self):
		self.precision = patch.object(Withdrawal, "quantity_precision", return_value=3)
		self.precision.start()
		self.addCleanup(self.precision.stop)
		self.throw = patch("frappe.throw", side_effect=frappe.ValidationError)
		self.throw.start()
		self.addCleanup(self.throw.stop)

	def doc(self, quantity, rows):
		return frappe.get_doc({"doctype": "Withdrawal", "planned_withdrawal_qty": quantity,
			"work_orders": [{"work_order": name, "net_print_qty": qty} for name, qty in rows]})

	def test_proportional_allocation_and_duplicate_work_orders(self):
		doc = self.doc(100, [("WO-A", 25), ("WO-B", 30), ("WO-A", 25)])
		doc.calculate_allocation(strict=True)
		self.assertEqual(doc.allowance_qty, 20)
		self.assertEqual([row.withdrawal_qty for row in doc.work_orders], [31.25, 37.5, 31.25])

	def test_rounding_reconciles_in_stock_precision(self):
		doc = self.doc(1, [("A", .1), ("B", .1), ("C", .1)])
		doc.calculate_allocation(strict=True)
		self.assertEqual(sum(Decimal(str(row.withdrawal_qty)) for row in doc.work_orders), Decimal(1))
		self.assertEqual([row.allocated_allowance_qty for row in doc.work_orders], [.234, .233, .233])

	def test_incomplete_drafts_and_invalid_submission(self):
		for quantity, rows in [(None, []), (10, [(None, 0)]), (10, [("A", 12)]), (10, [("A", -1)])]:
			with self.subTest(quantity=quantity, rows=rows):
				doc = self.doc(quantity, rows)
				doc.calculate_allocation()
				with self.assertRaises(frappe.ValidationError):
					doc.calculate_allocation(strict=True)

	def test_zero_allowance(self):
		doc = self.doc(80, [("A", 50), ("B", 30)])
		doc.calculate_allocation(strict=True)
		self.assertEqual(doc.allowance_qty, 0)
		self.assertEqual([row.withdrawal_qty for row in doc.work_orders], [50, 30])

	def test_nonfinite_quantities_rejected(self):
		for quantity in (float("nan"), float("inf")):
			with self.assertRaises(frappe.ValidationError):
				self.doc(quantity, [("A", 1)]).calculate_allocation()

	def test_partial_manufacture_allowed_full_and_split_full_blocked(self):
		doc = self.doc(10, [("A", 5)])
		doc.company = "Company"
		doc.wip_warehouse = "WIP"
		wo = frappe._dict(name="A", qty=2, docstatus=1, status="In Process", company="Company",
			wip_warehouse="WIP", skip_transfer=0, transfer_material_against="Work Order")
		wo.check_permission = MagicMock()
		with patch("frappe.get_doc", return_value=wo), patch("frappe.db", new=MagicMock()) as db:
			for quantities, blocked in [([1], False), ([2], True), ([1, 1], True)]:
				db.sql.return_value = [frappe._dict(fg_completed_qty=qty) for qty in quantities]
				for submission in (True, False):
					if blocked:
						with self.assertRaises(frappe.ValidationError):
							doc.get_work_orders(for_submission=submission)
					else:
						self.assertEqual(list(doc.get_work_orders(for_submission=submission)), ["A"])
				self.assertIn("docstatus in (0, 1)", db.sql.call_args.args[0])

	def test_generated_transfers_cannot_be_edited_or_cancelled_independently(self):
		doc = frappe._dict(custom_withdrawal="WD-1", flags=frappe._dict())
		with self.assertRaises(frappe.ValidationError):
			validate_generated_transfer(doc)
		with self.assertRaises(frappe.ValidationError):
			before_cancel_generated_transfer(doc)
		doc.flags.withdrawal_creation = "WD-1"
		validate_generated_transfer(doc)
		doc.flags.withdrawal_cancellation = "WD-1"
		before_cancel_generated_transfer(doc)
		self.assertIn("Withdrawal Work Order", doc.ignore_linked_doctypes)

	def test_closed_unsubmitted_and_incompatible_work_orders_rejected(self):
		doc = self.doc(10, [("A", 5)])
		doc.company = "Company"
		doc.wip_warehouse = "WIP"
		base = dict(name="A", qty=2, docstatus=1, status="In Process", company="Company",
			wip_warehouse="WIP", skip_transfer=0, transfer_material_against="Work Order")
		for change in ({"docstatus": 0}, {"status": "Stopped"}, {"status": "Closed"},
			{"company": "Other"}, {"wip_warehouse": "Other"}, {"skip_transfer": 1},
			{"transfer_material_against": "Job Card"}):
			wo = frappe._dict(base | change)
			wo.check_permission = MagicMock()
			with self.subTest(change=change), patch("frappe.get_doc", return_value=wo):
				with self.assertRaises(frappe.ValidationError):
					doc.get_work_orders(for_submission=True)

	def test_quantity_precision_reconciles_header_and_rows(self):
		doc = self.doc(1.00049, [("A", .30049), ("B", .40049)])
		doc.calculate_allocation(strict=True)
		self.assertEqual(doc.planned_withdrawal_qty, 1)
		self.assertEqual(sum(Decimal(str(row.withdrawal_qty)) for row in doc.work_orders), Decimal(1))

	def test_submission_groups_rows_and_uses_zero_bom_qty_for_additional_material(self):
		doc = self.doc(10, [("A", 2), ("A", 3), ("B", 3)])
		doc.name = "WD-TEST"
		doc.item = "Material"
		doc.company = "Company"
		doc.source_warehouse = "Advanced WIP"
		doc.wip_warehouse = "WIP"
		doc.stock_uom = doc.uom = "Inch"
		doc.calculate_allocation(strict=True)
		doc.flags.withdrawal_work_orders = {
			name: frappe._dict(name=name, qty=2, bom_no="BOM", project=None) for name in ("A", "B")
		}
		entries = []

		def new_entry(doctype):
			self.assertEqual(doctype, "Stock Entry")
			entry = MagicMock(name="entry")
			entry.name = f"STE-{len(entries)}"
			entry.get_item_details.return_value = frappe._dict()
			entries.append(entry)
			return entry

		with patch("frappe.new_doc", side_effect=new_entry), patch("frappe.db", new=MagicMock()) as db:
			db.sql.return_value = [(2,)]
			with patch("frappe.model.document.Document.db_set") as db_set:
				doc.on_submit()
				self.assertEqual(db_set.call_count, 3)
		self.assertEqual(len(entries), 2)
		self.assertEqual([entry.append.call_args.args[1].qty for entry in entries], [6.25, 3.75])
		for entry in entries:
			self.assertEqual(entry.update.call_args.args[0]["fg_completed_qty"], 0)
			self.assertEqual(entry.update.call_args.args[0]["custom_withdrawal"], doc.name)
			entry.insert.assert_called_once()
			entry.submit.assert_called_once()
