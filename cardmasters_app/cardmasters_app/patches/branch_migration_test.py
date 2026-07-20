import frappe
from frappe.utils import flt


# =============================================================================
# CONFIGURATION
# =============================================================================

COMPANY = "CARDMASTERS CDO"
TARGET_BRANCH = "Cagayan de Oro"
BRANCH_FIELD = "branch"
CUTOFF_DATE = "2026-07-15"
PRECISION = 6


# Representative documents discovered from the restored production database.
SAMPLES = [
	# Already-tested control
	("Sales Invoice", "ACC-SINV-2026-08709", "Sales Invoice control"),

	# Purchase Invoice
	(
		"Purchase Invoice",
		"ACC-PINV-2026-04124",
		"Unpaid Purchase Invoice with taxes",
	),
	(
		"Purchase Invoice",
		"ACC-PINV-2026-04070",
		"Partially paid Purchase Invoice",
	),

	# Payment Entry
	(
		"Payment Entry",
		"PAY50396UCPB 3254701 CDO-0429",
		"Supplier payment with 28 references",
	),
	(
		"Payment Entry",
		"PAY50155CR8318",
		"Customer receipt with multiple references and unallocated amount",
	),

	# Journal Entry
	(
		"Journal Entry",
		"ACC-JV-2026-04363",
		"Two-row Journal Entry with customer and supplier",
	),
	(
		"Journal Entry",
		"ACC-JV-2026-04361",
		"Multi-row supplier Journal Entry",
	),
	(
		"Journal Entry",
		"ACC-JV-2026-04279",
		"Opening Journal Entry",
	),

	# Delivery Note
	(
		"Delivery Note",
		"MAT-DN-2026-09032",
		"Normal Delivery Note from Sales Order with taxes",
	),
	(
		"Delivery Note",
		"MAT-DN-2026-07755",
		"Sales Return Delivery Note",
	),

	# Purchase Receipt
	(
		"Purchase Receipt",
		"MAT-PRE-2026-01351",
		"Purchase Receipt from Purchase Order with taxes",
	),

	# Stock Entry purposes
	(
		"Stock Entry",
		"MAT-STE-2026-20536",
		"Material Receipt",
	),
	(
		"Stock Entry",
		"MAT-STE-2026-16263",
		"Material Issue",
	),
	(
		"Stock Entry",
		"MAT-STE-2026-26354",
		"Material Transfer",
	),
	(
		"Stock Entry",
		"MAT-STE-2026-26525",
		"Material Transfer for Manufacture",
	),
	(
		"Stock Entry",
		"MAT-STE-2026-26484",
		"Manufacture",
	),
	(
		"Stock Entry",
		"MAT-STE-2026-24011-2",
		"Repack",
	),

	# Stock Reconciliation
	(
		"Stock Reconciliation",
		"MAT-RECO-2026-00099",
		"Quantity, valuation and multi-item reconciliation",
	),
]


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def normalize_number(value):
	return round(flt(value), PRECISION)


def normalize_text(value):
	if value is None:
		return ""
	return str(value)


def print_separator(character="=", length=100):
	print(character * length)


def print_heading(title):
	print()
	print_separator()
	print(title)
	print_separator()


def get_field_value(row, fieldname):
	try:
		return row.get(fieldname)
	except Exception:
		return getattr(row, fieldname, None)


def get_document_posting_date(doc):
	possible_fields = [
		"posting_date",
		"transaction_date",
	]

	for fieldname in possible_fields:
		if doc.meta.has_field(fieldname):
			return doc.get(fieldname)

	return None


def get_document_company(doc):
	if doc.meta.has_field("company"):
		return doc.get("company")

	return None


# =============================================================================
# SOURCE DOCUMENT INSPECTION
# =============================================================================

def get_branch_locations(doc):
	"""
	Return every header or child-table location where the Branch field exists.
	"""

	locations = []

	if doc.meta.has_field(BRANCH_FIELD):
		locations.append(
			{
				"location_type": "header",
				"table_field": None,
				"row_name": doc.name,
				"value": doc.get(BRANCH_FIELD),
			}
		)

	for df in doc.meta.fields:
		if df.fieldtype != "Table":
			continue

		rows = doc.get(df.fieldname)

		if not rows:
			continue

		for row in rows:
			if not row.meta.has_field(BRANCH_FIELD):
				continue

			locations.append(
				{
					"location_type": "child",
					"table_field": df.fieldname,
					"row_name": row.name,
					"value": row.get(BRANCH_FIELD),
				}
			)

	return locations


def validate_no_conflicting_branch(doc):
	"""
	Stop if any existing branch value is neither blank nor the target branch.
	"""

	conflicts = []
	locations = get_branch_locations(doc)

	for location in locations:
		value = location["value"]

		if not value:
			continue

		if value == TARGET_BRANCH:
			continue

		conflicts.append(location)

	if conflicts:
		messages = []

		for conflict in conflicts:
			message = (
				conflict["location_type"]
				+ " "
				+ normalize_text(conflict["table_field"])
				+ " "
				+ normalize_text(conflict["row_name"])
				+ " currently has Branch "
				+ normalize_text(conflict["value"])
			)
			messages.append(message)

		frappe.throw(
			"Conflicting Branch values found:\n"
			+ "\n".join(messages)
		)


def assign_branch_to_source(doc):
	"""
	Set Branch on the document header and all child rows where the field exists.
	"""

	updated_locations = []

	if doc.meta.has_field(BRANCH_FIELD):
		current_value = doc.get(BRANCH_FIELD)

		if current_value != TARGET_BRANCH:
			doc.set(BRANCH_FIELD, TARGET_BRANCH)

			updated_locations.append(
				"Header: " + doc.doctype + " " + doc.name
			)

	for df in doc.meta.fields:
		if df.fieldtype != "Table":
			continue

		rows = doc.get(df.fieldname)

		if not rows:
			continue

		for row in rows:
			if not row.meta.has_field(BRANCH_FIELD):
				continue

			current_value = row.get(BRANCH_FIELD)

			if current_value == TARGET_BRANCH:
				continue

			row.set(BRANCH_FIELD, TARGET_BRANCH)

			updated_locations.append(
				df.fieldname + ": " + row.name
			)

	return updated_locations


def verify_source_branch(doc):
	"""
	Confirm that every applicable source location contains the target Branch.
	"""

	failures = []
	locations = get_branch_locations(doc)

	if not locations:
		failures.append(
			"No Branch field was found on the header or any child table."
		)
		return failures

	for location in locations:
		if location["value"] == TARGET_BRANCH:
			continue

		message = (
			location["location_type"]
			+ " "
			+ normalize_text(location["table_field"])
			+ " "
			+ normalize_text(location["row_name"])
			+ " has Branch "
			+ normalize_text(location["value"])
		)

		failures.append(message)

	return failures


# =============================================================================
# DOCUMENT FINANCIAL SNAPSHOT
# =============================================================================

DOCUMENT_VALUE_FIELDS = [
	"grand_total",
	"rounded_total",
	"base_grand_total",
	"base_rounded_total",
	"outstanding_amount",
	"paid_amount",
	"received_amount",
	"unallocated_amount",
	"total_debit",
	"total_credit",
	"difference",
	"difference_amount",
	"total_outgoing_value",
	"total_incoming_value",
	"value_difference",
	"total_taxes_and_charges",
	"base_total_taxes_and_charges",
	"net_total",
	"base_net_total",
]


def capture_document_values(doc):
	values = {}

	for fieldname in DOCUMENT_VALUE_FIELDS:
		if not doc.meta.has_field(fieldname):
			continue

		values[fieldname] = normalize_number(
			doc.get(fieldname)
		)

	return values


# =============================================================================
# GENERAL LEDGER SNAPSHOT
# =============================================================================

def capture_gl_snapshot(doctype, document_name):
	rows = frappe.db.sql(
		"""
		SELECT
			account,
			party_type,
			party,
			against,
			against_voucher_type,
			against_voucher,
			debit,
			credit,
			debit_in_account_currency,
			credit_in_account_currency,
			account_currency,
			cost_center,
			project,
			finance_book,
			branch
		FROM `tabGL Entry`
		WHERE voucher_type = %s
		  AND voucher_no = %s
		  AND is_cancelled = 0
		ORDER BY
			account,
			party_type,
			party,
			against_voucher_type,
			against_voucher,
			debit,
			credit
		""",
		(doctype, document_name),
		as_dict=True,
	)

	signature = []
	total_debit = 0
	total_credit = 0

	for row in rows:
		total_debit += flt(row.debit)
		total_credit += flt(row.credit)

		signature_row = (
			normalize_text(row.account),
			normalize_text(row.party_type),
			normalize_text(row.party),
			normalize_text(row.against),
			normalize_text(row.against_voucher_type),
			normalize_text(row.against_voucher),
			normalize_number(row.debit),
			normalize_number(row.credit),
			normalize_number(row.debit_in_account_currency),
			normalize_number(row.credit_in_account_currency),
			normalize_text(row.account_currency),
			normalize_text(row.cost_center),
			normalize_text(row.project),
			normalize_text(row.finance_book),
		)

		signature.append(signature_row)

	signature.sort()

	branch_values = []

	for row in rows:
		branch_values.append(row.branch)

	return {
		"count": len(rows),
		"total_debit": normalize_number(total_debit),
		"total_credit": normalize_number(total_credit),
		"signature": signature,
		"branches": branch_values,
	}


# =============================================================================
# PAYMENT LEDGER SNAPSHOT
# =============================================================================

def capture_payment_ledger_snapshot(doctype, document_name):
	meta = frappe.get_meta("Payment Ledger Entry")

	if not meta.has_field("branch"):
		return {
			"available": False,
			"count": 0,
			"total_amount": 0,
			"signature": [],
			"branches": [],
		}

	fields = [
		"account",
		"party_type",
		"party",
		"voucher_type",
		"voucher_no",
		"against_voucher_type",
		"against_voucher_no",
		"amount",
		"account_currency",
		"branch",
	]

	valid_fields = []

	for fieldname in fields:
		if meta.has_field(fieldname):
			valid_fields.append(fieldname)

	filters = {
		"voucher_type": doctype,
		"voucher_no": document_name,
	}

	if meta.has_field("delinked"):
		filters["delinked"] = 0

	rows = frappe.get_all(
		"Payment Ledger Entry",
		filters=filters,
		fields=valid_fields,
		order_by="creation asc",
	)

	signature = []
	branches = []
	total_amount = 0

	for row in rows:
		amount = get_field_value(row, "amount")
		total_amount += flt(amount)

		signature_row = (
			normalize_text(get_field_value(row, "account")),
			normalize_text(get_field_value(row, "party_type")),
			normalize_text(get_field_value(row, "party")),
			normalize_text(get_field_value(row, "voucher_type")),
			normalize_text(get_field_value(row, "voucher_no")),
			normalize_text(
				get_field_value(row, "against_voucher_type")
			),
			normalize_text(
				get_field_value(row, "against_voucher_no")
			),
			normalize_number(amount),
			normalize_text(
				get_field_value(row, "account_currency")
			),
		)

		signature.append(signature_row)
		branches.append(
			get_field_value(row, BRANCH_FIELD)
		)

	signature.sort()

	return {
		"available": True,
		"count": len(rows),
		"total_amount": normalize_number(total_amount),
		"signature": signature,
		"branches": branches,
	}


# =============================================================================
# STOCK LEDGER SNAPSHOT
# =============================================================================

def capture_stock_ledger_snapshot(doctype, document_name):
	rows = frappe.db.sql(
		"""
		SELECT
			item_code,
			warehouse,
			actual_qty,
			qty_after_transaction,
			valuation_rate,
			stock_value,
			stock_value_difference,
			batch_no,
			serial_no
		FROM `tabStock Ledger Entry`
		WHERE voucher_type = %s
		  AND voucher_no = %s
		  AND is_cancelled = 0
		ORDER BY
			item_code,
			warehouse,
			posting_date,
			posting_time,
			creation
		""",
		(doctype, document_name),
		as_dict=True,
	)

	signature = []
	total_actual_qty = 0
	total_value_difference = 0

	for row in rows:
		total_actual_qty += flt(row.actual_qty)
		total_value_difference += flt(
			row.stock_value_difference
		)

		signature_row = (
			normalize_text(row.item_code),
			normalize_text(row.warehouse),
			normalize_number(row.actual_qty),
			normalize_number(row.qty_after_transaction),
			normalize_number(row.valuation_rate),
			normalize_number(row.stock_value),
			normalize_number(row.stock_value_difference),
			normalize_text(row.batch_no),
			normalize_text(row.serial_no),
		)

		signature.append(signature_row)

	signature.sort()

	return {
		"count": len(rows),
		"total_actual_qty": normalize_number(total_actual_qty),
		"total_value_difference": normalize_number(
			total_value_difference
		),
		"signature": signature,
	}


# =============================================================================
# SNAPSHOT COMPARISON
# =============================================================================

def compare_document_values(before, after):
	failures = []

	all_fields = []

	for fieldname in before:
		if fieldname not in all_fields:
			all_fields.append(fieldname)

	for fieldname in after:
		if fieldname not in all_fields:
			all_fields.append(fieldname)

	for fieldname in all_fields:
		before_value = before.get(fieldname)
		after_value = after.get(fieldname)

		if before_value == after_value:
			continue

		failures.append(
			"Document field "
			+ fieldname
			+ " changed from "
			+ normalize_text(before_value)
			+ " to "
			+ normalize_text(after_value)
		)

	return failures


def compare_gl(before, after):
	failures = []

	if before["count"] != after["count"]:
		failures.append(
			"Active GL row count changed from "
			+ str(before["count"])
			+ " to "
			+ str(after["count"])
		)

	if before["total_debit"] != after["total_debit"]:
		failures.append(
			"GL debit changed from "
			+ str(before["total_debit"])
			+ " to "
			+ str(after["total_debit"])
		)

	if before["total_credit"] != after["total_credit"]:
		failures.append(
			"GL credit changed from "
			+ str(before["total_credit"])
			+ " to "
			+ str(after["total_credit"])
		)

	if before["signature"] != after["signature"]:
		failures.append(
			"The active GL accounting signature changed."
		)

	for value in after["branches"]:
		if value != TARGET_BRANCH:
			failures.append(
				"An active GL Entry has Branch "
				+ normalize_text(value)
			)
			break

	return failures


def compare_payment_ledger(before, after):
	failures = []

	if not before["available"] and not after["available"]:
		return failures

	if before["count"] != after["count"]:
		failures.append(
			"Active Payment Ledger row count changed from "
			+ str(before["count"])
			+ " to "
			+ str(after["count"])
		)

	if before["total_amount"] != after["total_amount"]:
		failures.append(
			"Payment Ledger amount changed from "
			+ str(before["total_amount"])
			+ " to "
			+ str(after["total_amount"])
		)

	if before["signature"] != after["signature"]:
		failures.append(
			"The active Payment Ledger signature changed."
		)

	for value in after["branches"]:
		if value != TARGET_BRANCH:
			failures.append(
				"An active Payment Ledger Entry has Branch "
				+ normalize_text(value)
			)
			break

	return failures


def compare_stock_ledger(before, after):
	failures = []

	if before["count"] != after["count"]:
		failures.append(
			"Active Stock Ledger row count changed from "
			+ str(before["count"])
			+ " to "
			+ str(after["count"])
		)

	if (
		before["total_actual_qty"]
		!= after["total_actual_qty"]
	):
		failures.append(
			"Stock Ledger quantity changed from "
			+ str(before["total_actual_qty"])
			+ " to "
			+ str(after["total_actual_qty"])
		)

	if (
		before["total_value_difference"]
		!= after["total_value_difference"]
	):
		failures.append(
			"Stock value difference changed from "
			+ str(before["total_value_difference"])
			+ " to "
			+ str(after["total_value_difference"])
		)

	if before["signature"] != after["signature"]:
		failures.append(
			"The active Stock Ledger signature changed."
		)

	return failures


# =============================================================================
# INDIVIDUAL SAMPLE TEST
# =============================================================================

def test_sample(doctype, document_name, description):
	frappe.db.rollback()

	result = {
		"doctype": doctype,
		"name": document_name,
		"description": description,
		"status": "FAIL",
		"messages": [],
	}

	print_heading(
		doctype + " — " + document_name
	)
	print(description)

	try:
		if not frappe.db.exists(doctype, document_name):
			frappe.throw(
				doctype
				+ " "
				+ document_name
				+ " does not exist."
			)

		doc = frappe.get_doc(doctype, document_name)

		if doc.docstatus != 1:
			frappe.throw(
				"Document must be submitted. Current docstatus: "
				+ str(doc.docstatus)
			)

		company = get_document_company(doc)

		if company and company != COMPANY:
			frappe.throw(
				"Company mismatch. Expected "
				+ COMPANY
				+ ", found "
				+ normalize_text(company)
			)

		posting_date = get_document_posting_date(doc)

		if posting_date:
			if str(posting_date) > CUTOFF_DATE:
				frappe.throw(
					"Posting date "
					+ str(posting_date)
					+ " is after cutoff "
					+ CUTOFF_DATE
				)

		validate_no_conflicting_branch(doc)

		before_document = capture_document_values(doc)
		before_gl = capture_gl_snapshot(
			doctype,
			document_name,
		)
		before_ple = capture_payment_ledger_snapshot(
			doctype,
			document_name,
		)
		before_sle = capture_stock_ledger_snapshot(
			doctype,
			document_name,
		)

		print("Before:")
		print(
			"  Active GL:",
			before_gl["count"],
			"Debit:",
			before_gl["total_debit"],
			"Credit:",
			before_gl["total_credit"],
		)
		print(
			"  Active Payment Ledger:",
			before_ple["count"],
			"Amount:",
			before_ple["total_amount"],
		)
		print(
			"  Active Stock Ledger:",
			before_sle["count"],
			"Value difference:",
			before_sle["total_value_difference"],
		)

		updated_locations = assign_branch_to_source(doc)

		if not updated_locations:
			print(
				"Source already contains the target Branch "
				"in all applicable locations."
			)
		else:
			print(
				"Updated source locations:",
				len(updated_locations),
			)

		doc.flags.ignore_validate_update_after_submit = True

		doc.save(
			ignore_permissions=True,
			ignore_version=True,
		)

		doc.reload()

		after_document = capture_document_values(doc)
		after_gl = capture_gl_snapshot(
			doctype,
			document_name,
		)
		after_ple = capture_payment_ledger_snapshot(
			doctype,
			document_name,
		)
		after_sle = capture_stock_ledger_snapshot(
			doctype,
			document_name,
		)

		failures = []

		source_failures = verify_source_branch(doc)

		for message in source_failures:
			failures.append(
				"Source Branch validation: " + message
			)

		document_failures = compare_document_values(
			before_document,
			after_document,
		)

		for message in document_failures:
			failures.append(message)

		gl_failures = compare_gl(
			before_gl,
			after_gl,
		)

		for message in gl_failures:
			failures.append(message)

		ple_failures = compare_payment_ledger(
			before_ple,
			after_ple,
		)

		for message in ple_failures:
			failures.append(message)

		sle_failures = compare_stock_ledger(
			before_sle,
			after_sle,
		)

		for message in sle_failures:
			failures.append(message)

		if failures:
			frappe.db.rollback()

			result["status"] = "FAIL"
			result["messages"] = failures

			print()
			print("RESULT: FAIL — rolled back")

			for message in failures:
				print("  -", message)

			return result

		frappe.db.commit()

		result["status"] = "PASS"
		result["messages"] = [
			"Source, GL, Payment Ledger and Stock Ledger validations passed."
		]

		print()
		print("RESULT: PASS — committed")
		print(
			"  Active GL after:",
			after_gl["count"],
			"Debit:",
			after_gl["total_debit"],
			"Credit:",
			after_gl["total_credit"],
		)
		print(
			"  Active Payment Ledger after:",
			after_ple["count"],
			"Amount:",
			after_ple["total_amount"],
		)
		print(
			"  Active Stock Ledger after:",
			after_sle["count"],
			"Value difference:",
			after_sle["total_value_difference"],
		)

		return result

	except Exception as error:
		frappe.db.rollback()

		result["status"] = "ERROR"
		result["messages"] = [
			str(error),
		]

		print()
		print("RESULT: ERROR — rolled back")
		print(type(error).__name__ + ":", str(error))

		return result


# =============================================================================
# RUN TEST HARNESS
# =============================================================================

def run():
	frappe.db.rollback()

	print_heading("ACCOUNTING DIMENSION MIGRATION TEST HARNESS")

	print("Company:", COMPANY)
	print("Target Branch:", TARGET_BRANCH)
	print("Cutoff Date:", CUTOFF_DATE)
	print("Samples:", len(SAMPLES))

	RESULTS = []

	for sample in SAMPLES:
		doctype = sample[0]
		document_name = sample[1]
		description = sample[2]

		sample_result = test_sample(
			doctype,
			document_name,
			description,
		)

		RESULTS.append(sample_result)


	# =============================================================================
	# CONSOLIDATED RESULTS
	# =============================================================================

	print_heading("CONSOLIDATED TEST RESULTS")

	pass_count = 0
	fail_count = 0
	error_count = 0

	for result in RESULTS:
		status = result["status"]

		if status == "PASS":
			pass_count += 1
		elif status == "FAIL":
			fail_count += 1
		else:
			error_count += 1

		print(
			status.ljust(6),
			"|",
			result["doctype"],
			"|",
			result["name"],
			"|",
			result["description"],
		)

		if status != "PASS":
			for message in result["messages"]:
				print("       -", message)

	print()
	print_separator()
	print("PASS:", pass_count)
	print("FAIL:", fail_count)
	print("ERROR:", error_count)
	print("TOTAL:", len(RESULTS))
	print_separator()

	if fail_count == 0 and error_count == 0:
		print(
			"ALL REPRESENTATIVE MIGRATION TESTS PASSED."
		)
	else:
		print(
			"ONE OR MORE TESTS REQUIRE REVIEW. "
			"FAILED OR ERROR SAMPLES WERE ROLLED BACK."
		)