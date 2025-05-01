import frappe;


@frappe.whitelist()
def get_liquidated_transactions(petty_cash_count=None):
	print("Server is executing for liquidated")
	results = []

	try:
		if not petty_cash_count:
			print(f"Invalid petty_cash_count: {petty_cash_count}")
			frappe.response['message'] = results
			return

		query = """
			SELECT
				pcr.name AS request,
				v.name AS voucher_name,
				pi.name AS invoice_name,
				v.total_amount_released
			FROM
				`tabPetty Cash Request` pcr
			INNER JOIN
				`tabPurchase Invoice` pi ON pi.custom_petty_cash_request = pcr.name
			INNER JOIN
				`tabPetty Cash Voucher` v ON v.petty_cash_request = pcr.name
			WHERE
				pcr.petty_cash_count = %s
		"""
		results = frappe.db.sql(query, values=[petty_cash_count], as_dict=True)
		print(f"Total results fetched: {len(results)}")

		frappe.response['message'] = results

	except Exception as e:
		print(f"Error in get_liquidated_transactions: {str(e)}")
		frappe.response['message'] = []

@frappe.whitelist()
def get_unliquidated_transactions():
	print("Server is executing for unliquidated")
	try:
		print("Script is running!")

		# One SQL query
		query = """
			SELECT
				pcr.name AS request,
				v.name AS voucher_name,
				v.total_amount_released
			FROM
				`tabPetty Cash Request` pcr
			LEFT JOIN
				`tabPurchase Invoice` pi ON pi.custom_petty_cash_request = pcr.name
			INNER JOIN
				`tabPetty Cash Voucher` v ON v.petty_cash_request = pcr.name
			WHERE
				pi.name IS NULL
		"""
		results = frappe.db.sql(query, as_dict=True)

		print(f"Total unliquidated transactions: {len(results)}")
		frappe.response['message'] = results

	except Exception as e:
		frappe.log_error(f"get_unliquidated_transactions error: {str(e)}")
		frappe.response['message'] = []

