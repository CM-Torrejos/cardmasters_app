# Editable statement of accounts templates

Search **SOA Template** in Desk. Two starter records are installed: **CardMasters General Ledger** and **CardMasters Accounts Receivable**. Accounts Managers and System Managers can edit their HTML/Jinja and CSS; Accounts Users can select and read templates.

On **Process Statement Of Accounts**, choose a matching **SOA Template**, save, and use **Preview Template**, **Download**, or **Send Emails**. The editor's **Preview** button can render unsaved layout edits against a saved statement. Select an included customer, or leave the customer blank to use its first customer. HTML previews run in a sandboxed iframe; PDF previews use the native PDF engine. Preview never sends mail.

A template can be marked **Default for This Report**. Only one enabled default is allowed per report. Blank selections use that default or the original ERPNext layout when no default is configured. Starter records are not defaults, so installation leaves existing statements on the native layout. Setup preserves edits to starter records on subsequent migrations.

## Available variables

| Variable | Contents |
| --- | --- |
| `doc` | Statement settings as a data dictionary |
| `customer`, `company` | Customer and company data dictionaries |
| `filters`, `report` | Native report filters and column metadata |
| `data` | All native report rows, including opening/total/closing rows |
| `transactions` | Native rows with a voucher number, excluding summary rows |
| `totals` | GL: opening_balance, debit, credit, balance. AR: invoiced, paid, credit_note, outstanding |
| `currency` | Currency of the report amounts |
| `invoices` | Sales Invoice metadata keyed by invoice number: posting_date, due_date, po_no, po_date, currency, grand_total |
| `ageing` | Native ageing result, or None |
| `letter_head` | Selected native letterhead, or None |
| `terms_and_conditions` | Selected terms HTML, or None |

Use `frappe.format(value, 'Date')`, `frappe.utils.fmt_money(value, currency=currency)`, `frappe.utils.formatdate`, and `frappe.utils.flt` to format values. Jinja loops, conditions, and standard filters are available. HTML data is escaped automatically; use `|safe` for trusted letterhead/terms HTML. Optional row fields should use `row.get('field')`. CSS is literal CSS without Jinja. Script tags, malformed Jinja, disabled defaults, and mismatched report selections are rejected. Preview also catches missing variables and rendering errors before use.

The layout sandbox exposes formatting helpers and plain data only; database APIs and document mutation methods are not available. A template changes presentation, not report calculations. Amounts and outstanding balances come from native reports at the selected dates; invoice metadata is supplementary and current.

## Integration and deployment

All files belong to `cardmasters_app`; no ERPNext or Frappe core files are edited. The `process_soa_html` hook routes both native statement layouts through a dispatcher. Thin whitelisted endpoint adapters provide scoped statement context while delegating downloads and email delivery to ERPNext. A `Scheduled Job Type` controller override routes only ERPNext's existing SOA daily callback through the same adapter; all other jobs delegate unchanged. This keeps the native schedule and job logging without adding a duplicate scheduled sender.

Deploy with the normal app release, `bench --site <site> migrate`, asset setup/build as required by the deployment, and worker/web restart. Migration installs the DocType, custom field fixture, and starter records; fresh installation also runs the idempotent setup. Review this integration after an ERPNext upgrade, especially if native SOA function signatures or its rendering context change. Other apps overriding the same endpoint, SOA hook, or Scheduled Job Type controller need compatibility review.

For direct Python callers that need an explicit selection, enter `statement_context(doc)` before calling the native `get_report_pdf`/`get_statement_dict`. The Desk endpoints and scheduled sender do this automatically. Raw native calls outside that context can use the configured default, but do not receive a statement-specific selection.

Tests: `cardmasters_app.cardmasters_app.services.test_soa_templates`. The real-data integration check uses rollback-only statement and template records; email enqueue is intercepted. Native PDF checks require `wkhtmltopdf` and a reachable local web server for print assets. Native letterheads, terms, orientation, and report filtering remain available.

## CSV and Excel exports

Save a **Process Statement Of Accounts**, then choose **Export → CSV** or **Export → Excel**. Leave the customer blank for all customers on the statement, or select one included customer. Both General Ledger and Accounts Receivable are supported. The download uses the saved dates and report filters.

CSV contains one combined UTF-8 table with customer identifiers on every row. Excel (.xlsx) contains one sheet per customer, with numeric monetary values, real dates, frozen column headings, and filters. References and PO numbers remain text so leading zeroes are preserved. The export includes invoice PO/due-date metadata, native transaction rows, native balance/total rows, and ageing when enabled. The **Row Type** column distinguishes transactions, summaries, and ageing summaries; filter to **Transaction** when calculating transaction-only sums. Ageing summary rows identify the currency used by the native ageing report, which can differ from a General Ledger presentation currency.

These are structured data exports. HTML/CSS, branding, and terms remain part of the PDF layout. Export generation does not render or depend on the selected HTML template. Statement read/export permission and customer read permission are required. Exports do not send emails or create stored attachments. Tests are in `cardmasters_app.cardmasters_app.services.test_soa_exports`.
