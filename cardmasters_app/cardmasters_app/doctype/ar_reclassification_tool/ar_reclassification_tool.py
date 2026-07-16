# Copyright (c) 2026, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
import frappe.desk.query_report
import csv
from io import StringIO
from frappe.utils import flt, nowdate
from frappe.model.document import Document

class ARReclassificationTool(Document):
    pass

TARGET_ACCOUNTS = [
    "1451 - ACCOUNTS RECEIVABLE - EMPLOYEE - CM CDO", 
    "1410 - ACCOUNTS RECEIVABLE - TRADE - CM CDO"
]
EMPLOYEE_AR_ACCOUNT = "1451 - ACCOUNTS RECEIVABLE - EMPLOYEE - CM CDO"

@frappe.whitelist()
def run_employee_ar_reclassification(filters=None):
    _validate_permissions()
    filters = _parse_filters(filters)
    
    execution_logs = []
    customer_to_employee = _get_employee_mapping()
    
    report_rows, fieldnames = _get_ar_report_data(filters)
    if not report_rows:
        return {"status": "empty", "message": "No rows found in the default Accounts Receivable report for Employee Customers."}

    total_rows = len(report_rows)

    # Main Processing Loop
    for index, raw_row in enumerate(report_rows):
        row = _format_row(raw_row, fieldnames)
        if not row:
            continue

        v_type = row.get("voucher_type")
        v_no = row.get("voucher_no")
        party = row.get("party")
        outstanding = flt(row.get("outstanding_amount") or row.get("outstanding"))

        # 1. Basic Skip Conditions
        if v_type not in ["Journal Entry", "Sales Invoice"] or not v_no or outstanding == 0:
            continue

        r_account = _get_actual_receivable_account(v_type, v_no, party, row.get("account") or row.get("receivable_account"))
        if not r_account or r_account not in TARGET_ACCOUNTS:
            continue

        linked_employee = customer_to_employee.get(party)
        if not linked_employee:
            _append_log(execution_logs, v_type, v_no, party, "N/A", "Skipped", "No active Employee master record linked to this Customer profile.")
            continue

        # 2. Idempotency Check
        if _is_already_processed(v_type, v_no, party):
            _append_log(execution_logs, v_type, v_no, party, linked_employee, "Skipped", "A reclassification entry already exists.")
            continue

        # 3. Ledger Creation
        try:
            if v_type == "Journal Entry":
                je_name = _process_journal_entry_reclass(v_no, party, r_account, linked_employee)
            elif v_type == "Sales Invoice":
                je_name = _process_sales_invoice_reclass(v_type, v_no, party, r_account, linked_employee, outstanding)
            
            _append_log(execution_logs, v_type, v_no, party, linked_employee, "Success", f"Successfully created adjustment entry {je_name}")

        except Exception as err:
            frappe.db.rollback()
            _append_log(execution_logs, v_type, v_no, party, linked_employee, "Error", f"System validation rejected entry: {str(err)}")

        # 4. Update UI
        frappe.publish_realtime("reclass_progress", {
            "current": index + 1, "total": total_rows, "message": f"Processed line {v_type} {v_no}", "alert": False
        }, user=frappe.session.user)

    # Generate output
    return _finalize_and_log(execution_logs)


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def _validate_permissions():
    if not ("Accounts Manager" in frappe.get_roles() or "System Manager" in frappe.get_roles()):
        frappe.throw("Access Denied: You do not have the required accounting permissions.")

def _parse_filters(filters):
    if isinstance(filters, str):
        return frappe.parse_json(filters)
    return filters or {}

def _get_employee_mapping():
    employees = frappe.get_all(
        "Employee", 
        filters={"custom_customer_profile": ["!=", ""], "status": "Active"}, 
        fields=["name", "custom_customer_profile"]
    )
    return {emp.custom_customer_profile: emp.name for emp in employees}

def _get_ar_report_data(filters):
    default_ar_filters = {
        "company": filters.get("company") or frappe.defaults.get_user_default("Company"),
        "report_date": filters.get("report_date") or nowdate(),
        "party_type": "Customer",
        "customer_group": "Employee",
        "range": filters.get("range") or "30, 60, 90, 120"
    }

    report_data = frappe.desk.query_report.run("Accounts Receivable", filters=default_ar_filters)
    raw_columns = report_data.get("columns", [])
    
    fieldnames = [col.get("fieldname") if isinstance(col, dict) else col for col in raw_columns]
    return report_data.get("result", []), fieldnames

def _format_row(raw_row, fieldnames):
    if isinstance(raw_row, (list, tuple)):
        return frappe._dict(zip(fieldnames, raw_row))
    elif isinstance(raw_row, dict):
        return frappe._dict(raw_row)
    return None

def _get_actual_receivable_account(v_type, v_no, party, r_account):
    if r_account and r_account in TARGET_ACCOUNTS:
        return r_account

    if v_type == "Sales Invoice":
        return frappe.db.get_value("Sales Invoice", v_no, "debit_to")
    elif v_type == "Journal Entry":
        return frappe.db.get_value("Journal Entry Account", {"parent": v_no, "party": party}, "account")
    return None

def _is_already_processed(v_type, v_no, party):
    # 1. Ignore our own Reclassification Journal Entries
    if frappe.db.get_value(v_type, v_no, "custom_reclass_source_type", ignore=True):
        return True

    # 2. Duplicate Check using Custom Fields
    return frappe.db.exists("Journal Entry", {
        "custom_reclass_source_type": v_type,
        "custom_reclass_source_name": v_no,
        "custom_reclass_party": party,
        "docstatus": ["in", [0, 1]]
    })

def _process_journal_entry_reclass(v_no, party, r_account, linked_employee):
    je_lines = frappe.get_all(
        "Journal Entry Account",
        filters={"parent": v_no, "party": party, "account": r_account, "docstatus": 1},
        fields=["debit_in_account_currency", "credit_in_account_currency"]
    )
    if not je_lines:
        raise Exception("Could not trace original accounting lines within target document.")

    parent_company, parent_date = frappe.db.get_value("Journal Entry", v_no, ["company", "posting_date"])

    je = _init_journal_entry(parent_company, parent_date, "Journal Entry", v_no, party)
    je.user_remark = f"Reverse & Reclass of Journal Entry line from {v_no} to Employee AR."

    for line in je_lines:
        credit_amt = flt(line.debit_in_account_currency)
        debit_amt = flt(line.credit_in_account_currency)

        row_customer = _build_je_account_row(r_account, "Customer", party, debit_amt, credit_amt)
        
        if credit_amt > 0:
            row_customer.update({"reference_type": "Journal Entry", "reference_name": v_no})

        row_employee = _build_je_account_row(EMPLOYEE_AR_ACCOUNT, "Employee", linked_employee, credit_amt, debit_amt)
        
        je.append("accounts", row_customer)
        je.append("accounts", row_employee)

    je.insert(ignore_permissions=True)
    je.submit()
    return je.name

def _process_sales_invoice_reclass(v_type, v_no, party, r_account, linked_employee, outstanding):
    parent_company = frappe.db.get_value("Sales Invoice", v_no, "company")
    amount_to_move = abs(outstanding)
    is_debit_balance = outstanding > 0

    je = _init_journal_entry(parent_company, nowdate(), v_type, v_no, party)
    je.user_remark = f"Reclass of {v_no} to Employee AR"

    customer_debit = amount_to_move if not is_debit_balance else 0
    customer_credit = amount_to_move if is_debit_balance else 0
    row_customer = _build_je_account_row(r_account, "Customer", party, customer_debit, customer_credit)

    if is_debit_balance:
        row_customer.update({"reference_type": v_type, "reference_name": v_no})

    employee_debit = amount_to_move if is_debit_balance else 0
    employee_credit = amount_to_move if not is_debit_balance else 0
    row_employee = _build_je_account_row(EMPLOYEE_AR_ACCOUNT, "Employee", linked_employee, employee_debit, employee_credit)

    je.append("accounts", row_customer)
    je.append("accounts", row_employee)

    je.insert(ignore_permissions=True)
    je.submit()
    return je.name

def _init_journal_entry(company, posting_date, source_type, source_name, party):
    je = frappe.new_doc("Journal Entry")
    je.company = company
    je.entry_type = "Journal Entry"
    je.posting_date = posting_date
    je.custom_reclass_source_type = source_type
    je.custom_reclass_source_name = source_name
    je.custom_reclass_party = party
    return je

def _build_je_account_row(account, party_type, party, debit, credit):
    return {
        "account": account,
        "party_type": party_type,
        "party": party,
        "debit_in_account_currency": debit,
        "credit_in_account_currency": credit,
        "is_advance": "No"
    }

def _append_log(logs, v_type, v_no, party, emp_id, status, details):
    logs.append({
        "Voucher Type": v_type, "Voucher No": v_no, "Customer": party,
        "Employee ID": emp_id, "Status": status, "Details": details
    })

def _finalize_and_log(execution_logs):
    if not execution_logs:
        return {"status": "empty", "message": "No operations required processing."}

    csv_buffer = StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=["Voucher Type", "Voucher No", "Customer", "Employee ID", "Status", "Details"])
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
        "message": f"Operation complete. Successfully processed {success_count} ledger rows. Check downloaded spreadsheet for audit results."
    }