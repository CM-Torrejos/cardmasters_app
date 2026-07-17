import frappe
from frappe.utils import flt


COMPANY = "CARDMASTERS CDO"
TARGET_BRANCH = "Cagayan de Oro"
BRANCH_FIELD = "branch"
PRECISION = 6


NATIVE_REPOST_SAMPLES = [
    (
        "Journal Entry",
        "ACC-JV-2026-04279",
        "Opening Journal Entry after temporarily unfreezing accounts",
    ),
]


DIRECT_BACKFILL_SAMPLES = [
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
    (
        "Purchase Receipt",
        "MAT-PRE-2026-01351",
        "Purchase Receipt from Purchase Order with taxes",
    ),
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
    (
        "Stock Reconciliation",
        "MAT-RECO-2026-00099",
        "Quantity, valuation and multi-item reconciliation",
    ),
]


def number(value):
    return round(flt(value), PRECISION)


def text(value):
    return "" if value is None else str(value)


def heading(title):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def capture_gl(doctype, name):
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
        (doctype, name),
        as_dict=True,
    )

    signature = []
    total_debit = 0
    total_credit = 0
    branches = []

    for row in rows:
        total_debit += flt(row.debit)
        total_credit += flt(row.credit)
        branches.append(row.branch)

        signature.append(
            (
                text(row.account),
                text(row.party_type),
                text(row.party),
                text(row.against),
                text(row.against_voucher_type),
                text(row.against_voucher),
                number(row.debit),
                number(row.credit),
                number(row.debit_in_account_currency),
                number(row.credit_in_account_currency),
                text(row.account_currency),
                text(row.cost_center),
                text(row.project),
                text(row.finance_book),
            )
        )

    signature.sort()

    return {
        "count": len(rows),
        "debit": number(total_debit),
        "credit": number(total_credit),
        "signature": signature,
        "branches": branches,
    }


def capture_stock_ledger(doctype, name):
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
        (doctype, name),
        as_dict=True,
    )

    signature = []

    for row in rows:
        signature.append(
            (
                text(row.item_code),
                text(row.warehouse),
                number(row.actual_qty),
                number(row.qty_after_transaction),
                number(row.valuation_rate),
                number(row.stock_value),
                number(row.stock_value_difference),
                text(row.batch_no),
                text(row.serial_no),
            )
        )

    signature.sort()

    return {
        "count": len(rows),
        "signature": signature,
    }


def capture_payment_ledger(doctype, name):
    meta = frappe.get_meta("Payment Ledger Entry")

    if not meta.has_field("branch"):
        return {
            "count": 0,
            "amount": 0,
            "signature": [],
            "branches": [],
        }

    filters = {
        "voucher_type": doctype,
        "voucher_no": name,
    }

    if meta.has_field("delinked"):
        filters["delinked"] = 0

    rows = frappe.get_all(
        "Payment Ledger Entry",
        filters=filters,
        fields=[
            "account",
            "party_type",
            "party",
            "against_voucher_type",
            "against_voucher_no",
            "amount",
            "branch",
        ],
    )

    signature = []
    branches = []
    amount = 0

    for row in rows:
        amount += flt(row.amount)
        branches.append(row.branch)

        signature.append(
            (
                text(row.account),
                text(row.party_type),
                text(row.party),
                text(row.against_voucher_type),
                text(row.against_voucher_no),
                number(row.amount),
            )
        )

    signature.sort()

    return {
        "count": len(rows),
        "amount": number(amount),
        "signature": signature,
        "branches": branches,
    }


def validate_company(doc):
    if doc.meta.has_field("company") and doc.company != COMPANY:
        frappe.throw(
            f"{doc.doctype} {doc.name} belongs to {doc.company}, not {COMPANY}."
        )

    if doc.docstatus != 1:
        frappe.throw(
            f"{doc.doctype} {doc.name} is not submitted. Docstatus: {doc.docstatus}"
        )


def validate_no_conflicting_source_branch(doc):
    if doc.meta.has_field(BRANCH_FIELD):
        value = doc.get(BRANCH_FIELD)

        if value and value != TARGET_BRANCH:
            frappe.throw(
                f"{doc.doctype} {doc.name} already has Branch {value}."
            )

    for df in doc.meta.fields:
        if df.fieldtype != "Table":
            continue

        for row in doc.get(df.fieldname) or []:
            if not row.meta.has_field(BRANCH_FIELD):
                continue

            value = row.get(BRANCH_FIELD)

            if value and value != TARGET_BRANCH:
                frappe.throw(
                    f"{row.doctype} {row.name} already has Branch {value}."
                )


def set_source_branch_directly(doc):
    updated = 0

    if doc.meta.has_field(BRANCH_FIELD):
        current = doc.get(BRANCH_FIELD)

        if current != TARGET_BRANCH:
            frappe.db.set_value(
                doc.doctype,
                doc.name,
                BRANCH_FIELD,
                TARGET_BRANCH,
                update_modified=False,
            )
            updated += 1

    for df in doc.meta.fields:
        if df.fieldtype != "Table":
            continue

        for row in doc.get(df.fieldname) or []:
            if not row.meta.has_field(BRANCH_FIELD):
                continue

            current = row.get(BRANCH_FIELD)

            if current == TARGET_BRANCH:
                continue

            frappe.db.set_value(
                row.doctype,
                row.name,
                BRANCH_FIELD,
                TARGET_BRANCH,
                update_modified=False,
            )
            updated += 1

    return updated


def verify_source_branch(doc):
    doc.reload()
    failures = []

    if doc.meta.has_field(BRANCH_FIELD):
        if doc.get(BRANCH_FIELD) != TARGET_BRANCH:
            failures.append(
                f"Header Branch is {doc.get(BRANCH_FIELD)}."
            )

    for df in doc.meta.fields:
        if df.fieldtype != "Table":
            continue

        for row in doc.get(df.fieldname) or []:
            if not row.meta.has_field(BRANCH_FIELD):
                continue

            if row.get(BRANCH_FIELD) != TARGET_BRANCH:
                failures.append(
                    f"{row.doctype} {row.name} Branch is {row.get(BRANCH_FIELD)}."
                )

    return failures


def validate_gl_unchanged(before, after):
    failures = []

    if before["count"] != after["count"]:
        failures.append(
            f"GL row count changed from {before['count']} to {after['count']}."
        )

    if before["debit"] != after["debit"]:
        failures.append(
            f"GL debit changed from {before['debit']} to {after['debit']}."
        )

    if before["credit"] != after["credit"]:
        failures.append(
            f"GL credit changed from {before['credit']} to {after['credit']}."
        )

    if before["signature"] != after["signature"]:
        failures.append("GL accounting signature changed.")

    for branch in after["branches"]:
        if branch != TARGET_BRANCH:
            failures.append(
                f"Active GL Entry still has Branch {branch}."
            )
            break

    return failures


def validate_stock_ledger_unchanged(before, after):
    failures = []

    if before["count"] != after["count"]:
        failures.append(
            f"Stock Ledger row count changed from {before['count']} "
            f"to {after['count']}."
        )

    if before["signature"] != after["signature"]:
        failures.append("Stock Ledger signature changed.")

    return failures


def validate_payment_ledger_unchanged(before, after):
    failures = []

    if before["count"] != after["count"]:
        failures.append(
            f"Payment Ledger row count changed from {before['count']} "
            f"to {after['count']}."
        )

    if before["amount"] != after["amount"]:
        failures.append(
            f"Payment Ledger amount changed from {before['amount']} "
            f"to {after['amount']}."
        )

    if before["signature"] != after["signature"]:
        failures.append("Payment Ledger signature changed.")

    for branch in after["branches"]:
        if branch != TARGET_BRANCH:
            failures.append(
                f"Active Payment Ledger Entry still has Branch {branch}."
            )
            break

    return failures


def test_native_repost(doctype, name, description):
    frappe.db.rollback()

    heading(f"NATIVE REPOST — {doctype} — {name}")
    print(description)

    try:
        doc = frappe.get_doc(doctype, name)

        validate_company(doc)
        validate_no_conflicting_source_branch(doc)

        before_gl = capture_gl(doctype, name)
        before_ple = capture_payment_ledger(doctype, name)
        before_sle = capture_stock_ledger(doctype, name)

        if doc.meta.has_field(BRANCH_FIELD):
            doc.set(BRANCH_FIELD, TARGET_BRANCH)

        for df in doc.meta.fields:
            if df.fieldtype != "Table":
                continue

            for row in doc.get(df.fieldname) or []:
                if row.meta.has_field(BRANCH_FIELD):
                    row.set(BRANCH_FIELD, TARGET_BRANCH)

        doc.flags.ignore_validate_update_after_submit = True

        doc.save(
            ignore_permissions=True,
            ignore_version=True,
        )

        doc.reload()

        after_gl = capture_gl(doctype, name)
        after_ple = capture_payment_ledger(doctype, name)
        after_sle = capture_stock_ledger(doctype, name)

        failures = []

        failures.extend(verify_source_branch(doc))
        failures.extend(validate_gl_unchanged(before_gl, after_gl))
        failures.extend(
            validate_payment_ledger_unchanged(before_ple, after_ple)
        )
        failures.extend(
            validate_stock_ledger_unchanged(before_sle, after_sle)
        )

        if failures:
            frappe.db.rollback()

            print("RESULT: FAIL — rolled back")

            for failure in failures:
                print("  -", failure)

            return {
                "status": "FAIL",
                "doctype": doctype,
                "name": name,
                "messages": failures,
            }

        frappe.db.commit()

        print("RESULT: PASS — committed")

        return {
            "status": "PASS",
            "doctype": doctype,
            "name": name,
            "messages": [],
        }

    except Exception as error:
        frappe.db.rollback()

        print("RESULT: ERROR — rolled back")
        print(type(error).__name__ + ":", str(error))

        return {
            "status": "ERROR",
            "doctype": doctype,
            "name": name,
            "messages": [str(error)],
        }


def test_direct_backfill(doctype, name, description):
    frappe.db.rollback()

    heading(f"DIRECT BRANCH BACKFILL — {doctype} — {name}")
    print(description)

    try:
        doc = frappe.get_doc(doctype, name)

        validate_company(doc)
        validate_no_conflicting_source_branch(doc)

        before_gl = capture_gl(doctype, name)
        before_sle = capture_stock_ledger(doctype, name)

        updated_source_rows = set_source_branch_directly(doc)

        frappe.db.sql(
            """
            UPDATE `tabGL Entry`
            SET branch = %s
            WHERE voucher_type = %s
              AND voucher_no = %s
              AND is_cancelled = 0
              AND IFNULL(branch, '') = ''
            """,
            (TARGET_BRANCH, doctype, name),
        )

        doc.reload()

        after_gl = capture_gl(doctype, name)
        after_sle = capture_stock_ledger(doctype, name)

        failures = []

        failures.extend(verify_source_branch(doc))
        failures.extend(validate_gl_unchanged(before_gl, after_gl))
        failures.extend(
            validate_stock_ledger_unchanged(before_sle, after_sle)
        )

        if failures:
            frappe.db.rollback()

            print("RESULT: FAIL — rolled back")

            for failure in failures:
                print("  -", failure)

            return {
                "status": "FAIL",
                "doctype": doctype,
                "name": name,
                "messages": failures,
            }

        frappe.db.commit()

        print(
            f"RESULT: PASS — committed; "
            f"updated {updated_source_rows} source locations"
        )

        return {
            "status": "PASS",
            "doctype": doctype,
            "name": name,
            "messages": [],
        }

    except Exception as error:
        frappe.db.rollback()

        print("RESULT: ERROR — rolled back")
        print(type(error).__name__ + ":", str(error))

        return {
            "status": "ERROR",
            "doctype": doctype,
            "name": name,
            "messages": [str(error)],
        }


def run():
    heading("BRANCH MIGRATION SECOND-STAGE TEST")

    print("Company:", COMPANY)
    print("Target Branch:", TARGET_BRANCH)
    print(
        "Native repost samples:",
        len(NATIVE_REPOST_SAMPLES),
    )
    print(
        "Direct backfill samples:",
        len(DIRECT_BACKFILL_SAMPLES),
    )

    results = []

    for doctype, name, description in NATIVE_REPOST_SAMPLES:
        results.append(
            test_native_repost(
                doctype,
                name,
                description,
            )
        )

    for doctype, name, description in DIRECT_BACKFILL_SAMPLES:
        results.append(
            test_direct_backfill(
                doctype,
                name,
                description,
            )
        )

    heading("CONSOLIDATED SECOND-STAGE RESULTS")

    passed = 0
    failed = 0
    errors = 0

    for result in results:
        status = result["status"]

        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            failed += 1
        else:
            errors += 1

        print(
            status.ljust(6),
            "|",
            result["doctype"],
            "|",
            result["name"],
        )

        for message in result["messages"]:
            print("       -", message)

    print()
    print("=" * 100)
    print("PASS:", passed)
    print("FAIL:", failed)
    print("ERROR:", errors)
    print("TOTAL:", len(results))
    print("=" * 100)

    if failed == 0 and errors == 0:
        print("ALL SECOND-STAGE MIGRATION TESTS PASSED.")
    else:
        print(
            "ONE OR MORE SECOND-STAGE TESTS REQUIRE REVIEW. "
            "FAILED DOCUMENTS WERE ROLLED BACK."
        )

    return {
        "pass": passed,
        "fail": failed,
        "error": errors,
        "total": len(results),
        "results": results,
    }