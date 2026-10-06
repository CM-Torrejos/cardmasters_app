"""Desk-managed SOA layouts using native ERPNext report/PDF/email generation."""

import copy
import re
from contextlib import contextmanager
from contextvars import ContextVar

import frappe
from frappe import _
from frappe.utils import flt, formatdate, today
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

NATIVE_MODULE = "erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts"
STATEMENT_DOCTYPE = "Process Statement Of Accounts"
REPORT_TYPES = ("General Ledger", "Accounts Receivable")
_active_statement = ContextVar("cardmasters_soa_statement", default=None)
_active_template = ContextVar("cardmasters_soa_template", default=None)


def native():
    return frappe.get_module(NATIVE_MODULE)


def template_environment():
    """Templates see data and formatters, never document methods or database APIs."""
    from frappe.utils import fmt_money

    env = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)
    env.globals.update({
        "_": _,
        "frappe": frappe._dict({
            "format": frappe.format_value,
            "utils": frappe._dict({"fmt_money": fmt_money, "formatdate": formatdate, "flt": flt}),
        }),
    })
    return env


def validate_template_document(doc):
    if doc.report_type not in REPORT_TYPES:
        frappe.throw(_("Select a supported statement report."))
    if not (doc.html or "").strip():
        frappe.throw(_("HTML template is required."))
    if doc.is_default and not doc.enabled:
        frappe.throw(_("A default template must be enabled."))
    if re.search(r"</?\s*script\b", doc.html, re.I):
        frappe.throw(_("Statement templates cannot contain script tags."))
    if re.search(r"</\s*style\b", doc.css or "", re.I):
        frappe.throw(_("CSS must contain styles only, without closing style tags."))
    try:
        template_environment().from_string(doc.html)
    except TemplateError as exc:
        frappe.throw(_("Invalid HTML template: {0}").format(str(exc)))


def get_selected_template(doc, report_type, check_permission=False):
    name = doc.get("custom_soa_template") if doc else None
    if not name:
        name = frappe.db.get_value("SOA Template", {
            "report_type": report_type, "enabled": 1, "is_default": 1,
        }, "name")
    if not name:
        return None
    template = frappe.get_doc("SOA Template", name)
    if check_permission:
        template.check_permission("read")
    if not template.enabled:
        frappe.throw(_("SOA template {0} is disabled.").format(template.name))
    if template.report_type != report_type:
        frappe.throw(_("SOA template {0} is for {1}, not {2}.").format(
            template.name, template.report_type, report_type))
    return template


def validate_statement(doc, method=None):
    # Validate explicit choices; defaults are checked at generation time as well.
    if doc.get("custom_soa_template"):
        get_selected_template(doc, doc.report, check_permission=True)


@contextmanager
def statement_context(doc, template=None):
    doc_token = _active_statement.set(doc)
    template_token = _active_template.set(template)
    try:
        yield
    finally:
        _active_template.reset(template_token)
        _active_statement.reset(doc_token)


def build_context(doc, filters, data, report, ageing, letter_head, terms_and_conditions):
    from erpnext import get_company_currency
    from erpnext.accounts.party import get_party_account_currency

    customer_name = filters.get("party", [None])[0]
    customer = frappe.get_doc("Customer", customer_name).as_dict()
    company = frappe.get_doc("Company", filters.company).as_dict()
    rows = [frappe._dict(row) for row in data]
    transactions = [row for row in rows if row.get("voucher_no")]
    currency = (
        filters.get("presentation_currency")
        or (next((row.get("currency") for row in transactions if row.get("currency")), None)
            if report["report_name"] == "Accounts Receivable" else None)
        or (get_company_currency(filters.company) if report["report_name"] == "Accounts Receivable" else None)
        or get_party_account_currency("Customer", customer_name, filters.company)
        or get_company_currency(filters.company)
    )
    if report["report_name"] == "General Ledger":
        totals = frappe._dict({
            "opening_balance": flt(rows[0].get("balance")) if rows else 0,
            "debit": sum(flt(row.get("debit")) for row in transactions),
            "credit": sum(flt(row.get("credit")) for row in transactions),
            "balance": flt(rows[-1].get("balance")) if rows else 0,
        })
    else:
        totals = frappe._dict({
            key: sum(flt(row.get(key)) for row in transactions)
            for key in ("invoiced", "paid", "credit_note", "outstanding")
        })
    invoice_names = list({row.voucher_no for row in transactions if row.get("voucher_type") == "Sales Invoice"})
    invoices = {}
    if invoice_names:
        for invoice in frappe.get_all("Sales Invoice", filters={
            "name": ["in", invoice_names], "company": filters.company, "customer": customer_name,
        }, fields=["name", "posting_date", "due_date", "po_no", "po_date", "currency", "grand_total"]):
            invoices[invoice.name] = invoice
    return {
        "doc": doc.as_dict() if doc else frappe._dict({
            "report": report["report_name"], "company": filters.company,
            "from_date": filters.get("from_date"), "to_date": filters.get("to_date"),
            "posting_date": filters.get("report_date"), "ageing_based_on": filters.get("ageing_based_on"),
        }),
        "filters": filters, "data": rows, "transactions": transactions, "report": report,
        "customer": customer, "company": company, "currency": currency, "totals": totals,
        "invoices": invoices, "ageing": ageing, "letter_head": letter_head,
        "terms_and_conditions": terms_and_conditions,
    }


def render_soa_template(filters, data, report, ageing=None, letter_head=None, terms_and_conditions=None):
    """Jinja hook called by the native SOA template dispatcher."""
    doc = _active_statement.get()
    template = _active_template.get() or get_selected_template(doc, report["report_name"])
    if not template:
        suffix = "" if report["report_name"] == "General Ledger" else "_accounts_receivable"
        path = f"erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts{suffix}.html"
        return frappe.render_template(path, {
            "filters": filters, "data": data, "report": report, "ageing": ageing,
            "letter_head": letter_head, "terms_and_conditions": terms_and_conditions,
        }, is_path=True)
    validate_template_document(template)
    context = build_context(doc, filters, data, report, ageing, letter_head, terms_and_conditions)
    try:
        body = template_environment().from_string(template.html).render(context)
    except TemplateError as exc:
        frappe.throw(_("SOA template {0} could not be rendered: {1}").format(template.name, str(exc)))
    # CSS is literal so braces and @media rules need no Jinja escaping.
    return f'<style>{template.css or ""}</style>\n{body}'


def load_statement(document_name):
    doc = frappe.get_doc(STATEMENT_DOCTYPE, document_name)
    doc.check_permission("read")
    get_selected_template(doc, doc.report, check_permission=True)
    return doc


@frappe.whitelist()
def download_statements(document_name):
    doc = load_statement(document_name)
    with statement_context(doc):
        return native().download_statements(document_name)


@frappe.whitelist()
def send_emails(document_name, from_scheduler=False, posting_date=None):
    doc = load_statement(document_name)
    with statement_context(doc):
        return native().send_emails(document_name, from_scheduler=from_scheduler, posting_date=posting_date)


@frappe.whitelist()
def send_auto_email():
    frappe.has_permission(STATEMENT_DOCTYPE, throw=True)
    statements = frappe.get_list(STATEMENT_DOCTYPE, filters={"enable_auto_email": 1},
        or_filters={"to_date": today(), "posting_date": today()})
    for entry in statements:
        send_emails(entry.name, from_scheduler=True)
    return True


@frappe.whitelist()
def preview(document_name, customer=None, template_name=None, template_document=None, as_pdf=False):
    """Render one customer without saving statement/template edits or sending mail."""
    from frappe.utils import cint
    from frappe.utils.pdf import get_pdf

    doc = load_statement(document_name)
    template = None
    if template_document:
        payload = frappe.parse_json(template_document)
        # Only editable layout fields can enter the preview; do not accept flags/permissions.
        if payload.get("name") and frappe.db.exists("SOA Template", payload["name"]):
            template = frappe.get_doc("SOA Template", payload["name"])
            template.check_permission("write")
        else:
            frappe.has_permission("SOA Template", "create", throw=True)
            template = frappe.new_doc("SOA Template")
        for field in ("html", "css", "report_type"):
            template.set(field, payload.get(field))
        template.enabled = 1
        template.is_default = 0
        validate_template_document(template)
    elif template_name:
        template = frappe.get_doc("SOA Template", template_name)
        template.check_permission("read")
        if not template.enabled:
            frappe.throw(_("Select an enabled SOA template."))
    if template and template.report_type != doc.report:
        frappe.throw(_("The template and statement must use the same report type."))
    if not doc.customers:
        frappe.throw(_("Add a customer to the saved statement first."))
    customer = customer or doc.customers[0].customer
    entry = next((row for row in doc.customers if row.customer == customer), None)
    if not entry:
        frappe.throw(_("Select a customer included in this statement."))
    frappe.get_doc("Customer", customer).check_permission("read")
    preview_doc = copy.deepcopy(doc)
    preview_doc.set("customers", [entry.as_dict()])
    with statement_context(preview_doc, template):
        statements = native().get_statement_dict(preview_doc)
    html = statements.get(customer)
    if not html:
        frappe.throw(_("No statement transactions were found for this customer and these filters."))
    if cint(as_pdf):
        frappe.local.response.filename = "SOA Preview.pdf"
        frappe.local.response.filecontent = get_pdf(html, {"orientation": doc.orientation})
        frappe.local.response.type = "download"
        return
    # The native print wrapper includes links without statement document metadata.
    # Preview has its own PDF action; hide the wrapper toolbar in the iframe.
    return html.replace("</head>", "<style>.action-banner { display: none !important; }</style></head>")
