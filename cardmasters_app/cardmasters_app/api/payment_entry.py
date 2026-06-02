import frappe

@frappe.whitelist()
def reverse_payment_entry(payment_entry_name, reversal_date):
    from cardmasters_app.cardmasters_app.services.payment_entry import reverse_payment_entry as reverse_pe
    return reverse_pe(payment_entry_name, reversal_date)
