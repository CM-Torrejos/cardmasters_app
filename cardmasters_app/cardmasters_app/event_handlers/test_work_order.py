from unittest import TestCase
from unittest.mock import Mock

import frappe

from cardmasters_app.cardmasters_app.event_handlers.work_order import (
    start_production_from_operation_progress,
    revert_production_to_not_started,
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

    def test_resetting_last_operation_reverts_production(self):
        for progress in ("In Progress", "Done", "On Hold"):
            with self.subTest(progress=progress):
                doc = self.make_doc(
                    ["Not Started", "Not Started"],
                    previous=["Not Started", progress], state="In Production",
                )
                revert_production_to_not_started(doc)
                self.assertEqual(doc.workflow_state, "Not Started")

    def test_every_operation_must_be_explicitly_not_started(self):
        for progress in ("In Progress", "Done", "On Hold", None, "", " Not Started "):
            with self.subTest(progress=progress):
                doc = self.make_doc(
                    ["Not Started", progress],
                    previous=["In Progress", progress], state="In Production",
                )
                revert_production_to_not_started(doc)
                self.assertEqual(doc.workflow_state, "In Production")

    def test_unrelated_save_does_not_revert_manually_started_work_order(self):
        doc = self.make_doc(["Not Started"], state="In Production")
        revert_production_to_not_started(doc)
        self.assertEqual(doc.workflow_state, "In Production")

    def test_empty_or_missing_operations_do_not_revert(self):
        for operations in ([], None):
            with self.subTest(operations=operations):
                doc = self.make_doc([], state="In Production")
                doc.operations = operations
                revert_production_to_not_started(doc)
                self.assertEqual(doc.workflow_state, "In Production")

    def test_missing_previous_document_does_not_revert(self):
        doc = self.make_doc(["Not Started"], state="In Production")
        doc.get_doc_before_save.return_value = None
        revert_production_to_not_started(doc)
        self.assertEqual(doc.workflow_state, "In Production")

    def test_new_operation_alone_does_not_count_as_a_reset(self):
        doc = self.make_doc(["Not Started"], previous=[], state="In Production")
        revert_production_to_not_started(doc)
        self.assertEqual(doc.workflow_state, "In Production")

    def test_reset_preserves_other_workflow_states(self):
        for state in ("Draft", "Not Started", "Pending Consumption", "Pending Claiming", "In Claiming", "Cancelled"):
            with self.subTest(state=state):
                doc = self.make_doc(["Not Started"], previous=["In Progress"], state=state)
                revert_production_to_not_started(doc)
                self.assertEqual(doc.workflow_state, state)

    def test_reset_preserves_draft_and_cancelled_documents(self):
        for docstatus in (0, 2):
            with self.subTest(docstatus=docstatus):
                doc = self.make_doc(
                    ["Not Started"], previous=["In Progress"],
                    state="In Production", docstatus=docstatus,
                )
                revert_production_to_not_started(doc)
                self.assertEqual(doc.workflow_state, "In Production")

    def test_hooks_together_follow_operation_progress_in_both_directions(self):
        for current, previous, state, expected in (
            (["In Progress"], ["Not Started"], "Not Started", "In Production"),
            (["Not Started"], ["In Progress"], "In Production", "Not Started"),
        ):
            with self.subTest(expected=expected):
                doc = self.make_doc(current, previous=previous, state=state)
                start_production_from_operation_progress(doc)
                revert_production_to_not_started(doc)
                self.assertEqual(doc.workflow_state, expected)
