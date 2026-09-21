# Extraction logic (`form8825/`)

How a Form 8825 PDF becomes structured JSON. This covers every file in the
`form8825/` package, the algorithm in `extract.py` in depth, and the test
fixtures that pin its behaviour.

- [Package map](#package-map)
- [Output contract](#output-contract)
- [The two shapes of a Form 8825 PDF](#the-two-shapes-of-a-form-8825-pdf)
- [Pipeline at a glance](#pipeline-at-a-glance)
- [Algorithm step by step](#algorithm-step-by-step)
- [Constants and tolerances](#constants-and-tolerances)
- [Worked example](#worked-example)
- [Multi-page and multi-property handling](#multi-page-and-multi-property-handling)
- [Totals: computed, then cross-checked](#totals-computed-then-cross-checked)
- [Errors vs warnings](#errors-vs-warnings)
- [`validate.py`](#validatepy)
- [`cli.py`](#clipy)
- [Test fixtures (`testdata/`)](#test-fixtures-testdata)
- [Adapting to a new form revision](#adapting-to-a-new-form-revision)
- [Known limitations](#known-limitations)

---

## Package map

```
form8825/
  __init__.py   package marker
  schema.py     the vocabulary: which form line maps to which JSON key
  extract.py    the extractor: PDF -> list of property dicts + warnings
  validate.py   arithmetic rules over the extractor's output (or edited data)
  cli.py        command-line wrapper: extract + validate + print/write JSON
```

Dependency direction is one-way. `form8825/` is a standalone library and
knows nothing about `backend/`. The backend imports `extract_pdf` and the
key lists from it; the CLI imports `extract` and `validate`.

```
cli.py ──► extract.py ──► schema.py
   └────► validate.py
backend/crud.py ──► extract.py, schema.py
```

### `schema.py`: the vocabulary

Everything else is driven by these constants, so the extractor never
hardcodes a line number.

| Constant | Meaning |
|---|---|
| `LINE_ITEM_MAP` | `{line_code: (section, json_key)}` for every line that has a per-property dollar value. 15 entries: `2a`, `2b` (income) and `3`–`14`, `17` (expense). |
| `TOTAL_LINE_CODES` | `{"total_income": "2c", "total_expenses": "18", "net_income": "19"}`. The form's own printed totals. Used **only** for cross-checking. |
| `INCOME_KEYS` / `EXPENSE_KEYS` | Ordered JSON keys derived from `LINE_ITEM_MAP` (2 income, 13 expense). The backend also iterates these when it writes rows. |
| `PROPERTY_LETTERS` | `["A", "B", "C", "D"]`. The form has room for four properties per page. |

Lines 15 and 16 are "Reserved for future use" on the form and are
deliberately absent. Line 1 (address/type) is handled separately as the
property address.

Mapping, for reference:

| Line | JSON key | Section |
|---|---|---|
| 2a | `gross_rents` | income |
| 2b | `other_income` | income |
| 3 | `advertising` | expense |
| 4 | `auto_travel` | expense |
| 5 | `cleaning_maintenance` | expense |
| 6 | `commissions` | expense |
| 7 | `insurance` | expense |
| 8 | `interest` | expense |
| 9 | `legal_professional` | expense |
| 10 | `real_estate_taxes` | expense |
| 11 | `repairs` | expense |
| 12 | `utilities` | expense |
| 13 | `wages_salaries` | expense |
| 14 | `depreciation` | expense |
| 17 | `other_deductions` | expense |

`frontend/src/labels.ts` mirrors this table by hand. See
[FRONTEND_LOGIC.md](FRONTEND_LOGIC.md).

---

## Output contract

`extract_pdf(path)` returns `(properties, warnings)`.

Each property is a plain dict, identical to `task_input_files/8825_output.json`:

```json
{
  "property_name": "A",
  "property_address": "123 lake ave",
  "income_line_items":  { "gross_rents": 182400, "other_income": 1200 },
  "expense_line_items": { "advertising": 0, "auto_travel": 1450, "...": 0 },
  "totals": {
    "total_rental_income": 183600,
    "total_expenses": 114500,
    "net_income": 69100
  }
}
```

Guarantees:

- Every property has **all** 2 income and 13 expense keys. A blank cell is `0`, never missing.
- Amounts are `int` (rounded), negative when the form shows `(1,234)` or `-1234`.
- Properties are ordered by letter (`A`, `B`, ...), not by page position.
- `totals` are **computed** from the line items, not copied from the form.
- `property_name` is the column letter, not a name read from the form.

`warnings` is a list of `ExtractionWarning(property_letter, message)`.
`property_letter` is `None` for document-level warnings.

---

## The two shapes of a Form 8825 PDF

Both occur in practice, and the extractor handles both through one code path.

| | Flattened / printed | Fillable (the IRS's own PDF) |
|---|---|---|
| Where the taxpayer's numbers live | Drawn into the page content stream | In AcroForm widget annotations (`/V`) |
| `page.extract_words()` returns | The numbers | Only the blank template |
| Failure if handled naively | none | Silently extracts a blank form, with no error |

For fillable PDFs `_annotation_words()` reads each filled widget's value and
gives it the geometry of the widget rectangle. Those word-shaped dicts are
appended to the printed words, so everything downstream sees one list of
`{text, x0, x1, top, bottom}` and needs no special case.

This also makes the Rev. 12-2025 continuation page work: there, even the
property letters (A/B/C/D) are typed into fields rather than printed, so they
only become locatable column headers via the annotation words.

---

## Pipeline at a glance

```
PDF
 │  pdfplumber.open()                      fails ──► ExtractionError
 ▼
for each page:
 │  has_usable_text_layer?                 no ──► warning, skip page
 ▼
 words = extract_words() + _annotation_words()
 │
 ├─ _find_column_headers   → {A: x0, B: x0, ...}
 ├─ _find_anchor_column    → the reprinted line-number column
 ├─ _read_layout           → PageLayout(row_centers, column_x0, total_centers, value_x_min)
 ├─ _extract_page_values   → values[letter][code], totals[letter][code]
 └─ _extract_page_addresses→ addresses[letter]
 │
 ▼  merge pages by property letter
 ▼
for each property letter (sorted):
   fill 15 line items (default 0)
   compute 2c / 18 / 19
   compare with the form's printed totals → warning on mismatch
   emit dict
```

---

## Algorithm step by step

### 0. Is this page readable? (`has_usable_text_layer`)

Two checks, both must pass:

1. `len(page.chars) >= 10`. A scanned page has ~0 characters.
2. The extracted text (lower-cased) contains both `"gross rents"` and `"rental real estate"`. This rejects pages that have text but are not an 8825 (a cover letter, a different form).

It intentionally inspects the **template** text, not the taxpayer's numbers.
On a fillable PDF the numbers are not in the text layer at all, so requiring
them would reject a perfectly good form. The real question is "can I find the
row and column anchors", and those are printed.

A failing page produces a warning and is skipped. The rest of the document is
still processed.

### 1. Gather words (`_page_words`, `_annotation_words`)

`page.extract_words()` plus one synthetic word per filled form field.
`_annotation_words` handles:

- byte values (decoded as UTF-8, `errors="replace"`)
- whitespace inside values (`" ".join(value.split())`)
- non-string `/V` (checkbox states) and empty strings, which are skipped

### 2. Find the column headers (`_find_column_headers`)

The property columns are headed A/B/C/D.

1. Candidates: words whose text is a property letter **and** `x0 > HEADER_MIN_X0` (250). The letters also appear in the far-left row labels, and this keeps those out.
2. Group candidates into rows by vertical centre (`ROW_TOLERANCE`).
3. Pick the row with the most **distinct** letters. Ties go to the topmost row.
4. Return `{letter: x0}`.

"Most distinct letters" is what stops a stray `A` elsewhere on the page,
for example "Schedule A (Form 8825)" on line 17, from being mistaken for a
header.

If no header row exists the page has no property columns and
`_read_layout` returns an empty layout. Nothing is attributed, no error.

### 3. Find the row anchors (`_find_anchor_column`)

**Why anchors.** Every line number (2a, 2b, 3–14, 17, plus 2c/18/19) is
printed a *second* time in a narrow column immediately left of the value
columns, on the same text row as the dollar amount. That reprint is a better
row marker than the line's label, because long labels ("Total rental real
estate expenses for each property. Add lines...") wrap onto a second line
and only that second line sits level with the value.

**How.**

1. Candidates: words that are a known anchor code (`ANCHOR_CODES` = `LINE_ITEM_MAP` keys plus `2c/18/19`) with `x1 < min(header x0)`.
2. Sort by right edge `x1`; start a new cluster whenever the gap to the cluster's first word exceeds `ANCHOR_CLUSTER_WIDTH` (6pt). Right-aligned numbers share a right edge, so one column is one cluster.
3. Keep clusters with at least `MIN_ANCHOR_ROWS` (5) **distinct** codes.
4. Take the **rightmost** usable cluster. The same numbers also appear in the far-left label column, and the reprint is the one closest to the values.

Returns `[]` if nothing qualifies.

### 4. Build the page layout (`_read_layout`)

```python
PageLayout(
    row_centers   = {"2a": 312.4, "3": 336.0, ...},  # per-property lines
    column_x0     = {"A": 354.4, "B": 416.9, ...},
    total_centers = {"2c": 324.0, "18": 522.0, "19": 537.0},
    value_x_min   = max(anchor.x1),  # values must start right of this
)
```

Anchors are split by code: `LINE_ITEM_MAP` codes go to `row_centers`, the
rest to `total_centers`. Row position is the **vertical centre**
`(top + bottom) / 2`, not the top edge, because a form-field widget and the
printed line number beside it share a row but not a baseline.

**Nothing is hardcoded**, because the IRS moves these between revisions:

| Revision | Anchor column x | Header x range |
|---|---|---|
| Rev. 11-2018 | ~317 | ~354-548 |
| Rev. 12-2025 | ~282 | ~321-543 |

### 5. Assign values to (line, property) (`_extract_page_values`)

1. Keep words that match `NUMBER_RE` (`^[-(]?[\d,]+(?:\.\d+)?\)?$`) **and** have `x0 > value_x_min`. That drops labels and anything left of the value columns.
2. For each anchored row, take every kept word whose vertical centre is within `ROW_TOLERANCE` (4pt) of the row centre.
3. Decide which property each belongs to by its **right edge** (`x1`). Values are right-aligned, so the right edge sits inside its own column, and the left edge does not reliably.
4. `_parse_amount` converts text to `int`.

Column boundaries (`_column_boundaries`, `_assign_column`):

- Sort headers left to right. Column *i* spans `[x0_i, x0_{i+1})`.
- The **last** column has no next header, so it borrows the spacing of the previous pair: `right = x0_last + (x0_last - x0_prev)`.
- If it is the **only** column there is no spacing to borrow and nothing to its right to confuse it with, so it runs to `+inf`.
- A value matches when `left - 10 <= x1 < right`. The 10pt slack on the left tolerates a right-aligned value whose edge sits slightly under the header's own x0.

The function runs twice with the same machinery: once over `row_centers`
(line items) and once over `total_centers` (printed totals for the
cross-check).

`_parse_amount` rules:

| Text | Result |
|---|---|
| `"182,400"` | `182400` |
| `"(1,234)"` | `-1234` |
| `"-1234"` | `-1234` |
| `"12.6"` | `13` (rounded) |
| unparseable | `0` |

### 6. Read addresses (`_address_column_x1`, `_extract_page_addresses`)

Line 1 lists each property: row letter, then (a) physical address, then type
and other columns.

**Right edge of the address cell.** A fixed cutoff does not work, and
neither does reading it off the "(b)" header: the header is centred over its
column while the cells under it start much further left (on Rev. 12-2025,
header "(b)" is at x=243 but its cells begin at x=202). A cutoff right of 202
would append the property-type code to the street address. So:

1. Find the `(b)` header word.
2. Among the page's vertical rules (`page.vertical_edges`) with `45 < x0 <= header_b.x0`, take the rightmost. That is the real boundary the form draws.
3. No rule or no header: fall back to `ADDRESS_COLUMN_X1_FALLBACK` (236).

**Which words belong to which property.**

- A row letter is a property letter with `x0 < 45`, `top > 100`, and a vertical centre above the first value row (so line-item labels further down are excluded).
- For each row letter, gather words with `45 <= x0 < address_x1` and `letter.top - 15 <= word.top <= letter.top + 3`.
- Sort by `(top, x0)` and join with spaces. The window allows an address that wraps to a second line.

### 7. Merge pages and build the result

See [Multi-page and multi-property handling](#multi-page-and-multi-property-handling)
and [Totals](#totals-computed-then-cross-checked).

---

## Constants and tolerances

All at the top of `extract.py`. These are the first things to adjust if a
new form revision stops extracting correctly.

| Constant | Value | What it controls |
|---|---|---|
| `ROW_TOLERANCE` | 4.0pt | Max vertical-centre distance for two words to count as the same row. Used for header rows and for value-to-anchor matching. |
| `HEADER_MIN_X0` | 250.0 | Property-letter headers must be right of this, to exclude row letters and labels. |
| `ADDRESS_COLUMN_X0` | 45.0 | Left edge of the address column, right of the A/B/C/D row letters. |
| `ADDRESS_COLUMN_X1_FALLBACK` | 236.0 | Address right edge when the form draws no column rule. |
| `ANCHOR_CLUSTER_WIDTH` | 6.0pt | Max spread of right edges that still counts as one anchor column. |
| `MIN_ANCHOR_ROWS` | 5 | Distinct line numbers a cluster needs to be called the anchor column. |
| left slack in `_assign_column` | 10pt | How far left of a header a value's right edge may fall. Inline, not a named constant. |

---

## Worked example

The flattened fixture (`f8825_multi_flat.pdf`, Rev. 11-2018 geometry) has
three populated columns and no D.

```
headers (x0):     A = 354.4     B = 416.9     C = 479.4
bounds:           A [354.4, 416.9)  B [416.9, 479.4)  C [479.4, 541.9)
                                                         └ borrows the 62.5 spacing
value right edge: 385.9 (A)     448.4 (B)     510.9 (C)      = x0 + 31.5
```

For `2a` (gross rents), suppose the anchor `"2a"` has a vertical centre of
`Y` (about 284 on this fixture; the exact figure is read off the page). The
extractor looks at every number word within 4pt of `Y` and right of the
anchor column:

| Word | x1 | Falls in | Result |
|---|---|---|---|
| `182,400` | 385.9 | A | `values["A"]["2a"] = 182400` |
| `96,000` | 448.4 | B | `values["B"]["2a"] = 96000` |
| `310,500` | 510.9 | C | `values["C"]["2a"] = 310500` |

A zero is drawn as **nothing** on the form. Properties with no word on a row
simply have no entry, and step 7 fills the gap with `0`.

---

## Multi-page and multi-property handling

Each page is read independently, then merged by property letter:

```python
for letter, line_values in page_values.items():
    if not line_values and not page_addresses.get(letter):
        continue                                   # nothing for this letter here
    if letter not in merged_values:
        property_order.append(letter)              # first sighting
    merged_values.setdefault(letter, {}).update(line_values)
    merged_totals.setdefault(letter, {}).update(page_totals.get(letter, {}))
```

- A property split across a page 1 / continuation page combines by letter.
- If two pages supply the same `(letter, line)`, the **later page wins** (`dict.update`).
- A letter with an address but all-zero values still yields a property.
- A letter with neither values nor an address is dropped, which is how an unused column D disappears.
- If no property is found anywhere, a document-level warning is emitted: `"no properties found; the form appears to be blank, or its layout isn't one this extractor recognises"`.

---

## Totals: computed, then cross-checked

```
total_income   = gross_rents + other_income          (line 2c = 2a + 2b)
total_expenses = sum(all 13 expense items)           (line 18)
net_income     = total_income - total_expenses       (line 19 = 2c - 18)
```

These are calculated from the extracted line items, never copied from the
form. The form's own printed 2c / 18 / 19 are read (via `total_centers`) and
compared. A mismatch adds a warning and does not change the output:

```
WARNING [property B]: total expenses: computed 87510 but form prints 87500 for line 18
```

(The figures are illustrative. The `WARNING [...]` prefix is the CLI's
formatting; the stored message is `total expenses: computed ... for line 18`.)

That makes the printed total an independent check on extraction accuracy: if
a digit was misread, the sum will not match what the taxpayer printed.

---

## Errors vs warnings

Only one condition raises. Everything that goes wrong *inside* a readable PDF
comes back as a warning, so one bad page never costs the rest of the document.

| Condition | Result |
|---|---|
| File can't be opened (corrupt, truncated, encrypted, not a PDF) | `ExtractionError` (pdfminer raises many unrelated exception types, all caught and re-raised with `from exc`) |
| Page has no usable text layer / not an 8825 | Warning `"page N has no usable text layer; skipped (would need OCR - see README notes)"` |
| No properties found | Document-level warning |
| Printed total ≠ computed total | Per-property warning |
| Amount text can't be parsed | Treated as `0` (no warning) |

How callers react:

- **CLI**: `ExtractionError` prints `ERROR: ...` and exits 2. Warnings print to stderr as `WARNING [property X]: ...` or `[document]`.
- **API**: `ExtractionError` becomes HTTP 400. Warnings are stored and returned with the document. See [BACKEND_LOGIC.md](BACKEND_LOGIC.md).

---

## `validate.py`

Pure functions over the output-JSON dict shape, so they can be reused on
extracted **or manually edited** data.

```python
validate_property(prop)   -> list[ValidationIssue]
validate_properties(list) -> (list[ValidationIssue], grand_total_net_income)
```

Rules checked per property:

1. `totals.total_rental_income == gross_rents + other_income`
2. `totals.total_expenses == sum(expense_line_items.values())`
3. `totals.net_income == total_rental_income - total_expenses`

`grand_total_net_income` is the sum of `net_income` across all properties.

Note the distinction from the extractor's cross-check: `extract.py` compares
computed totals against the **printed** ones on the PDF, while `validate.py`
checks the **internal consistency** of a totals block against its own line
items. Today only the CLI calls `validate.py`. The API does not, because it
never stores totals, so there is nothing that could be inconsistent.

---

## `cli.py`

```bash
python -m form8825.cli task_input_files/f8825.pdf -o out.json
python -m form8825.cli f8825_multi.pdf            # JSON to stdout
```

Flow: `extract_pdf` → print warnings → `validate_properties` → print issues
and the grand total → write JSON.

| Stream | Content |
|---|---|
| stdout | The JSON (only when `-o` is not given) |
| stderr | `WARNING`, `VALIDATION`, the grand total line, the "Wrote N properties" line |
| exit code | `0` success, `2` file could not be opened |

Sending diagnostics to stderr keeps stdout clean so it can be piped.

---

## Test fixtures (`testdata/`)

`testdata/source.py` is the **single source of truth**: three properties
(A, B, C) with deliberately varied values and zeros in different fields per
property (A has no commissions, B has no auto/travel or utilities, C has no
advertising). That exercises "empty cell → 0" in every column, not just A.
`compute_totals()` lives here too.

`python -m testdata.make_fixture` derives three files from it, so the PDFs and
the expected JSON cannot drift apart:

| File | Built by | Purpose |
|---|---|---|
| `f8825_multi.pdf` | `generate_fillable_pdf` | Source data written into the IRS's own fillable Rev. 12-2025 form. Values live in field annotations. **Primary fixture.** |
| `f8825_multi_flat.pdf` | `generate_flat_pdf` | Same data drawn onto a page in the Rev. 11-2018 geometry (reportlab). Covers printed-to-PDF forms and proves the extractor finds moved columns. Only A/B/C, so it also proves D is not assumed. |
| `f8825_multi_expected.json` | `build_expected_json` | Expected result. **Both** PDFs must extract to it. |

Implementation notes on the fillable generator:

- The IRS names value fields `f1_23`, `f1_24`, ... with nothing indicating the property column, so `_index_fields` derives the column from each widget's x position: the fields of one line, sorted left to right, are A through D.
- `_reset_form` blanks the widgets **and** the parallel field objects under `/AcroForm/Fields`, then repoints `/AcroForm/Fields` at the page widgets. Leaving the second set behind lets a viewer render stale values over the new ones.
- Blank cells are left empty rather than zero-filled, matching how the real form looks.
- The flat generator draws negatives as `(1,234` to exercise the accounting-negative parse.

The original assignment files in `task_input_files/` are `f8825.pdf` and its
`8825_output.json`. Both fixtures and the real input extract to their expected
JSON exactly.

---

## Adapting to a new form revision

1. Regenerate or obtain a sample. Run the CLI and read the warnings.
2. If it returns no properties, dump `_page_words(page)` and check three things: the property letters sit right of `HEADER_MIN_X0`; at least `MIN_ANCHOR_ROWS` line numbers share a right edge left of the headers; a `(b)` header and a vertical rule exist for the address.
3. Adjust the constants above before touching logic. Most drift is a constant.
4. Add the new revision as a fixture next to the existing two, so a future change cannot break one while the other passes.

If the IRS adds or removes a line, edit `LINE_ITEM_MAP` in `schema.py`. The
extractor, backend and CLI pick it up. Also update `frontend/src/labels.ts`
by hand, since it does not share code with this package.

---

## Known limitations

- **No OCR.** Scanned pages are detected and skipped with a warning. The row/column logic only needs `(text, x0, x1, top, bottom)`, so `ocrmypdf` or word boxes from Tesseract could feed it unchanged. Design in [NOTES.md](NOTES.md), next steps in [WHATS_NEXT.md](WHATS_NEXT.md).
- **Unparseable amounts become `0` silently.** The printed-total cross-check usually catches the resulting mismatch, but only if the form printed a total.
- **Later page overrides earlier** for the same `(letter, line)`; there is no conflict warning.
- **Warnings lose their property letter** when persisted by the backend (only the message text is stored).
- **Amounts are whole dollars.** Cents are rounded away, matching the form.
- **Four properties per page.** More would need `PROPERTY_LETTERS` extended and a form that has the columns.
