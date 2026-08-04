import frappe
from frappe import _


@frappe.whitelist()
def get_sales_order_payment_counts(customer: str) -> dict[str, int]:
    """Return submitted Sales Order payment-state counts visible to the user."""
    if not customer or not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer is required"))

    sales_orders = frappe.get_list(
        "Sales Order",
        filters={"customer": customer, "docstatus": 1},
        fields=["grand_total", "custom_outstanding_balance"],
        limit_page_length=0,
    )

    partly_paid = 0
    fully_unpaid = 0

    for sales_order in sales_orders:
        outstanding_balance = sales_order.custom_outstanding_balance or 0
        grand_total = sales_order.grand_total or 0

        if 0 < outstanding_balance < grand_total:
            partly_paid += 1
        elif outstanding_balance == grand_total:
            fully_unpaid += 1

    return {
        "partly_paid": partly_paid,
        "fully_unpaid": fully_unpaid,
    }
