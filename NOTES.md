# Task 1 notes: PDF failure modes, text-layer detection, scanned support

## Possible failures when processing PDF files, and how this script handles them

| Failure | Handling |
|---|---|
| **No text layer (scanned/photographed form)** | `has_usable_text_layer()` checks `page.chars` count and looks for known form labels ("gross rents", "rental real estate") in the extracted text. If either check fails, the page is skipped with a warning instead of silently returning zeros. See "Scanned PDF support" below for what OCR fallback would look like. |
| **Values stored in form fields, not page text** | Handled. On the IRS's own *fillable* 8825 the page content stream holds only the blank template — every entry lives in an AcroForm field annotation, so `page.extract_text()` returns a pristine empty form and a text-only extractor reports zero properties without erroring. `_annotation_words()` reads each filled widget's `/V` and gives it the geometry of its rectangle, so field values and printed values join one word list and share a single code path. |
| **Encrypted / password-protected PDF** | Handled: `extract_pdf()` wraps `pdfplumber.open()` and re-raises as `ExtractionError`. The CLI prints `ERROR: could not open ... ` and exits 2; the API turns it into a 400 rather than a 500, since an unopenable upload is the caller's problem. |
| **Corrupted / truncated file** | Same path — pdfminer raises on malformed PDF structure and it surfaces as the same `ExtractionError`. |
| **Wrong form entirely (not an 8825)** | Caught by the same `has_usable_text_layer()` label check — a page with real text but none of the 8825's known labels is treated as "no usable layer" and skipped, rather than producing a bogus all-zero property. |
| **Blank form** | A form with a readable layout but nothing filled in extracts zero properties, which is correct but indistinguishable from a failure at a glance, so it now emits an explicit "no properties found" warning. |
| **Layout drift between form revisions** | Handled. Between Rev. 11-2018 and the client's Rev. 12-2025 file the line-number anchor column moves from x≈317 to x≈282 and the property headers from x≈354-548 to x≈321-543, so any hardcoded x-band works on one revision and finds nothing on the other. Nothing is hardcoded — `_find_column_headers()` picks the row holding the most property letters, and `_find_anchor_column()` takes the rightmost cluster of right-aligned line numbers left of those headers. Rows are matched on vertical *centre* rather than top edge, because a field widget and the line number printed beside it share a row without sharing a baseline. The same applies to the address cell: its right edge comes from the vertical rule the form draws between columns (a) and (b), because the (b) cells begin ~40pt left of their own centred header and a fixed cutoff appends the property type code to the street address. Both form revisions are kept as fixtures so a future revision can't quietly break one while the other passes. |
| **Numbers formatted inconsistently** | Handled: `_parse_amount()` strips commas and treats a leading `(` as a minus sign (IRS accounting-negative convention), regardless of whether digits have thousands separators. |
| **Row text wraps onto a second line** (e.g. lines 2c, 18, 19, whose descriptions are long enough to wrap) | Handled by anchoring on the *reprinted* line-number token that sits just left of the value columns and lands on the same row as the number, rather than the paragraph's first line. |
| **Multi-page property lists** | Handled: each page is read independently and merged by property letter, so properties split across page 1 / page 2 (or a continuation page) combine correctly. On the Rev. 12-2025 continuation page the column letters are themselves typed into fields rather than printed, which works for free because field values are treated as words. Verified against a page-2 copy of the real form. |
| **OCR misreads on scanned input** (once implemented) | Would need value sanity checks — e.g. a line item that OCRs to non-numeric text, or a total that doesn't reconcile (2a+2b != 2c) — surfaced as a warning rather than accepted as-is. The extractor already does this reconciliation check for PDF-reported totals; the same check would catch OCR noise. |

## How the script determines whether a PDF has a usable text layer

`has_usable_text_layer(page)` in [form8825/extract.py](form8825/extract.py):
1. `len(page.chars) < 10` → treated as no text layer at all (a scanned image page comes back with ~0 chars from pdfplumber, since there's nothing for pdfminer to decode).
2. Otherwise, extract the page text and check it contains both `"gross rents"` and `"rental real estate"` (case-insensitive) — labels specific to this form. This catches the case where a page *does* have real text (so check 1 passes) but it isn't actually an 8825 page, e.g. a cover letter or a different form mixed into the same PDF.

Both checks must pass for the page to be processed; otherwise it's skipped and a warning is emitted rather than the page contributing bogus zero-valued data.

Note that this check deliberately looks at the *template* text and not at the taxpayer's numbers. On a fillable 8825 the numbers aren't in the text layer at all, so a check that required them would reject a perfectly readable form. What the check is really asking is "can I find the row and column anchors on this page", and those are printed.

## What's skipped today when there's no usable text layer

The page is simply excluded from extraction, with a warning printed to stderr. No OCR fallback is implemented.

## What would change to support scanned input

1. **Detect** the same way (`has_usable_text_layer` already does this).
2. **Add an OCR step** before extraction, one of:
   - `ocrmypdf` to add an invisible, positioned text layer to the scanned PDF, then run the *exact same* `pdfplumber`-based extraction unchanged — this is the least invasive option since none of the row/column logic needs to know OCR happened.
   - `pytesseract` directly on page images (`page.to_image()` / `pdf2image`) to get word boxes, then feed those boxes into the same `_read_layout` / `_assign_column` logic, since it already works purely off `(text, top, x0, x1)` tuples — the code doesn't care whether those came from pdfminer or Tesseract.
3. **Lower confidence handling**: OCR introduces misreads (e.g. "0" vs "O", digit transpositions). Would add: (a) reconciliation checks already in place (2a+2b vs 2c, sum of expenses vs 18) surfaced as hard warnings/errors rather than informational, since an OCR'd form is more likely to be wrong; (b) per-word OCR confidence scores (Tesseract provides these) to flag low-confidence numeric cells for manual review instead of trusting them outright — this maps directly onto Task 3's manual-correction UI, i.e. OCR'd low-confidence values would be extracted but pre-flagged as "needs review."
4. Tesseract is not installed on this machine, so this path is designed but not implemented, per the task's guidance that scanned-PDF support is optional.
