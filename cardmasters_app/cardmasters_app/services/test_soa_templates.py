import unittest
from unittest.mock import patch

import frappe
from jinja2 import TemplateError

from cardmasters_app.cardmasters_app.overrides.scheduled_job_type import (
    CUSTOM_SOA_JOB,
    NATIVE_SOA_JOB,
    CustomScheduledJobType,
)
from cardmasters_app.cardmasters_app.services import soa_templates as soa


class TestSOATemplates(unittest.TestCase):
    def setUp(self):
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")
        frappe.db.savepoint("soa_template_test")

    def tearDown(self):
        frappe.db.rollback(save_point="soa_template_test")
        frappe.set_user(self.previous_user)

    def make_template(self, **values):
        return frappe.get_doc({
            "doctype": "SOA Template", "template_name": frappe.generate_hash(length=12),
            "report_type": "General Ledger", "enabled": 1, "html": "<h1>{{ customer.customer_name }}</h1>",
            **values,
        })

    def test_rejects_invalid_templates_and_disabled_defaults(self):
        for values in ({"html": "{% if %}"}, {"html": "<script>alert(1)</script>"},
                       {"css": "</style><script>bad</script>"}, {"enabled": 0, "is_default": 1}):
            with self.subTest(values=values), self.assertRaises(frappe.ValidationError):
                self.make_template(**values).insert()

    def test_only_one_default_per_report(self):
        first = self.make_template(is_default=1).insert()
        with self.assertRaises(frappe.ValidationError):
            self.make_template(is_default=1).insert()
        self.assertEqual(soa.get_selected_template(None, "General Ledger").name, first.name)

    def test_rejects_disabled_and_wrong_report_selection(self):
        template = self.make_template(enabled=0).insert()
        doc = frappe._dict(custom_soa_template=template.name)
        with self.assertRaises(frappe.ValidationError):
            soa.get_selected_template(doc, "General Ledger")
        template.enabled = 1
        template.save()
        with self.assertRaises(frappe.ValidationError):
            soa.get_selected_template(doc, "Accounts Receivable")

    def test_sandbox_escapes_data_and_excludes_database_access(self):
        env = soa.template_environment()
        self.assertEqual(env.from_string("{{ name }}").render(name="<script>bad</script>"),
                         "&lt;script&gt;bad&lt;/script&gt;")
        with self.assertRaises(TemplateError):
            env.from_string("{{ frappe.db.get_value('User', 'Administrator', 'email') }}").render()
        with self.assertRaises(TemplateError):
            env.from_string("{{ missing_variable }}").render()

    def test_context_restored_after_nested_render_and_failure(self):
        with soa.statement_context("outer", "outer-template"):
            with self.assertRaises(ValueError):
                with soa.statement_context("inner"):
                    self.assertEqual(soa._active_statement.get(), "inner")
                    raise ValueError("render failed")
            self.assertEqual(soa._active_statement.get(), "outer")
            self.assertEqual(soa._active_template.get(), "outer-template")
        self.assertIsNone(soa._active_statement.get())
        self.assertIsNone(soa._active_template.get())

    def test_wrappers_keep_native_generation_and_scope_context(self):
        doc = frappe._dict(name="test", custom_soa_template="layout")
        with patch.object(soa, "load_statement", return_value=doc), patch.object(soa, "get_selected_template", return_value=None), patch.object(soa, "native") as native:
            def download(name):
                self.assertIs(soa._active_statement.get(), doc)
                return "native-result"
            native.return_value.download_statements.side_effect = download
            self.assertEqual(soa.download_statements("test"), "native-result")
            self.assertIsNone(soa._active_statement.get())
            soa.send_emails("test", from_scheduler=True, posting_date="2026-10-05")
            native.return_value.send_emails.assert_called_once_with(
                "test", from_scheduler=True, posting_date="2026-10-05")

    def test_ar_totals_exclude_native_subtotal_rows(self):
        fake_customer = frappe._dict(as_dict=lambda: frappe._dict(customer_name="Sample"))
        fake_company = frappe._dict(as_dict=lambda: frappe._dict(company_name="Company"))
        data = [frappe._dict(voucher_type="Payment Entry", voucher_no="PE-1", invoiced=100,
                            paid=20, credit_note=10, outstanding=70),
                frappe._dict(invoiced=100, paid=20, credit_note=10, outstanding=70), {}]
        with patch("frappe.get_doc", side_effect=[fake_customer, fake_company]), patch(
            "erpnext.accounts.party.get_party_account_currency", return_value="PHP"
        ):
            context = soa.build_context(None, frappe._dict(party=["C"], company="Company"), data,
                                        {"report_name": "Accounts Receivable"}, None, None, None)
        self.assertEqual(context["totals"].outstanding, 70)
        self.assertEqual(len(context["transactions"]), 1)

    def test_preview_rejects_customer_outside_saved_statement(self):
        doc = frappe._dict(customers=[frappe._dict(customer="allowed")], report="General Ledger")
        with patch.object(soa, "load_statement", return_value=doc):
            with self.assertRaises(frappe.ValidationError):
                soa.preview("statement", customer="unrelated")

    def test_scheduler_routes_only_native_soa_job_and_restores_method(self):
        job = CustomScheduledJobType({"doctype": "Scheduled Job Type", "method": NATIVE_SOA_JOB})
        seen = []
        def execute(instance):
            seen.append(instance.method)
        with patch("frappe.core.doctype.scheduled_job_type.scheduled_job_type.ScheduledJobType.execute", execute):
            job.execute()
            job.method = "other.job"
            job.execute()
        self.assertEqual(seen, [CUSTOM_SOA_JOB, "other.job"])
        self.assertEqual(job.method, "other.job")
        job.method = NATIVE_SOA_JOB
        with patch("frappe.core.doctype.scheduled_job_type.scheduled_job_type.ScheduledJobType.execute", side_effect=ValueError):
            with self.assertRaises(ValueError):
                job.execute()
        self.assertEqual(job.method, NATIVE_SOA_JOB)

    def test_native_reports_pdf_and_email_attachment_use_selected_templates(self):
        """Exercise real report rows with rollback-only statement/template records."""
        from pathlib import Path
        from shutil import which

        candidates = frappe.get_all("Sales Invoice", filters={"docstatus": 1, "outstanding_amount": [">", 0]},
                                    fields=["company", "customer", "posting_date"],
                                    order_by="posting_date desc", limit=1)
        if not candidates:
            self.skipTest("No submitted invoice with an outstanding balance is available")
        invoice = candidates[0]
        directory = Path(frappe.get_app_path("cardmasters_app", "templates", "soa"))
        for report_type in soa.REPORT_TYPES:
            with self.subTest(report_type=report_type):
                template = self.make_template(report_type=report_type,
                    html=(directory / "starter.html").read_text() + "<p>SELECTED-SOA-LAYOUT</p>",
                    css=(directory / "starter.css").read_text()).insert()
                doc = frappe.new_doc(soa.STATEMENT_DOCTYPE)
                doc.company = invoice.company
                doc.report = report_type
                doc.from_date = invoice.posting_date
                doc.to_date = invoice.posting_date
                doc.posting_date = invoice.posting_date
                doc.orientation = "Landscape"
                doc.include_ageing = 1
                doc.custom_soa_template = template.name
                doc.append("customers", {"customer": invoice.customer,
                    "customer_name": frappe.db.get_value("Customer", invoice.customer, "customer_name"),
                    "billing_email": "soa-test@example.invalid"})
                doc.insert(set_name="SOA test " + frappe.generate_hash(length=12))
                rows_before = soa.native().get_statement_dict(doc, get_statement_dict=True)
                html = soa.preview(doc.name)
                self.assertIn("SELECTED-SOA-LAYOUT", html)
                self.assertIn("Statement of Accounts", html)
                self.assertEqual(rows_before, soa.native().get_statement_dict(doc, get_statement_dict=True))
                edited = soa.preview(doc.name, template_document=frappe.as_json({
                    "name": template.name, "report_type": report_type,
                    "html": "<p>UNSAVED-PREVIEW {{ customer.customer_name }}</p>", "css": "p { color: red; }",
                }))
                self.assertIn("UNSAVED-PREVIEW", edited)
                self.assertNotIn("UNSAVED-PREVIEW", frappe.db.get_value("SOA Template", template.name, "html"))
                # A configured default also works for direct native callers; no selection
                # and no default retain the native layout.
                doc.custom_soa_template = None
                doc.save()
                native_html = soa.preview(doc.name)
                self.assertNotIn("SELECTED-SOA-LAYOUT", native_html)
                template.is_default = 1
                template.save()
                direct_html = soa.native().get_statement_dict(doc)[invoice.customer]
                self.assertIn("SELECTED-SOA-LAYOUT", direct_html)
                template.is_default = 0
                template.save()
                doc.custom_soa_template = template.name
                doc.save()
                if which("wkhtmltopdf"):
                    with soa.statement_context(doc):
                        pdf = soa.native().get_report_pdf(doc)
                    self.assertTrue(pdf.startswith(b"%PDF"))
                    # Intercept the queue boundary: no test emails can be delivered.
                    with patch("frappe.enqueue") as enqueue:
                        self.assertTrue(soa.send_emails(doc.name))
                    self.assertTrue(enqueue.called)
                    attachments = enqueue.call_args.kwargs["attachments"]
                    self.assertTrue(attachments[0]["fcontent"].startswith(b"%PDF"))
