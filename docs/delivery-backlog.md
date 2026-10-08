# Delivery Note backlog

On a submitted Sales Order, System Managers can use **Actions → Submit Delivery Backlog**, choose draft Delivery Notes, and choose a target month. The selected month defaults to the selected note's posting month. New stock entries and selected Delivery Notes post on the first day at midnight.

The server enforces the System Manager role and normal document permissions, workflow transitions, manufacturing validations, and stock/accounting validations. Each selected note must belong entirely to the Sales Order, customer, and company. The action sets Production Branch to Cagayan de Oro and fills an empty Payment Method from submitted advance Payment Entries: Acknowledgement Receipt → Cash; Collection Receipt → Credit. Missing, unsupported, or conflicting receipt types require a manual payment choice.

Work Orders are matched by Sales Order item row. Missing orders use the active default company BOM. Inactive BOM orders are cancelled and amended only when they have no non-cancelled stock entries. Multiple matching orders, unlinked legacy orders, existing draft stock entries, product bundles, and serialized or unbatched stock items require manual resolution.

Available batch stock at the chosen posting time is reused. Only the shortage is manufactured, within the Work Order's remaining quantity. Work Orders with Skip Material Transfer manufacture directly; others transfer the missing quantity from the configured Cagayan de Oro source warehouse into its WIP warehouse first. BOM items and normal valuation remain in force. The action adds audit comments and submits the selected Delivery Notes.

After stock preparation and before Delivery Note submission, each involved Work Order advances through the active workflow: Not Started → In Production → Pending Consumption → Pending Claiming → In Claiming. Existing Work Orders continue from their current state, including when available batch stock covers the delivery and no new manufacture entry is needed. Work Orders already In Claiming remain there. The action uses normal workflow transitions and records workflow comments; it does not directly set workflow state or bypass role checks. The acting System Manager must also have the roles required by those transitions. Missing workflows, unsupported states, blocked conditions, or ambiguous actions fail and roll back the entire backlog action.

All document changes roll back if any step fails. A repeated submission rejects already submitted notes. Existing submitted entries are never cancelled or reposted to another month.

Item Specifics and Particulars retain Allow on Submit = 0. The System Manager action applies the existing surrounding-whitespace cleanup through targeted server-side child updates and updates Payment Method and Production Branch through targeted header updates. It records an additional comment identifying cleaned rows. It never changes metadata or exposes ordinary editing of submitted item fields.

Deployment: clear the site cache to load the new client hook.

Validation: eleven unit tests cover role enforcement, payment inference, ambiguous/default BOM handling, targeted updates without unlocking fields, failure rollback, forward workflow advancement from each supported state, duplicate role transitions, blocked/ambiguous transitions, missing workflows, unsupported states, and advancement before delivery submission when existing stock covers demand. The rollback smoke helper in `api/test_delivery_backlog.py` runs real controllers on a restored local site, verifies that item descriptions receive only whitespace cleanup, and checks that a second submission creates no additional stock entries; it always rolls back the transaction.
