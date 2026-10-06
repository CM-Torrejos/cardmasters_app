"""PDF and email delivery for the Sales Order data source."""

import frappe
from frappe.utils import add_days, add_months, getdate, today
from frappe.utils.pdf import get_pdf

from cardmasters_app.cardmasters_app.services.soa_templates import native, template_environment
from cardmasters_app.cardmasters_app.services.soa_sales_orders import collect_statement

PDF_OPTIONS = {"orientation": "Landscape", "page-size": "A4", "margin-top": "8mm", "margin-bottom": "8mm",
               "margin-left": "10mm", "margin-right": "10mm"}


def collect_statements(doc, template):
    result = {}
    for entry in doc.customers:
        if entry.customer not in result:
            statement = collect_statement(doc, entry.customer, template)
            if statement:
                result[entry.customer] = statement
    return result


def render_statement(doc, template, statement):
    from jinja2 import TemplateError
    from cardmasters_app.cardmasters_app.services.soa_templates import validate_template_document

    validate_template_document(template)
    context = {"doc": doc.as_dict(), "statement": statement, "customer": statement.customer,
               "company": statement.company, "currency": statement.currency,
               "data": statement.rows, "transactions": statement.rows, "totals": statement.totals,
               "settings": statement.settings}
    try:
        body = template_environment().from_string(template.html).render(context)
    except TemplateError as exc:
        frappe.throw(frappe._("SOA template {0} could not be rendered: {1}").format(template.name, str(exc)))
    return '<!doctype html><html><head><meta charset="utf-8"><title>Statement of Account</title><style>' + (
        template.css or "") + '</style></head><body>' + body + '</body></html>'


def get_statement_dict(doc, template):
    return {customer: render_statement(doc, template, statement)
            for customer, statement in collect_statements(doc, template).items()}


def report_pdf(doc, template, consolidated=True):
    statements = get_statement_dict(doc, template)
    if not statements:
        return False
    if consolidated:
        delimiter = '<div style="page-break-before:always"></div>' if doc.include_break else ""
        # Render one document with one stylesheet, rather than concatenate HTML documents.
        from bs4 import BeautifulSoup
        bodies = [str(BeautifulSoup(html, "html.parser").body.decode_contents()) for html in statements.values()]
        html = '<html><head><meta charset="utf-8"><style>' + (template.css or "") + '</style></head><body>' + delimiter.join(bodies) + '</body></html>'
        return get_pdf(html, dict(PDF_OPTIONS))
    return {customer: get_pdf(html, dict(PDF_OPTIONS)) for customer, html in statements.items()}


def send_emails(doc, template, from_scheduler=False, posting_date=None):
    pdfs = report_pdf(doc, template, consolidated=False)
    if not pdfs:
        return False
    for customer, pdf in pdfs.items():
        context = native().get_context(customer, doc)
        recipients, cc = native().get_recipients_and_cc(customer, doc)
        if not recipients:
            continue
        filename = frappe.render_template(doc.pdf_name, context)
        sender = frappe.db.get_value("Email Account", doc.sender, "email_id") if doc.sender else frappe.session.user
        frappe.enqueue(queue="short", method=frappe.sendmail, recipients=recipients, sender=sender, cc=cc,
            subject=frappe.render_template(doc.subject, context), message=frappe.render_template(doc.body, context),
            now=True, reference_doctype=doc.doctype, reference_name=doc.name,
            attachments=[{"fname": filename + ".pdf", "fcontent": pdf}], expose_recipients="header")
    if doc.enable_auto_email and from_scheduler:
        new_date = getdate(posting_date or today())
        if doc.frequency in ("Daily", "Weekly", "Biweekly"):
            new_date = add_days(new_date, {"Daily": 1, "Weekly": 7, "Biweekly": 14}[doc.frequency])
        else:
            new_date = add_months(new_date, 1 if doc.frequency == "Monthly" else 3)
        doc.add_comment("Comment", "Emails sent on: " + frappe.utils.format_datetime(frappe.utils.now()))
        doc.db_set("posting_date", new_date)
    return True
