# Custom Accounts Receivable

Uses ERPNext's Accounts Receivable ledger calculation and permissions, with a
server-side **Show Ageing Buckets** filter. Leave it empty for the standard data,
or select one or more buckets to include only entries with a non-zero balance
in at least one selected bucket. For balances older than 30 days with the default
ranges, select **31-60**, **61-90**, **91-120**, and **121+**.

The filter applies to invoice/payment-term rows before customer subtotals and
charts are calculated. A customer with no matching entries disappears; a
customer with mixed ages retains only matching entries. Credits in selected
buckets remain included. Not-yet-due entries have no ageing bucket balance and
are excluded when selecting buckets. Column visibility alone does not filter
data. Exported data uses the same server-side filtering.

The Ageing Based On and Calculate Ageing With options retain their standard
meaning. Changing Ageing Range clears the selected buckets to avoid applying
stale boundaries. The Summary button opens ERPNext's standard summary report,
which does not support this custom filter.

Deploy with the normal app update and `bench --site <site> migrate`, then reload
Desk and search for **Custom Accounts Receivable**. No ledger data is modified.

Tests (from a configured bench):

```
bench --site <site> run-tests --app cardmasters_app --module cardmasters_app.cardmasters_app.report.custom_accounts_receivable.test_custom_accounts_receivable
```
