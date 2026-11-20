# Manual sales order branch correction

From the app root, run `./run_local_so_branch_reassignment --preview` for a preview or
`./run_local_so_branch_reassignment` to apply. The launcher prints the audit path.

Scope and behavior:

- All dates, draft and submitted orders; cancelled orders are excluded.
- SO-023593 and SO-023584 → Makati.
- `custom_for_branch` (the actual For Branch field) = Makati → Makati.
- Exact customer CARDMASTERS CEBU → Cebu.
- Exact customer CARDMASTERS MAKATI → Makati.
- Conflicting rules block the entire apply; missing or cancelled explicitly named orders also block it.
- Both header and item branches are updated. Company, timestamps, invoices, accounting entries, and other fields are untouched. Document hooks are deliberately bypassed.
- The JSON stores the old header and item branches before any updates. All updates commit together; an error before commit rolls them back. Preserve this file for auditing or a separately reviewed reversal. If execution fails after commit, inspect the database before retrying; the prepared audit file still contains the before-images.
- Already-correct orders are skipped.
- Orders below 100% billed receive `future_invoice_attention: true`. This flag does not block apply. New invoices can inherit the corrected branch: explicitly set their header and item accounting branches to CDO if required before submitting them. This script does not install future invoice automation.
- For CARDMASTERS R&D, exactly one submitted linked Credit Memo is expected. Its `commercial_amount` is compared exactly to the order `grand_total`; mismatches, absent submitted memos, and multiple submitted memos are flagged. Draft/cancelled memos are listed for context but not treated as authoritative. No amounts are changed. R&D flags do not block branch corrections; R&D orders can still qualify for a branch correction through another rule.
- Reports reading sales order branches will reflect the corrections. Reports using company alone will not separate the branches. Existing invoices/accounting retain their own values.

After applying, review the JSON status, refresh branch reports, and spot-check the affected orders and their linked invoices. This script verifies branch writes, but does not independently snapshot and compare all linked accounting documents.
