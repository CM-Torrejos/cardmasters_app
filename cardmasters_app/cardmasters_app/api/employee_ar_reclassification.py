# Copyright (c) 2026, Your Company and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
import csv
from io import StringIO
from frappe.utils import flt, getdate, nowdate

@frappe.whitelist()
def run_employee_ar_reclassification(filters=None):
	if not ("Accounts Manager" in frappe.get_roles() or "System Manager" in frappe.get_roles()):
		frappe.throw("Access Denied: You do not have the required accounting permissions.")

	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	else:
		filters = filters or {}

	execution_logs = []

	employees = frappe.get_all(
		"Employee", 
		filters={"custom_customer_profile": ["!=", ""], "status": "Active"}, 
		fields=["name", "custom_customer_profile"]
	)
	customer_to_employee = {emp.custom_customer_profile: emp.name for emp in employees}

	default_ar_filters = {
		"company": filters.get("company") or frappe.defaults.get_user_default("Company"),
		"report_date": filters.get("report_date") or nowdate(),
		"party_type": "Customer",
		"customer_group": "Employee",
		"range": filters.get("range") or "30, 60, 90, 120"
	}

	report_data = frappe.desk.query_report.run("Accounts Receivable", filters=default_ar_filters)
	raw_columns = report_data.get("columns", [])
	report_rows = report_data.get("result", [])

	if not report_rows:
		return {"status": "empty", "message": "No rows found in the default Accounts Receivable report for Employee Customers."}

	fieldnames = []
	for col in raw_columns:
		if isinstance(col, dict):
			fieldnames.append(col.get("fieldname"))
		elif isinstance(col, str):
			fieldnames.append(col)

	target_accounts = [
		"1451 - ACCOUNTS RECEIVABLE - EMPLOYEE - CM CDO", 
		"1410 - ACCOUNTS RECEIVABLE - TRADE - CM CDO"
	]

	total_rows = len(report_rows)

	for index, raw_row in enumerate(report_rows):
		current_count = index + 1
		
		if isinstance(raw_row, (list, tuple)):
			row = frappe._dict(zip(fieldnames, raw_row))
		elif isinstance(raw_row, dict):
			row = frappe._dict(raw_row)
		else:
			continue

		v_type = row.get("voucher_type")
		v_no = row.get("voucher_no")
		r_account = row.get("account") or row.get("receivable_account")
		party = row.get("party")
		outstanding = flt(row.get("outstanding_amount") or row.get("outstanding"))

		if v_type not in ["Journal Entry", "Sales Invoice"] or not v_no:
			continue

		if not r_account or r_account not in target_accounts:
			if v_type == "Sales Invoice":
				r_account = frappe.db.get_value("Sales Invoice", v_no, "debit_to")
			elif v_type == "Journal Entry":
				r_account = frappe.db.get_value("Journal Entry Account", {"parent": v_no, "party": party}, "account")
			
			if not r_account or r_account not in target_accounts:
				continue

		linked_employee = customer_to_employee.get(party)
		if not linked_employee:
			execution_logs.append({
				"Voucher Type": v_type, "Voucher No": v_no, "Customer": party,
				"Employee ID": "N/A", "Status": "Skipped", 
				"Details": "No active Employee master record linked to this Customer profile."
			})
			continue

		if outstanding == 0:
			continue

		# FIXED: Smarter duplicate check queries child tables to see if this exact customer has been processed for this voucher
		already_done = frappe.db.sql("""
			SELECT je.name FROM `tabJournal Entry` je
			JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
			WHERE je.cheque_no = %s AND jea.party = %s AND je.docstatus in (0, 1)
		""", (v_no, party))

		if already_done:
			execution_logs.append({
				"Voucher Type": v_type, "Voucher No": v_no, "Customer": party,
				"Employee ID": linked_employee, "Status": "Skipped", 
				"Details": "A reclassification Journal Entry matching this reference document and customer already exists."
			})
			continue

		amount_to_move = abs(outstanding)
		is_debit_balance = outstanding > 0

		try:
			# --- REVERSING INTERFACE FOR JOURNAL ENTRIES ---
			if v_type == "Journal Entry":
				je_lines = frappe.get_all(
					"Journal Entry Account",
					filters={"parent": v_no, "party": party, "account": r_account, "docstatus": 1},
					fields=["debit_in_account_currency", "credit_in_account_currency"]
				)
				if not je_lines:
					raise Exception("Could not trace original accounting lines within target document.")

				parent_company = frappe.db.get_value("Journal Entry", v_no, "company")
				parent_date = frappe.db.get_value("Journal Entry", v_no, "posting_date")

				je = frappe.new_doc("Journal Entry")
				je.company = parent_company
				je.entry_type = "Journal Entry"
				je.posting_date = parent_date
				je.cheque_no = v_no
				je.cheque_date = parent_date
				je.user_remark = f"Reverse & Reclass of Journal Entry line from {v_no} to Employee AR."

				for line in je_lines:
					row_customer = {
						"account": r_account, "party_type": "Customer", "party": party,
						"debit_in_account_currency": line.credit_in_account_currency,
						"credit_in_account_currency": line.debit_in_account_currency,
						"is_advance": "No"
					}
					row_employee = {
						"account": "1451 - ACCOUNTS RECEIVABLE - EMPLOYEE - CM CDO", "party_type": "Employee", "party": linked_employee,
						"debit_in_account_currency": line.debit_in_account_currency,
						"credit_in_account_currency": line.credit_in_account_currency,
						"is_advance": "No"
					}
					je.append("accounts", row_customer)
					je.append("accounts", row_employee)

				je.insert(ignore_permissions=True)
				je.submit()

			# --- REVERSING INTERFACE FOR SALES INVOICES ---
			elif v_type == "Sales Invoice":
				parent_company = frappe.db.get_value("Sales Invoice", v_no, "company")
				current_date = nowdate()

				je = frappe.new_doc("Journal Entry")
				je.company = parent_company
				je.entry_type = "Journal Entry"
				je.posting_date = current_date
				je.cheque_no = v_no
				je.cheque_date = current_date
				je.user_remark = f"Reclass of {v_no} to Employee AR"

				row_customer = {
					"account": r_account, "party_type": "Customer", "party": party,
					"debit_in_account_currency": amount_to_move if not is_debit_balance else 0,
					"credit_in_account_currency": amount_to_move if is_debit_balance else 0,
					"is_advance": "No"
				}
				if is_debit_balance:
					row_customer.update({"reference_type": v_type, "reference_name": v_no})

				row_employee = {
					"account": "1451 - ACCOUNTS RECEIVABLE - EMPLOYEE - CM CDO", "party_type": "Employee", "party": linked_employee,
					"debit_in_account_currency": amount_to_move if is_debit_balance else 0,
					"credit_in_account_currency": amount_to_move if not is_debit_balance else 0,
					"is_advance": "No"
				}
				je.append("accounts", row_customer)
				je.append("accounts", row_employee)

				je.insert(ignore_permissions=True)
				je.submit()

			execution_logs.append({
				"Voucher Type": v_type, "Voucher No": v_no, "Customer": party,
				"Employee ID": linked_employee, "Status": "Success", 
				"Details": f"Successfully created and submitted adjustment ledger entry {je.name}"
			})

		except Exception as err:
			frappe.db.rollback()
			execution_logs.append({
				"Voucher Type": v_type, "Voucher No": v_no, "Customer": party,
				"Employee ID": linked_employee, "Status": "Error", 
				"Details": f"System validation rejected entry: {str(err)}"
			})

		frappe.publish_realtime("reclass_progress", {
			"current": current_count, "total": total_rows,
			"message": f"Processed line {v_type} {v_no}", "alert": False
		}, user=frappe.session.user)

	if execution_logs:
		csv_buffer = StringIO()
		headers = ["Voucher Type", "Voucher No", "Customer", "Employee ID", "Status", "Details"]
		writer = csv.DictWriter(csv_buffer, fieldnames=headers)
		writer.writeheader()
		writer.writerows(execution_logs)

		log_file = frappe.get_doc({
			"doctype": "File",
			"file_name": f"AR_Reclassification_Log_{nowdate()}.csv",
			"content": csv_buffer.getvalue(),
			"is_private": 0
		})
		log_file.insert(ignore_permissions=True)

		success_count = len([x for x in execution_logs if x["Status"] == "Success"])
		return {
			"status": "complete",
			"file_url": log_file.file_url,
			"message": f"Operation complete. Successfully processed {success_count} ledger rows. Check downloaded spreadsheet for complete row-by-row audit results."
		}

	return {"status": "empty", "message": "No operations required processing."}