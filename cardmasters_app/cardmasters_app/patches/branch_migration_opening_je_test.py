import frappe
from frappe.utils import flt


COMPANY = "CARDMASTERS CDO"
TARGET_BRANCH = "Cagayan de Oro"
JOURNAL_ENTRY = "ACC-JV-2026-04279"
PRECISION = 6


def number(value):
    return round(flt(value), PRECISION)


def text(value):
    return "" if value is None else str(value)


def heading(title):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def capture_gl(name):
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
        WHERE voucher_type = 'Journal Entry'
          AND voucher_no = %s
          AND is_cancelled = 0
        ORDER BY
            account,
            party_type,
            party,
            debit,
            credit
        """,
        name,
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


def capture_payment_ledger(name):
    meta = frappe.get_meta("Payment Ledger Entry")

    filters = {
        "voucher_type": "Journal Entry",
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
        order_by="creation asc",
    )

    signature = []
    total_amount = 0
    branches = []

    for row in rows:
        total_amount += flt(row.amount)
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
        "amount": number(total_amount),
        "signature": signature,
        "branches": branches,
    }


def validate_unchanged(before, after, label):
    failures = []

    for key in before:
        if key == "branches":
            continue

        if before[key] != after[key]:
            failures.append(
                f"{label} {key} changed from "
                f"{before[key]} to {after[key]}."
            )

    for branch in after["branches"]:
        if branch != TARGET_BRANCH:
            failures.append(
                f"{label} still contains Branch {branch}."
            )
            break

    return failures


def run():
    frappe.db.rollback()

    heading("OPENING JOURNAL ENTRY DIRECT BACKFILL TEST")

    try:
        doc = frappe.get_doc("Journal Entry", JOURNAL_ENTRY)

        if doc.docstatus != 1:
            frappe.throw(
                f"{JOURNAL_ENTRY} is not submitted."
            )

        if doc.company != COMPANY:
            frappe.throw(
                f"Company is {doc.company}, expected {COMPANY}."
            )

        before_gl = capture_gl(JOURNAL_ENTRY)
        before_ple = capture_payment_ledger(JOURNAL_ENTRY)

        print("Before GL:", before_gl)
        print("Before Payment Ledger:", before_ple)

        # Journal Entry accounting dimensions belong on account rows.
        source_updates = 0

        for row in doc.accounts:
            if not row.meta.has_field("branch"):
                continue

            if row.branch and row.branch != TARGET_BRANCH:
                frappe.throw(
                    f"Journal Entry Account {row.name} already "
                    f"has conflicting Branch {row.branch}."
                )

            if row.branch != TARGET_BRANCH:
                frappe.db.set_value(
                    "Journal Entry Account",
                    row.name,
                    "branch",
                    TARGET_BRANCH,
                    update_modified=False,
                )
                source_updates += 1

        # Populate header only if this ERPNext version has the field.
        if doc.meta.has_field("branch"):
            if doc.branch and doc.branch != TARGET_BRANCH:
                frappe.throw(
                    f"Journal Entry header already has "
                    f"conflicting Branch {doc.branch}."
                )

            if doc.branch != TARGET_BRANCH:
                frappe.db.set_value(
                    "Journal Entry",
                    doc.name,
                    "branch",
                    TARGET_BRANCH,
                    update_modified=False,
                )
                source_updates += 1

        # Change classification only; do not repost.
        frappe.db.sql(
            """
            UPDATE `tabGL Entry`
            SET branch = %s
            WHERE voucher_type = 'Journal Entry'
              AND voucher_no = %s
              AND is_cancelled = 0
              AND IFNULL(branch, '') = ''
            """,
            (TARGET_BRANCH, JOURNAL_ENTRY),
        )

        frappe.db.sql(
            """
            UPDATE `tabPayment Ledger Entry`
            SET branch = %s
            WHERE voucher_type = 'Journal Entry'
              AND voucher_no = %s
              AND delinked = 0
              AND IFNULL(branch, '') = ''
            """,
            (TARGET_BRANCH, JOURNAL_ENTRY),
        )

        after_gl = capture_gl(JOURNAL_ENTRY)
        after_ple = capture_payment_ledger(JOURNAL_ENTRY)

        failures = []
        failures.extend(
            validate_unchanged(
                before_gl,
                after_gl,
                "GL",
            )
        )
        failures.extend(
            validate_unchanged(
                before_ple,
                after_ple,
                "Payment Ledger",
            )
        )

        doc.reload()

        for row in doc.accounts:
            if row.meta.has_field("branch"):
                if row.branch != TARGET_BRANCH:
                    failures.append(
                        f"Journal Entry Account {row.name} "
                        f"has Branch {row.branch}."
                    )

        if failures:
            frappe.db.rollback()

            print("RESULT: FAIL — rolled back")

            for failure in failures:
                print("  -", failure)

            return {
                "status": "FAIL",
                "messages": failures,
            }

        frappe.db.commit()

        print(
            "RESULT: PASS — committed; "
            f"updated {source_updates} source locations"
        )
        print("After GL:", after_gl)
        print("After Payment Ledger:", after_ple)

        return {
            "status": "PASS",
            "messages": [],
        }

    except Exception as error:
        frappe.db.rollback()

        print("RESULT: ERROR — rolled back")
        print(type(error).__name__ + ":", str(error))

        return {
            "status": "ERROR",
            "messages": [str(error)],
        }