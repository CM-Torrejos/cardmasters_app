import frappe
from frappe import _

def validate_revolving_fund_invoice(doc, method):
    if (doc.custom_from_revolving_fund == 1
    and any(
        line.purchase_order != doc.items[0].purchase_order
        for line in doc.items[1:]
    )):
    frappe.throw(
        "Found multiple purchase orders linked. "
        "Please follow one invoice per purchase order "
        "(for revolving fund transactions)"
    )
