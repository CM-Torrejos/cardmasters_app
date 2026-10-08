"""Sales Order item statements using dated payment allocations, not invoice rows."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import re

import frappe
from frappe import _
from frappe.utils import getdate, today

CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def allocate(total, weights):
    """Distribute currency cents proportionally; the last row takes the rounding remainder."""
    total = money(total)
    weights = [Decimal(str(value or 0)) for value in weights]
    weight_total = sum(weights)
    if not weights:
        return []
    if weight_total <= 0 or any(value < 0 for value in weights):
        frappe.throw(_("Sales Order items must have non-negative amounts and a positive total."))
    return apportion(total, weights)


def apportion(total, weights):
    """Largest-remainder currency allocation, including signed invoice adjustments."""
    from decimal import ROUND_FLOOR
    weights = [Decimal(str(value or 0)) for value in weights]
    denominator = sum(weights)
    if not denominator:
        frappe.throw(_("Cannot allocate an amount across a zero item total."))
    cents = money(total) / CENT
    exact = [cents * value / denominator for value in weights]
    floors = [value.to_integral_value(rounding=ROUND_FLOOR) for value in exact]
    remainder = int(cents - sum(floors))
    priority = sorted(range(len(weights)), key=lambda i: (exact[i] - floors[i], -i), reverse=True)
    for index in priority[:remainder]:
        floors[index] += 1
    return [value * CENT for value in floors]


def paid_as_of(order_names, invoices, invoice_items, ledger, direct, advances):
    """Attribute shared invoice settlements once, and remove transferred-advance overlap.

    Inputs are already restricted to the selected customer/company and cutoff date.
    Invoice rows can include future invoices: payments posted before an invoice are
    still advances at the cutoff. Return credit is counted either as unapplied credit
    on the return or as settlement on the original invoice, never both.
    """
    shares = defaultdict(lambda: defaultdict(Decimal))
    totals = defaultdict(Decimal)
    for item in invoice_items:
        weight = Decimal(str(item.get("base_net_amount") if item.get("base_net_amount") is not None else item.get("base_amount") or 0))
        totals[item.parent] += weight
        shares[item.parent][item.get("sales_order") or None] += weight
    invoice_outstanding = defaultdict(Decimal)
    ledger_invoices = set()
    source_credits = defaultdict(lambda: defaultdict(Decimal))
    for row in ledger:
        ledger_invoices.add(row.against_voucher_no)
        invoice_outstanding[row.against_voucher_no] += Decimal(str(row.amount or 0))
        source_credits[row.against_voucher_no][(row.voucher_type, row.voucher_no)] -= Decimal(str(row.amount or 0))
    direct_by_order = defaultdict(lambda: defaultdict(Decimal))
    for row in direct:
        direct_by_order[row.sales_order][(row.voucher_type, row.voucher_no)] += Decimal(str(row.amount or 0))
    payments = {name: sum(direct_by_order[name].values()) for name in order_names}
    overlap_by_order = defaultdict(lambda: defaultdict(Decimal))
    for invoice in invoices:
        if invoice.get("posted_total") and invoice.name not in ledger_invoices:
            frappe.throw(_("Invoice {0} has no dated payment ledger entries. Repair its ledger before generating this statement.").format(invoice.name))
        denominator = totals[invoice.name]
        if not denominator:
            if any(shares[invoice.name].values()) or invoice.get("posted_total") or invoice_outstanding[invoice.name]:
                frappe.throw(_("Cannot allocate invoice {0}: its item total is zero.").format(invoice.name))
            continue
        outstanding = invoice_outstanding[invoice.name]
        settlement = (-min(outstanding, Decimal(0))) if invoice.is_return else (
            Decimal(str(invoice.get("posted_total") or 0)) - outstanding)
        order_keys = list(shares[invoice.name])
        weights = list(shares[invoice.name].values())
        settlements = apportion(settlement, weights)
        transfers = defaultdict(Decimal)
        for advance in advances.get(invoice.name, []):
            transfers[(advance.reference_type, advance.reference_name)] += Decimal(str(advance.allocated_amount or 0))
        transferred_allocations = {
            source: apportion(min(amount, max(Decimal(0), source_credits[invoice.name][source])), weights)
            for source, amount in transfers.items()
        }
        for index, order in enumerate(order_keys):
            if order not in order_names:
                continue
            payments[order] += settlements[index]
            for source, allocated in transferred_allocations.items():
                overlap_by_order[order][source] += allocated[index]
    for order in order_names:
        for source, transferred in overlap_by_order[order].items():
            payments[order] -= min(max(Decimal(0), direct_by_order[order][source]), transferred)
        payments[order] = money(payments[order])
    return payments


def linked_data(order_names, company, customer, cutoff):
    names = list(order_names)
    links = frappe.get_all("Sales Invoice Item", filters={"sales_order": ["in", names], "docstatus": 1},
                           fields=["parent", "sales_order", "so_detail"])
    invoice_names = list({row.parent for row in links})
    invoices, invoice_items, ledger = [], [], []
    advances = defaultdict(list)
    if invoice_names:
        invoices = frappe.get_all("Sales Invoice", filters={
            "name": ["in", invoice_names], "company": company, "customer": customer, "docstatus": 1,
        }, fields=["name", "posting_date", "due_date", "is_return", "base_grand_total", "base_rounded_total",
                   "disable_rounded_total", "custom_bir_series", "custom_dr_billing_reference"])
        for invoice in invoices:
            frappe.get_doc("Sales Invoice", invoice.name).check_permission("read")
            total = invoice.base_grand_total if invoice.disable_rounded_total else (invoice.base_rounded_total or invoice.base_grand_total)
            invoice.posted_total = total if getdate(invoice.posting_date) <= cutoff else 0
        invoice_names = [row.name for row in invoices]
        if invoice_names:
            invoice_items = frappe.get_all("Sales Invoice Item", filters={"parent": ["in", invoice_names], "docstatus": 1},
                fields=["parent", "sales_order", "so_detail", "base_net_amount", "base_amount"])
            ledger = frappe.get_all("Payment Ledger Entry", filters={
                "company": company, "party_type": "Customer", "party": customer, "delinked": 0,
                "against_voucher_type": "Sales Invoice", "against_voucher_no": ["in", invoice_names],
                "posting_date": ["<=", cutoff],
            }, fields=["against_voucher_no", "voucher_type", "voucher_no", "amount"])
            for row in frappe.get_all("Sales Invoice Advance", filters={"parent": ["in", invoice_names], "docstatus": 1},
                fields=["parent", "reference_type", "reference_name", "allocated_amount"]):
                advances[row.parent].append(row)
    direct = frappe.db.sql("""
        select r.reference_name as sales_order, 'Payment Entry' as voucher_type,
            p.name as voucher_no,
            (case when p.payment_type='Receive' then r.allocated_amount else -r.allocated_amount end) as amount
        from `tabPayment Entry Reference` r join `tabPayment Entry` p on p.name=r.parent
        where p.docstatus=1 and r.docstatus=1 and p.company=%s and p.party_type='Customer' and p.party=%s
            and p.posting_date<=%s and r.reference_doctype='Sales Order' and r.reference_name in %s
        union all
        select r.reference_name, 'Journal Entry', j.name, r.credit-r.debit
        from `tabJournal Entry Account` r join `tabJournal Entry` j on j.name=r.parent
        where j.docstatus=1 and r.docstatus=1 and j.company=%s and r.party_type='Customer' and r.party=%s
            and j.posting_date<=%s and r.reference_type='Sales Order' and r.reference_name in %s
    """, (company, customer, cutoff, names, company, customer, cutoff, names), as_dict=True)
    return invoices, invoice_items, ledger, direct, advances


def plain_description(item):
    from frappe.utils import strip_html

    details = " ".join(filter(None, [item.get("item_name") or item.get("item_code"),
                                      item.get("custom_item_specifics"), item.get("custom_particulars")]))
    details = re.sub(r"\s+", " ", strip_html(details)).strip()
    return f"{item.qty:g} {item.uom} {details}"


def item_due_date(schedule, paid, invoice_due):
    cumulative = Decimal(0)
    for term in sorted(schedule, key=lambda row: getdate(row.due_date)):
        cumulative += Decimal(str(term.payment_amount or 0))
        if cumulative > paid and term.due_date:
            return getdate(term.due_date)
    return min(invoice_due) if invoice_due else None


def collect_statement(doc, customer, template):
    from erpnext import get_company_currency

    cutoff = getdate(doc.posting_date or today())
    customer_doc = frappe.get_doc("Customer", customer)
    customer_doc.check_permission("read")
    company_doc = frappe.get_doc("Company", doc.company)
    company_doc.check_permission("read")
    if doc.account or doc.finance_book or doc.payment_terms_template or doc.sales_partner or doc.sales_person or doc.territory or doc.project:
        frappe.throw(_("Sales Order statements use company, customer, statement date, currency and cost center filters. Clear the invoice/account filters first."))
    company_currency = get_company_currency(doc.company)
    if doc.currency and doc.currency != company_currency:
        frappe.throw(_("Sales Order statements currently require the company currency."))
    orders = frappe.get_list("Sales Order", filters={
        "company": doc.company, "customer": customer, "docstatus": 1, "transaction_date": ["<=", cutoff],
    }, fields=["name", "transaction_date", "currency", "grand_total", "rounded_total", "disable_rounded_total"],
       order_by="transaction_date asc, name asc", limit_page_length=0)
    if not orders:
        return None
    if any(order.currency != company_currency for order in orders):
        frappe.throw(_("This customer has foreign-currency Sales Orders. The Sales Order statement currently supports company-currency orders only."))
    order_names = {row.name for row in orders}
    items = frappe.get_all("Sales Order Item", filters={"parent": ["in", list(order_names)], "docstatus": 1},
        fields=["name", "parent", "idx", "item_code", "item_name", "qty", "uom", "net_amount", "amount",
                "custom_item_specifics", "custom_particulars", "cost_center"], order_by="parent asc, idx asc")
    schedules = frappe.get_all("Payment Schedule", filters={"parenttype": "Sales Order", "parent": ["in", list(order_names)], "docstatus": 1},
                              fields=["parent", "due_date", "payment_amount"])
    po_numbers = dict(frappe.get_all("Sales Order", filters={"name": ["in", list(order_names)]}, fields=["name", "po_no"], as_list=True))
    invoice_data = linked_data(order_names, doc.company, customer, cutoff)
    invoices, invoice_items, ledger, direct, advances = invoice_data
    paid = paid_as_of(order_names, *invoice_data)
    by_order, terms = defaultdict(list), defaultdict(list)
    by_item_invoice = defaultdict(list)
    invoice_map = {row.name: row for row in invoices if getdate(row.posting_date) <= cutoff and not row.is_return}
    for item in items:
        by_order[item.parent].append(item)
    for term in schedules:
        if term.due_date:
            terms[term.parent].append(term)
    for link in invoice_items:
        if link.parent in invoice_map:
            by_item_invoice[link.so_detail].append(invoice_map[link.parent])
    delivery_items = frappe.get_all("Delivery Note Item", filters={"against_sales_order": ["in", list(order_names)], "docstatus": 1},
                                   fields=["parent", "so_detail"])
    delivery_names = list({row.parent for row in delivery_items})
    delivery_map = {}
    if delivery_names:
        delivery_map = {row.name: row for row in frappe.get_all("Delivery Note", filters={
            "name": ["in", delivery_names], "company": doc.company, "customer": customer, "docstatus": 1, "posting_date": ["<=", cutoff],
        }, fields=["name", "custom_reference_no"])}
    by_item_dr = defaultdict(list)
    for link in delivery_items:
        if link.parent in delivery_map:
            by_item_dr[link.so_detail].append(delivery_map[link.parent].custom_reference_no or link.parent)
    rows = []
    cost_centers = {row.cost_center_name for row in doc.cost_center}
    for order in orders:
        total = money(order.grand_total if order.disable_rounded_total else (order.rounded_total or order.grand_total))
        balance = max(Decimal(0), total - paid[order.name])
        if balance <= 0 or not by_order[order.name]:
            continue
        order_items = by_order[order.name]
        weights = [item.net_amount if item.net_amount is not None else item.amount for item in order_items]
        amounts = allocate(total, weights)
        payments = allocate(total - balance, amounts)
        due_dates = [getdate(inv.due_date) for link in invoice_items if link.sales_order == order.name
                     and (inv := invoice_map.get(link.parent)) and inv.due_date]
        due = item_due_date(terms[order.name], paid[order.name], due_dates)
        first = True
        for item, amount, payment in zip(order_items, amounts, payments, strict=True):
            if cost_centers and item.cost_center not in cost_centers:
                continue
            linked_invoices = sorted(by_item_invoice[item.name], key=lambda row: (row.posting_date, row.name))
            rows.append(frappe._dict({
                "customer_name": customer_doc.customer_name, "sales_order": order.name, "so_item": item.name,
                "invoice_date": linked_invoices[0].posting_date if linked_invoices else order.transaction_date,
                "delivery_receipt": ", ".join(dict.fromkeys(by_item_dr[item.name])),
                "csi_invoice": ", ".join(dict.fromkeys(inv.custom_bir_series or inv.name for inv in linked_invoices)),
                "dr_billing_reference": ", ".join(dict.fromkeys(
                    inv.custom_dr_billing_reference for inv in linked_invoices if inv.custom_dr_billing_reference)),
                "bir_series": ", ".join(dict.fromkeys(
                    inv.custom_bir_series for inv in linked_invoices if inv.custom_bir_series)),
                "item_description": plain_description(item), "po_no": po_numbers.get(order.name) or "",
                "due_date": due, "aged": "Past Due" if due and due < cutoff else "Current" if due else "No Due Date",
                "remarks": "UNPAID" if payment <= 0 else "PARTLY PAID", "amount": float(amount),
                "payment": float(payment), "balance": float(amount - payment), "first_in_order": first,
            }))
            first = False
    if not rows:
        return None
    import base64
    from pathlib import Path
    logo = Path(frappe.get_app_path("cardmasters_app", "public", "images", "soa", "reference-logo.png"))
    logo_uri = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode("ascii")
    return frappe._dict({
        "customer": customer_doc.as_dict(), "company": company_doc.as_dict(), "date": cutoff,
        "number": doc.get("custom_soa_statement_number") or doc.name, "currency": company_currency,
        "rows": rows, "totals": frappe._dict({key: float(sum(money(row[key]) for row in rows))
                                               for key in ("amount", "payment", "balance")}),
        "settings": template.as_dict(), "logo_url": logo_uri,
    })
