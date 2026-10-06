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

## Sales Order statement matching the monitoring reference

Select **CardMasters Sales Order SOA** on an **Accounts Receivable** statement. Set the statement date and customers, then save. **Preview Template** and the native **Download** action produce the editable reference-style PDF. **Export → Excel** produces the designed workbook; **Excel (Data Table)** and CSV remain available for analysis. The template is installed locally as an opt-in record, without changing existing defaults.

The new **Data Source** field distinguishes native invoice/GL report templates from Sales Order item templates. The **Excel Layout** selects a separately maintained workbook layout; HTML/CSS changes affect PDF/HTML, not Excel cell formatting. Names, phone/email, payment reminder, bank details, and payee are shared editable template fields used in both outputs. Handwritten signatures are not reproduced. **Statement Number** on the statement is optional; otherwise its document name is displayed.

The Sales Order data source includes submitted orders dated on/before the statement date with a remaining balance at that cutoff. It includes unbilled orders. Amounts are allocated from the order's payable total (including its tax, discount and rounding adjustments) across item net amounts. Payments/credits are allocated proportionally across those item amounts, preserving every cent. Cost center selections restrict the displayed item rows after allocation; totals then describe the displayed rows. Account, finance book, project and invoice-specific filters are not supported in this data source and must be cleared.

Historical payments use dated native Payment Ledger allocations to linked invoices and submitted Payment Entry/Journal Entry references to the order. Shared invoices are apportioned across their complete item set, including items linked to other orders and unlinked items. Advances transferred to invoices are deducted from overlapping direct-order allocations. Applied/unapplied return credit is counted once. Unallocated customer receipts are not assigned arbitrarily to orders. The balance uses currently valid submitted records and the native ledger's posting dates/allocations; it is not an archival snapshot of prior cancellations, amendments or reconciliation versions. It does not use the cached `custom_outstanding_balance` or today's invoice outstanding values.

This first Sales Order layout supports company-currency orders. A customer with foreign-currency orders receives a clear error rather than mixed-currency totals. References come from submitted linked Delivery Notes (`custom_reference_no`, falling back to document name) and Sales Invoices (`custom_bir_series`, falling back to document name), filtered by the statement date and matched to the order item. The date column uses the linked invoice date when available and otherwise the order date. **Aged** uses the first unpaid order payment-term due date, falling back to linked invoice due dates; missing due dates show **No Due Date** instead of guessing a credit period.

The workbook recreates the logo, headings, grouped cells, grey/blue table, numeric totals, payment box, notes and signature lines. It has landscape A4 print settings, repeating headings, and one sheet per customer. Large statements can span pages. Its layout is reconstructed from the supplied PDF; native Excel rendering/font metrics can differ slightly. Reference-data previews are in `migration_artifacts/soa_reference_20261006/`; they are examples, not imported accounting records. Tests: `cardmasters_app.cardmasters_app.services.test_soa_sales_orders`.
