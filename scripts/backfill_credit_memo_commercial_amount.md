# Correct Credit Memo amounts

From the app root, run `./run_local_cm_correction --preview` to preview or
`./run_local_cm_correction` to apply on ams.localhost. The launcher prints the
path of its JSON audit under the site's private files.

Across all Sales Order dates, the script selects submitted linked Credit Memos
where Sponsored Amount and Commercial Amount are both zero and hidden Amount is
positive. It copies Amount into Sponsored Amount and sets Commercial Amount to
the linked Sales Order grand total minus Sponsored Amount. It records the original
values before writing, updates the two parent fields directly, verifies the
results, and commits the batch together.
