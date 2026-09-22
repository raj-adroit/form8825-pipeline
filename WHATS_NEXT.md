# What's left / what I'd do next

Tasks 1-3 are complete and verified working end-to-end (extraction matches
both provided/generated fixtures exactly, full stack runs and edits persist
with an audit trail). Task 4 is bonus/optional per the assignment; the JSON
output validation half (items 1-2) is now implemented, the rest isn't. Here's
what it would take for what's left:

## Task 4 - tests (bonus)

1. **Extraction accuracy tests** - done, `tests/test_extraction.py`: for
   each fixture (`task_input_files/f8825.pdf` + `8825_output.json`, and
   `f8825_multi.pdf` / `f8825_multi_flat.pdf` + `f8825_multi_expected.json`),
   runs `extract_pdf()` and asserts the result equals the expected JSON
   exactly, both as a whole-property compare and field-by-field.
2. **Totals validation tests** - done, `tests/test_validation.py`: exercises
   `form8825/validate.py`'s three checks - 2c = 2a + 2b, line 18 = sum of
   expenses, line 19 = 2c - 18 - and the grand-total-net-income rollup
   against all fixtures, plus a deliberately-broken case per total to
   confirm each check actually fires. Run with `uv run python -m pytest -q`
   (72 tests, all passing as of this session).
3. **CSV test result file**: one row per (property, check) - e.g.
   `fixture_file, property_name, check_name, expected, actual, passed` -
   written by the pytest run (a session-scoped fixture that accumulates rows
   and writes the CSV on teardown, or a small `pytest` plugin hook). Not
   implemented; the tests above currently report pass/fail only via pytest's
   own output.
4. **UI test automation**: Playwright against the running frontend +
   backend. Minimum useful coverage: upload a fixture PDF, assert each
   property renders with the right totals; edit one line item, assert the
   total and grand total update and a history entry appears; delete a
   document, assert it leaves the list. `frontend/` has no test tooling
   installed yet - would add `@playwright/test` as a dev dependency.

## Scanned PDF / OCR support (optional, not implemented)

Design is written up in `NOTES.md`. Short version: `has_usable_text_layer()`
already detects the no-text-layer case and skips the page with a warning
instead of guessing. Adding real support means running `ocrmypdf` (or
`pytesseract` word boxes) before/instead of `pdfplumber.extract_words()` -
the row/column matching logic in `extract.py` only needs `(text, top, x0,
x1)` tuples, so it doesn't care whether they came from pdfminer or OCR.
The main new work would be confidence-flagging low-certainty OCR values so
they surface as "needs review" in the UI rather than being trusted
silently - which the existing `source: manual` / audit-log machinery in
Task 3 could carry without schema changes.

## Smaller things worth doing with more time

- Re-running extraction on an already-uploaded document (currently each
  upload creates a new `Document` row even for the same file; there's no
  "re-extract" action in the UI, though the DB schema already supports
  multiple `extraction_runs` per document).
- Basic auth/user identity for the `changed_by` field, currently a free-text
  string hardcoded to `"user"` in the frontend.
- Re-extracting a document after an extractor improvement (e.g. support for a
  new IRS revision): documents already ingested with an older extractor keep
  their line items as-is, and the only way to refresh them today is to
  re-upload. The `extraction_runs`
  table is already shaped for it - what's missing is a
  `POST /api/documents/{id}/reextract` and somewhere to keep the original
  upload, since the API currently extracts from a temp file and discards it.
