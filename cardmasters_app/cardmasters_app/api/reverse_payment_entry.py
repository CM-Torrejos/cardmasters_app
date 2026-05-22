import frappe
from frappe import _
import erpnext
from erpnext.accounts.utils import reconcile_against_document

@frappe.whitelist()
def reverse_payment_entry(payment_entry_name, reversal_date):
	# 1. Server-Side Security Validation
	if not frappe.has_permission("Payment Entry", "cancel"):
		# OR frappe.only_for("Accounts Manager")
		frappe.throw(_("Not authorized to reverse Payment Entries."))

	# 2. Fetch the document for initial validations
	pe = frappe.get_doc("Payment Entry", payment_entry_name)
	
	# ==========================================
	# NEW: Idempotency Check
	# ==========================================
	if pe.custom_is_reversed:
		frappe.throw(_("This Payment Entry has already been reversed by Journal Entry: {0}").format(pe.custom_reversal_journal_entry))

	if pe.docstatus != 1:
		frappe.throw(_("Only submitted Payment Entries can be reversed."))

	# 3. Hard Stop Validations
	if pe.clearance_date:
		frappe.throw(_("This payment has already cleared the bank. Reversing it will impact your bank reconciliation. Please consult the Accounts Manager."))

	for ref in pe.references:
		if ref.reference_doctype in ["Purchase Invoice", "Sales Invoice", "Purchase Order", "Sales Order"]:
			frappe.throw(_("This Payment Entry is allocated to one or more documents. Please review manually or unlink before reversing."))

	# 4. Data Mapping via GL Entries (Single-Currency)
	gl_entries = frappe.get_all("GL Entry",
		filters={"voucher_type": "Payment Entry", "voucher_no": pe.name, "is_cancelled": 0},
		fields=["account", "party_type", "party", "cost_center", "project", "debit", "credit"]
	)

	if not gl_entries:
		frappe.throw(_("No GL Entries found for this Payment Entry. Reversal blocked."))

	# 5. Generate the Journal Entry FIRST
	je = frappe.new_doc("Journal Entry")
	je.posting_date = reversal_date
	je.company = pe.company
	je.voucher_type = "Journal Entry"
	je.user_remark = f"Automated Out-of-Period Reversal for {pe.name}"

	for gl in gl_entries:
		je.append("accounts", {
			"account": gl.account,
			"party_type": gl.party_type,
			"party": gl.party,
			"cost_center": gl.cost_center,
			"project": gl.project,
			"debit_in_account_currency": gl.credit,
			"credit_in_account_currency": gl.debit
		})

	# Save and Submit the Journal Entry 
	# (Note: ignore_permissions flag removed to enforce proper role rights)
	je.insert()
	je.submit()

	# 6. Automate the Payment Reconciliation
	if pe.party_type and pe.party:
		je_party_row = next((row for row in je.accounts if row.party == pe.party and row.party_type == pe.party_type), None)

		if je_party_row:
			account_type = erpnext.get_party_account_type(pe.party_type)
			dr_or_cr = "credit_in_account_currency" if account_type == "Receivable" else "debit_in_account_currency"
			
			allocated_amount = je_party_row.credit_in_account_currency or je_party_row.debit_in_account_currency

			entry_list = [frappe._dict({
				"voucher_type": "Payment Entry",
				"voucher_no": pe.name,
				"against_voucher_type": "Journal Entry",
				"against_voucher": je.name,
				"account": je_party_row.account,
				"party_type": pe.party_type,
				"party": pe.party,
				"dr_or_cr": dr_or_cr,
				"unadjusted_amount": allocated_amount,
				"allocated_amount": allocated_amount,
			})]

			reconcile_against_document(entry_list)

	# ==========================================
	# NEW: Update State Management directly in DB
	# ==========================================
	frappe.db.set_value('Payment Entry', pe.name, {
		'custom_is_reversed': 1,
		'custom_reversal_journal_entry': je.name
	})

	# 7. Post an audit trail comment
	if hasattr(frappe.local, 'docs') and payment_entry_name in frappe.local.docs:
		del frappe.local.docs[payment_entry_name]
		
	fresh_pe = frappe.get_doc("Payment Entry", payment_entry_name)
	fresh_pe.add_comment("Comment", f"Automated Out-of-Period Reversal executed on {reversal_date}. Reversing balances successfully reconciled to {je.name}.")

	return je.name

def clear_reversal_on_unreconcile_tool(doc, method):
    if doc.voucher_type == "Payment Entry":
        pe_name = doc.voucher_no
        reversal_je = frappe.db.get_value("Payment Entry", pe_name, "custom_reversal_journal_entry")
        
        if reversal_je:
            for row in doc.allocations:
                if row.reference_doctype == "Journal Entry" and row.reference_name == reversal_je:
                    
                    frappe.db.set_value("Payment Entry", pe_name, {
                        "custom_is_reversed": 0,
                        "custom_reversal_journal_entry": None
                    })
                    
                    pe = frappe.get_doc("Payment Entry", pe_name)
                    pe.add_comment("Comment", f"Automated Out-of-Period Reversal link cleared due to Unreconciliation ({doc.name}).")
                    
                    # NEW: Push a real-time event to the frontend
                    frappe.publish_realtime("reversal_cleared", {"docname": pe_name}, user=frappe.session.user)
                    break

def clear_reversal_on_je_cancel(doc, method):
    pe_name = frappe.db.get_value("Payment Entry", {"custom_reversal_journal_entry": doc.name}, "name")
    
    if pe_name:
        frappe.db.set_value("Payment Entry", pe_name, {
            "custom_is_reversed": 0,
            "custom_reversal_journal_entry": None
        })
        
        pe = frappe.get_doc("Payment Entry", pe_name)
        pe.add_comment("Comment", "Automated Out-of-Period Reversal link cleared because the Reversal Journal Entry was cancelled.")
        
        # NEW: Push a real-time event to the frontend
        frappe.publish_realtime("reversal_cleared", {"docname": pe_name}, user=frappe.session.user)