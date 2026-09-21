"""Extract per-property income/expense data from IRS Form 8825.

Where the numbers live
----------------------
A Form 8825 PDF comes in two shapes, and both turn up in practice:

* **Flattened / printed** - the taxpayer's numbers are drawn into the page
  content stream, so ``page.extract_words()`` returns them.
* **Fillable (the IRS's own PDF)** - the page content stream holds only the
  blank template; every entry lives in an AcroForm field annotation. Text
  extraction on such a file returns a pristine empty form, which looks
  exactly like a form with nothing filled in.

``_annotation_words()`` turns each filled field into a word-shaped dict using
its widget rectangle, so both shapes feed the same geometry below and a
fillable PDF needs no separate code path.

Layout strategy: the form prints each property's numbers as right-aligned text in one
of up to four columns (A/B/C/D). Two facts about the layout make it possible
to read the numbers reliably without depending on plain-text ordering:

1. Every line item (2a, 2b, 3-14, 17) has its line number reprinted in a
   narrow column immediately to the left of the value columns, on the *same
   text row* as the dollar amount. That copy is a more reliable row anchor
   than the line's own label, because long labels ("Total rental real estate
   expenses for each property. Add lines...") wrap onto a second line and
   only that second line lines up with the value.
2. The property letters (A/B/C/D) are printed as column headers, and each
   value is right-aligned to sit inside its own column, ending before the
   next column's header starts. So a value can be assigned to a property by
   comparing its right edge (x1) against the header x-positions.

Both the anchor column and the header row are *located on the page* rather
than hardcoded, because the IRS moves them between revisions: the Rev. 11-2018
form puts the anchor column at x~317 and the headers at x~354-548, while the
Rev. 12-2025 form puts them at x~282 and x~321-543. Rows are matched on the
vertical centre of a word rather than its top edge, since a field widget and
the printed line number next to it share a row without sharing a baseline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pdfplumber

from form8825.schema import (
    EXPENSE_KEYS,
    INCOME_KEYS,
    LINE_ITEM_MAP,
    PROPERTY_LETTERS,
    TOTAL_LINE_CODES,
)

NUMBER_RE = re.compile(r"^[-(]?[\d,]+(?:\.\d+)?\)?$")
ROW_TOLERANCE = 4.0  # points; a value and its row anchor share a vertical centre
HEADER_MIN_X0 = 250.0  # property-letter headers sit right of the line labels
ADDRESS_COLUMN_X0 = 45.0  # column (a) starts right of the A/B/C/D row letters
ADDRESS_COLUMN_X1_FALLBACK = 236.0  # used only when the form draws no column rule
ANCHOR_CLUSTER_WIDTH = 6.0  # points; how far apart two right edges can be and still be one column
MIN_ANCHOR_ROWS = 5  # distinct line numbers needed to call a cluster the anchor column

# Line numbers that are reprinted next to their value, and so can act as row
# anchors: the per-property line items plus the per-property totals.
ANCHOR_CODES = set(LINE_ITEM_MAP) | set(TOTAL_LINE_CODES.values())


class ExtractionError(Exception):
    """The file couldn't be opened as a PDF at all (corrupt, encrypted, not a PDF)."""


@dataclass
class ExtractionWarning:
    property_letter: str | None
    message: str


@dataclass
class PageLayout:
    """Row/column positions read off a single page."""

    row_centers: dict[str, float]  # line code -> vertical centre of its value row
    column_x0: dict[str, float]  # property letter -> x0 of its header
    total_centers: dict[str, float]  # "2c"/"18"/"19" -> vertical centre, for cross-checks
    value_x_min: float  # values sit right of this; the anchor column ends here


def has_usable_text_layer(page) -> bool:
    """Heuristic check for a real (non-scanned) text layer.

    A scanned page that hasn't been OCR'd comes back from pdfplumber with
    zero or near-zero chars. A text-layer page that isn't actually a Form
    8825 page (e.g. a cover letter) will have chars but none of the
    form's known labels. Both cases fail this check so the caller can
    decide how to handle them instead of silently extracting nothing.

    Note this deliberately looks at the *template* text, not the taxpayer's
    numbers: on a fillable PDF the numbers are in field annotations, but the
    template still has to be readable for the row/column anchors to work.
    """
    if len(page.chars) < 10:
        return False
    text = (page.extract_text() or "").lower()
    return "gross rents" in text and "rental real estate" in text


def _center(word: dict) -> float:
    return (word["top"] + word["bottom"]) / 2


def _parse_amount(text: str) -> int:
    """Parse a printed amount, treating a leading '(' or '-' as a minus sign."""
    negative = text.startswith(("(", "-"))
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        value = round(float(cleaned))
    except ValueError:
        return 0
    return -value if negative else value


def _annotation_words(page) -> list[dict]:
    """Filled AcroForm field values as word-shaped dicts.

    On a fillable Form 8825 every entry is the /V of a widget annotation and
    never reaches the page content stream. The widget rectangle puts the value
    at the same place on the page a printed value would have occupied, so once
    converted here it goes through exactly the same row/column matching.

    This is also what makes the Rev. 12-2025 continuation page work: on page 2
    the property letters themselves are typed into fields rather than printed,
    so they only become locatable column headers via this function.
    """
    words: list[dict] = []
    for annot in page.annots:
        value = (annot.get("data") or {}).get("V")
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if not isinstance(value, str):
            continue  # checkbox states and unfilled fields
        text = " ".join(value.split())
        if not text:
            continue
        words.append({
            "text": text,
            "x0": annot["x0"],
            "x1": annot["x1"],
            "top": annot["top"],
            "bottom": annot["bottom"],
        })
    return words


def _page_words(page) -> list[dict]:
    """Every readable value on the page: printed text plus filled form fields."""
    return page.extract_words() + _annotation_words(page)


def _find_column_headers(words: list[dict]) -> dict[str, float]:
    """Locate the A/B/C/D property-column headers -> {letter: x0}.

    Picks the row that holds the most distinct property letters right of the
    label area, so a stray "A" elsewhere on the page (e.g. "Schedule A
    (Form 8825)" on line 17) can't be mistaken for a column header.
    """
    candidates = [
        w for w in words
        if w["text"] in PROPERTY_LETTERS and w["x0"] > HEADER_MIN_X0
    ]
    rows: list[list[dict]] = []
    for w in sorted(candidates, key=_center):
        if rows and _center(w) - _center(rows[-1][0]) <= ROW_TOLERANCE:
            rows[-1].append(w)
        else:
            rows.append([w])
    if not rows:
        return {}
    best = max(rows, key=lambda row: (len({w["text"] for w in row}), -row[0]["top"]))
    return {w["text"]: w["x0"] for w in best}


def _find_anchor_column(words: list[dict], max_x: float) -> list[dict]:
    """Words of the narrow column where each line number is reprinted.

    The same line numbers are also printed in the far-left label column, so
    the reprint column is identified as the *rightmost* cluster of
    right-aligned line numbers that still sits left of the value columns.
    Returns [] when the page has no such column.
    """
    candidates = [w for w in words if w["text"] in ANCHOR_CODES and w["x1"] < max_x]
    clusters: list[list[dict]] = []
    for w in sorted(candidates, key=lambda w: w["x1"]):
        if clusters and w["x1"] - clusters[-1][0]["x1"] <= ANCHOR_CLUSTER_WIDTH:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    usable = [c for c in clusters if len({w["text"] for w in c}) >= MIN_ANCHOR_ROWS]
    return usable[-1] if usable else []


def _read_layout(words: list[dict]) -> PageLayout:
    column_x0 = _find_column_headers(words)
    if not column_x0:
        # No property columns on this page - nothing can be attributed anyway.
        return PageLayout({}, {}, {}, float("inf"))

    anchors = _find_anchor_column(words, max_x=min(column_x0.values()))
    row_centers: dict[str, float] = {}
    total_centers: dict[str, float] = {}
    for w in anchors:
        if w["text"] in LINE_ITEM_MAP:
            row_centers[w["text"]] = _center(w)
        else:
            total_centers[w["text"]] = _center(w)

    value_x_min = max((w["x1"] for w in anchors), default=HEADER_MIN_X0)
    return PageLayout(
        row_centers=row_centers,
        column_x0=column_x0,
        total_centers=total_centers,
        value_x_min=value_x_min,
    )


def _column_boundaries(column_x0: dict[str, float]) -> list[tuple[str, float, float]]:
    """Return (letter, left_bound, right_bound) sorted left to right.

    Each column is bounded on the right by the next header. The last column
    has no next header, so it borrows the spacing of the columns before it;
    when it is the *only* column there is no spacing to borrow and nothing
    further right to confuse it with, so it runs to the edge of the page.
    """
    letters = sorted(column_x0, key=lambda letter: column_x0[letter])
    xs = [column_x0[letter] for letter in letters]
    bounds = []
    for i, letter in enumerate(letters):
        if i + 1 < len(xs):
            right = xs[i + 1]
        elif i > 0:
            right = xs[i] + (xs[i] - xs[i - 1])
        else:
            right = float("inf")
        bounds.append((letter, xs[i], right))
    return bounds


def _assign_column(x1: float, bounds: list[tuple[str, float, float]]) -> str | None:
    for letter, left, right in bounds:
        if left - 10 <= x1 < right:
            return letter
    return None


def _extract_page_values(
    words: list[dict], layout: PageLayout
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """Return (values, totals) both keyed by property letter.

    values[letter][line_code] = amount
    totals[letter][line_code] = amount   (line_code in 2c/18/19, for cross-checks)
    """
    bounds = _column_boundaries(layout.column_x0)
    number_words = [
        w for w in words
        if NUMBER_RE.match(w["text"]) and w["x0"] > layout.value_x_min
    ]

    def read_rows(row_centers: dict[str, float]) -> dict[str, dict[str, int]]:
        found: dict[str, dict[str, int]] = {letter: {} for letter in layout.column_x0}
        for code, row_center in row_centers.items():
            for w in number_words:
                if abs(_center(w) - row_center) <= ROW_TOLERANCE:
                    letter = _assign_column(w["x1"], bounds)
                    if letter:
                        found.setdefault(letter, {})[code] = _parse_amount(w["text"])
        return found

    return read_rows(layout.row_centers), read_rows(layout.total_centers)


def _address_column_x1(page, words: list[dict]) -> float:
    """Right edge of the column (a) "physical address" cell.

    This can't be a fixed cutoff, and can't be read off the "(b)" header
    either: the header is centred over its column while the cells beneath it
    start much further left (on the Rev. 12-2025 form, header "(b)" sits at
    x=243 but its cells begin at x=202). A cutoff anywhere right of 202 would
    append the property's type code to its street address. The form draws a
    vertical rule on the real boundary, so use that.
    """
    header_b = next((w for w in words if w["text"] == "(b)"), None)
    if header_b is not None:
        rules = [
            edge["x0"] for edge in page.vertical_edges
            if ADDRESS_COLUMN_X0 < edge["x0"] <= header_b["x0"]
        ]
        if rules:
            return max(rules)
    return ADDRESS_COLUMN_X1_FALLBACK


def _extract_page_addresses(
    words: list[dict], first_row_center: float | None, address_x1: float
) -> dict[str, str]:
    letter_rows = [
        w for w in words
        if w["text"] in PROPERTY_LETTERS
        and w["x0"] < ADDRESS_COLUMN_X0
        and (first_row_center is None or _center(w) < first_row_center)
        and w["top"] > 100
    ]
    addresses: dict[str, str] = {}
    for lw in letter_rows:
        parts = [
            w for w in words
            if ADDRESS_COLUMN_X0 <= w["x0"] < address_x1
            and lw["top"] - 15 <= w["top"] <= lw["top"] + 3
        ]
        parts.sort(key=lambda w: (w["top"], w["x0"]))
        addresses[lw["text"]] = " ".join(p["text"] for p in parts).strip()
    return addresses


def extract_pdf(path: str) -> tuple[list[dict], list[ExtractionWarning]]:
    """Extract every property on the form into the output JSON's schema.

    Returns (properties, warnings). Each property dict has
    property_name/property_address/income_line_items/expense_line_items/totals,
    matching task_input_files/8825_output.json. Totals are computed from the extracted line
    items (2c = 2a+2b, 18 = sum of expenses, 19 = 2c-18) rather than copied
    from the form, and cross-checked against the form's own printed totals;
    a mismatch is reported as a warning rather than silently trusted.

    Raises ExtractionError if the file can't be opened as a PDF. Anything that
    goes wrong *within* a readable PDF (an unreadable page, a blank form, a
    total that doesn't add up) comes back as a warning instead, so one bad
    page can't cost you the rest of the document.
    """
    warnings: list[ExtractionWarning] = []
    merged_values: dict[str, dict[str, int]] = {}
    merged_totals: dict[str, dict[str, int]] = {}
    merged_addresses: dict[str, str] = {}
    property_order: list[str] = []

    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:  # pdfminer raises a family of unrelated exception types
        raise ExtractionError(f"could not open {path} as a PDF: {exc}") from exc

    with pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            if not has_usable_text_layer(page):
                warnings.append(ExtractionWarning(
                    None,
                    f"page {page_number} has no usable text layer; skipped "
                    "(would need OCR - see README notes)",
                ))
                continue

            words = _page_words(page)
            layout = _read_layout(words)
            first_row_center = min(layout.row_centers.values(), default=None)
            page_values, page_totals = _extract_page_values(words, layout)
            page_addresses = _extract_page_addresses(
                words, first_row_center, _address_column_x1(page, words)
            )

            for letter, line_values in page_values.items():
                if not line_values and not page_addresses.get(letter):
                    continue
                if letter not in merged_values:
                    property_order.append(letter)
                merged_values.setdefault(letter, {}).update(line_values)
                merged_totals.setdefault(letter, {}).update(page_totals.get(letter, {}))
            for letter, address in page_addresses.items():
                if address:
                    merged_addresses[letter] = address
                    if letter not in property_order:
                        property_order.append(letter)

    if not property_order:
        warnings.append(ExtractionWarning(
            None,
            "no properties found; the form appears to be blank, or its layout "
            "isn't one this extractor recognises",
        ))

    properties: list[dict] = []
    for letter in sorted(property_order):
        line_values = merged_values.get(letter, {})
        income = {key: 0 for key in INCOME_KEYS}
        expense = {key: 0 for key in EXPENSE_KEYS}
        for code, (section, key) in LINE_ITEM_MAP.items():
            amount = line_values.get(code, 0)
            (income if section == "income" else expense)[key] = amount

        total_income = income["gross_rents"] + income["other_income"]
        total_expenses = sum(expense.values())
        net_income = total_income - total_expenses

        reported = merged_totals.get(letter, {})
        for code, computed, label in (
            ("2c", total_income, "total income"),
            ("18", total_expenses, "total expenses"),
            ("19", net_income, "net income"),
        ):
            if code in reported and reported[code] != computed:
                warnings.append(ExtractionWarning(
                    letter,
                    f"{label}: computed {computed} but form prints {reported[code]} "
                    f"for line {code}",
                ))

        properties.append({
            "property_name": letter,
            "property_address": merged_addresses.get(letter, ""),
            "income_line_items": income,
            "expense_line_items": expense,
            "totals": {
                "total_rental_income": total_income,
                "total_expenses": total_expenses,
                "net_income": net_income,
            },
        })

    return properties, warnings
