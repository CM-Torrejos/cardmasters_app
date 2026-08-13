# Copyright (c) 2026, Shan Torrejos and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from cardmasters_app.cardmasters_app.event_handlers.sales_order import (
	get_grant_covered_amount,
)


class TestGrant(FrappeTestCase):
	def test_order_can_consume_entire_remaining_grant(self):
		grant = frappe._dict(name="TEST-GRANT", available_balance=9000)

		self.assertEqual(get_grant_covered_amount(grant, 9100), 9000)

	def test_order_uses_only_its_total_when_grant_has_more_value(self):
		grant = frappe._dict(name="TEST-GRANT", available_balance=9000)

		self.assertEqual(get_grant_covered_amount(grant, 5000), 5000)

	def test_zero_balance_grant_is_rejected(self):
		grant = frappe._dict(name="TEST-GRANT", available_balance=0)

		with self.assertRaises(frappe.ValidationError):
			get_grant_covered_amount(grant, 9100)
