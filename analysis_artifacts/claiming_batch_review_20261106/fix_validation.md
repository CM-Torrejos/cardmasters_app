# Amendment batch fix

Added `restore_material_request_batch_on_amendment` to Stock Entry `before_validate` so it runs on draft save and direct submission, before ERPNext can create an automatic FIFO bundle.

Scope: amended Material Issue / Material Transfer entries with Material Request-linked batch-managed items and no explicit batch or bundle. The handler reuses the creation mapper's Material Request batch resolver, verifies the request item belongs to the request and item code, and verifies the resolved Batch belongs to the item. It sets the batch and enables serial/batch fields. It leaves quantities, warehouses, and explicit batch/bundle selections intact. Missing or invalid resolution blocks saving with a request to explicitly select the intended batch. ERPNext retains responsibility for availability and posting-date validation.

This restores the request's intended batch; it does not blindly copy the immediately preceding entry's allocation, which could already be an erroneous FIFO allocation. It does not change submitted historical records or handle unrelated non-request-linked amendments.

Validation:
- 15 focused unit tests passed: amendment handling, Material Request creation mapper, and Stock Entry reason-account regression tests.
- In-memory direct-submit simulation against all 10 cancelled originals restored all 25 original batch assignments, checked against Version history, including repeated item codes. No documents saved; database connection rolled back afterward.
- `git diff --check` passed.

Production has not been deployed. Existing incorrect stock postings still require a separately reviewed data correction.
