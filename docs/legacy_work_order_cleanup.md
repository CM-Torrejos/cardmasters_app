# Legacy Work Order cleanup

From the production bench directory, after deploying this version of `cardmasters_app`:

```bash
bench --site YOUR_SITE execute cardmasters_app.maintenance.legacy_work_orders.run --kwargs '{"apply": 1}'
```

The command returns a JSON report with completed orders, skipped orders and reasons, and failures. To save it, append `> legacy-cleanup-report.json`.

Live progress prints immediately to stderr: mode, number of candidate Sales Orders, current order, cancellation/deletion steps, committed results, skip reasons, failures, elapsed time, and final totals. Redirecting the JSON report with `>` keeps progress visible in the terminal. `COMMITTED` means that order's changes have been saved. To disable progress, add `"progress": 0` to the kwargs. A process already running the older code will keep its original silent behavior.

Preview without changes:

```bash
bench --site YOUR_SITE execute cardmasters_app.maintenance.legacy_work_orders.run
```

Apply to one Sales Order or a limited batch:

```bash
bench --site YOUR_SITE execute cardmasters_app.maintenance.legacy_work_orders.run --kwargs '{"apply": 1, "sales_order": "SO-000007"}'
bench --site YOUR_SITE execute cardmasters_app.maintenance.legacy_work_orders.run --kwargs '{"apply": 1, "limit": 10}'
```

Use numeric `1` for apply; this works with Bench versions that parse kwargs as Python expressions. `limit` counts eligible orders processed, not orders scanned. Run this as a standalone maintenance command; it manages its own transactions.

An order qualifies when:

- Its Sales Order is submitted and `per_billed >= 100`.
- All its Work Orders match `SO-[digits]_MFG[digits]`, and the SO prefix matches their linked Sales Order. Orders with a mix of legacy and other Work Orders are skipped.
- No Stock Entry in any status references any of its Work Orders or Job Cards. This checks standard and custom Link fields on Stock Entry and Stock Entry Detail, including the custom repack Work Order field.
- It has linked Delivery Notes, and all are drafts, are not returns, and contain only items from this Sales Order. Shared Delivery Notes are skipped to avoid deleting another order's deliveries.
- Draft Delivery Note items combined cover every SO item's full stock quantity. Coverage uses `so_detail`, so repeated item codes and different selling units do not mask missing quantities. Missing/mismatched item references and non-positive quantities are skipped. Overdelivery qualifies.

For each qualifying Sales Order, the command:

1. Cancels submitted Job Cards, then submitted Work Orders.
2. Deletes linked Job Cards, draft Work Orders, then cancelled Work Orders (including previously cancelled ones).
3. Deletes the linked draft Delivery Notes.
4. Closes the Sales Order using ERPNext's controller, updating reservations as usual.

Each successful Sales Order commits independently. A failure rolls back that order completely, clears pending transaction callbacks, records the error, and continues. Standard cancellation, workflow and link validations remain active; there are no force deletes. Stock Entry blockers skip the whole order before cancellation begins. Re-running the command leaves already processed orders alone because their Work Orders no longer exist. Closing changes the standard SO `status`; it does not assign a custom workflow state.

## Local validation

The command was applied successfully on local site `ams.localhost` for `SO-000007`, `SO-000008`, `SO-000010`, and `SO-000077`: eight Work Orders, four draft Delivery Notes, and one existing Job Card deleted, and all four Sales Orders closed.

A full preview after the first three sample cleanups scanned 5,250 Sales Orders: 4,830 eligible, 420 skipped, zero errors. It identified 6,831 eligible Work Orders, 4,932 draft Delivery Notes, and 79 Job Cards. The subsequent SO-000077 test removed one group from those eligible totals. Skips were 310 not submitted/fully invoiced, 48 with non-legacy Work Orders, 33 with incomplete delivery coverage, 18 with linked Stock Entries, eight without linked draft deliveries, and three with non-draft/return deliveries. The full local preview report is `/tmp/legacy-work-order-preview.json`.

The integration suite uses existing local eligible data, creates temporary fixtures, and rolls back its changes. Run only against the local test site:

```bash
bench --site ams.localhost execute cardmasters_app.maintenance.test_legacy_work_orders.run_tests
```

The checks cover combined deliveries, repeated item codes, invalid references, quantity gaps, name matching, preview behavior, submitted/shared deliveries, incomplete billing, Stock Entry blockers in all statuses and custom fields, Stock Entries linked through Job Cards, actual draft/submitted Job Card cleanup, and rollback after an injected failure following deletion and closing.
