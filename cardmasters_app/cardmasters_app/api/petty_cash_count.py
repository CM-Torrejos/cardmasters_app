import frappe

@frappe.whitelist()
def get_unliquidated_transactions(petty_cash_count):
    """
    Return Purchase Orders where the Supplier is a disbursement officer
    (custom_is_disbursement_officer == 1) and which have no linked Purchase Invoices.
    """
    query = """
        SELECT
            po.name AS purchase_order,
            GROUP_CONCAT(DISTINCT poi.material_request SEPARATOR ', ') AS material_request,
            po.custom_amount_released AS amount_released
        FROM `tabPurchase Order` po
        JOIN `tabSupplier` s
            ON s.name = po.supplier
        JOIN `tabPurchase Order Item` poi
            ON poi.parent = po.name
        LEFT JOIN `tabPurchase Invoice Item` pii
            ON pii.purchase_order = po.name
        WHERE s.custom_is_disbursement_officer = 1
          AND po.docstatus = 1
          AND pii.name IS NULL
        GROUP BY po.name, po.custom_amount_released
    """
    try:
        return frappe.db.sql(query, as_dict=True)
    except Exception as e:
        frappe.log_error(f"Error fetching unliquidated transactions: {e}", "get_unliquidated_transactions")
        return []

@frappe.whitelist()
def get_liquidated_transactions(petty_cash_count):
    """
    Return Purchase Invoices on the Petty Cash Count date where the Supplier
    is a disbursement officer (custom_is_disbursement_officer == 1).
    """
    try:
        pcc = frappe.get_doc('Petty Cash Count', petty_cash_count)
        count_date = pcc.date
    except Exception as e:
        frappe.log_error(f"Invalid Petty Cash Count: {petty_cash_count} - {e}", "get_liquidated_transactions")
        return []

    query = """
        SELECT
            pi.name AS purchase_invoice,
            pii.purchase_order AS purchase_order,
            pii.purchase_receipt AS purchase_receipt,
            GROUP_CONCAT(DISTINCT pii.material_request SEPARATOR ', ') AS material_request,
            pi.grand_total AS amount_paid,
            pi.outstanding_amount AS outstanding_amount
        FROM `tabPurchase Invoice` pi
        JOIN `tabSupplier` s
            ON s.name = pi.supplier
        JOIN `tabPurchase Invoice Item` pii
            ON pii.parent = pi.name
        WHERE s.custom_is_disbursement_officer = 1
          AND pi.docstatus = 1
          AND pi.posting_date = %(count_date)s
        GROUP BY pi.name, pii.purchase_order, pii.purchase_receipt, pi.grand_total

        SELECT
            pi.name AS purchase_invoice,
            GROUP_CONCAT(DISTINCT pii.purchase_order     SEPARATOR ', ') AS purchase_order,
            GROUP_CONCAT(DISTINCT pii.purchase_receipt   SEPARATOR ', ') AS purchase_receipt,
            GROUP_CONCAT(DISTINCT pii.material_request   SEPARATOR ', ') AS material_request,
            MAX(pi.grand_total)        AS amount_paid,
            MAX(pi.outstanding_amount) AS outstanding_amount
        FROM `tabPurchase Invoice` pi
        JOIN `tabSupplier` s
            ON s.name = pi.supplier
        JOIN `tabPurchase Invoice Item` pii
            ON pii.parent = pi.name
        WHERE s.custom_is_disbursement_officer = 1
            AND pi.docstatus = 1
            AND pi.posting_date = %(count_date)s
        GROUP BY pi.name;

    """
    try:
        return frappe.db.sql(query, values={"count_date": count_date}, as_dict=True)
    except Exception as e:
        frappe.log_error(f"Error fetching liquidated transactions: {e}", "get_liquidated_transactions")
        return []
