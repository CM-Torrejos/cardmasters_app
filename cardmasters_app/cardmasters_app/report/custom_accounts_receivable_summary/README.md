# Custom Accounts Receivable Summary

A separate customer summary report based on ERPNext's standard Accounts
Receivable Summary. The existing Custom Accounts Receivable detail report is
retained.

Use **Show Ageing Buckets** to keep only customers with a non-zero net balance
in at least one selected bucket. With the default ranges, select **31-60**,
**61-90**, **91-120**, and **121+** to exclude customers whose balances are only
in 0-30 days. Leave the selector empty for the standard summary.

Filtering happens after customer balances are aggregated. Matching customers
retain all their standard summary amounts, including other ageing buckets,
advances, outstanding amounts, and optional GL/future-payment columns. Totals
and exports include only the retained customer rows. Credit balances qualify;
amounts that round to zero at the report's currency precision do not.

Changing Ageing Range clears the bucket selection. Column visibility remains
separate from filtering. The detail button opens Custom Accounts Receivable;
its bucket filter works on individual entries and is selected separately.

Activate through the normal app deployment and `bench --site <site> migrate`,
then reload Desk and search for **Custom Accounts Receivable Summary**.

Run tests in a configured bench:

```
bench --site <site> run-tests --app cardmasters_app --module cardmasters_app.cardmasters_app.report.custom_accounts_receivable_summary.test_custom_accounts_receivable_summary
```
