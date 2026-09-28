import json
import unittest

import frappe

from cardmasters_app.cardmasters_app.overrides.workspace import CustomWorkspace


class TestWorkspaceCardFilters(unittest.TestCase):
    def setUp(self):
        frappe.db.savepoint("card_filter_test")

    def tearDown(self):
        frappe.db.rollback(save_point="card_filter_test")

    def test_save_reload_and_rebuild_duplicate_targets(self):
        doc = frappe.new_doc("Workspace")
        self.assertIsInstance(doc, CustomWorkspace)
        doc.label = "Card filter test " + frappe.generate_hash(length=10)
        doc.title = doc.label
        doc.public = 0
        doc.for_user = frappe.session.user
        doc.content = "[]"
        rows = [dict(link_type="DocType", link_to="Sales Order", label=status,
                     custom_card_show_count=1,
                     custom_card_count_color="Red" if status == "Draft" else "Green",
                     custom_card_filters=json.dumps([["Sales Order", "status", "=", status]]))
                for status in ["Draft", "Completed"]]
        config = [dict(label="Orders", links=json.dumps(rows), link_count=2)]
        doc.build_links_table_from_card(config)
        doc.insert()
        doc.reload()
        self.assertEqual([r.custom_card_show_count for r in doc.links[1:]], [1, 1])
        self.assertEqual([r.custom_card_count_color for r in doc.links[1:]], ["Red", "Green"])
        self.assertEqual([r.custom_card_filters for r in doc.links[1:]],
                         [r["custom_card_filters"] for r in rows])
        self.assertEqual(doc.get_link_groups()[0]["links"][0]["custom_card_filters"],
                         rows[0]["custom_card_filters"])
        rows[0]["custom_card_filters"] = "[]"
        rows[0]["custom_card_show_count"] = 0
        config[0]["links"] = json.dumps(rows)
        doc.build_links_table_from_card(config)
        doc.save()
        doc.reload()
        self.assertEqual(len(doc.links), 3)
        self.assertEqual([r.custom_card_show_count for r in doc.links[1:]], [0, 1])
        self.assertEqual([r.custom_card_count_color for r in doc.links[1:]], ["Red", "Green"])
        self.assertEqual(doc.links[1].custom_card_filters, "[]")
        self.assertEqual(doc.links[2].custom_card_filters, rows[1]["custom_card_filters"])

    def test_non_doctype_links_do_not_keep_filters(self):
        doc = frappe.new_doc("Workspace")
        doc.build_links_table_from_card([dict(label="Reports", link_count=1, links=json.dumps([
            dict(link_type="Report", link_to="General Ledger", custom_card_filters="[]")
        ]))])
        self.assertIsNone(doc.links[1].custom_card_filters)
