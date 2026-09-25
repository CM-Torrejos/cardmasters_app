from unittest import TestCase
from unittest.mock import Mock

import frappe

from cardmasters_app.cardmasters_app.event_handlers.work_order import (
    start_production_from_operation_progress,
)


class TestOperationProductionTransition(TestCase):
    def make_doc(self, current, previous=None, state="Not Started", docstatus=1):
        def rows(values):
            return [
                frappe._dict(name=f"operation-{index}", custom_progress=value)
                for index, value in enumerate(values)
            ]

        doc = frappe._dict(
            docstatus=docstatus, workflow_state=state, operations=rows(current)
        )
        doc.get_doc_before_save = Mock(return_value=frappe._dict(
            operations=rows(previous if previous is not None else ["Not Started"] * len(current))
        ))
        return doc

    def test_one_started_or_done_operation_starts_production(self):
        for progress in ("In Progress", "Done"):
            with self.subTest(progress=progress):
                doc = self.make_doc(["Not Started", "On Hold", progress])
                start_production_from_operation_progress(doc)
                self.assertEqual(doc.workflow_state, "In Production")

    def test_unstarted_held_blank_and_missing_operations_do_not_start(self):
        for values in ([], ["Not Started"], ["On Hold"], [None, "", "On Hold"]):
            with self.subTest(values=values):
                doc = self.make_doc(values)
                start_production_from_operation_progress(doc)
                self.assertEqual(doc.workflow_state, "Not Started")

    def test_resuming_held_operation_starts_production(self):
        doc = self.make_doc(["In Progress"], previous=["On Hold"])
        start_production_from_operation_progress(doc)
        self.assertEqual(doc.workflow_state, "In Production")

    def test_unrelated_save_does_not_restart_reverted_work_order(self):
        doc = self.make_doc(["In Progress", "On Hold"], previous=["In Progress", "Not Started"])
        start_production_from_operation_progress(doc)
        self.assertEqual(doc.workflow_state, "Not Started")

    def test_other_workflow_states_are_preserved(self):
        for state in ("Draft", "In Production", "Pending Consumption", "Pending Claiming", "In Claiming", "Cancelled"):
            with self.subTest(state=state):
                doc = self.make_doc(["Done"], state=state)
                start_production_from_operation_progress(doc)
                self.assertEqual(doc.workflow_state, state)

    def test_draft_and_cancelled_documents_are_preserved(self):
        for docstatus in (0, 2):
            with self.subTest(docstatus=docstatus):
                doc = self.make_doc(["In Progress"], docstatus=docstatus)
                start_production_from_operation_progress(doc)
                self.assertEqual(doc.workflow_state, "Not Started")
