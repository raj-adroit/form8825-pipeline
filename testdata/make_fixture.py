"""Generate the Task 2 multi-property fixtures plus their shared expected JSON,
all derived from testdata/source.py.

Two PDFs are produced from the same source data, because a Form 8825 reaches
the pipeline in two different shapes and the extractor has to handle both:

* ``f8825_multi.pdf`` - the IRS's own fillable Rev. 12-2025 form (the same
  revision the client sends), with the simulated data written into its
  AcroForm fields. This is the primary fixture: its values live in field
  annotations, not in the page's text, exactly like the real input.
* ``f8825_multi_flat.pdf`` - a flattened form with the numbers drawn straight
  into the page content stream, in the older Rev. 11-2018 column geometry.
  This covers forms that arrive printed-to-PDF from tax software, and pins
  the extractor's ability to find the columns on a form whose layout has
  moved.

Both must extract to ``f8825_multi_expected.json``.

Usage:
    python -m testdata.make_fixture
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pypdf
from pypdf.generic import ArrayObject, NameObject
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from testdata.source import SOURCE_PROPERTIES, compute_totals

PAGE_WIDTH, PAGE_HEIGHT = letter

OUT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = OUT_DIR / "task_input_files" / "f8825.pdf"
PDF_PATH = OUT_DIR / "f8825_multi.pdf"
FLAT_PDF_PATH = OUT_DIR / "f8825_multi_flat.pdf"
JSON_PATH = OUT_DIR / "f8825_multi_expected.json"

# (line_code, description) in form order. 2c/18/19 are totals; the rest
# come from LINE_ITEM_MAP in form8825/schema.py.
ROWS: list[tuple[str, str]] = [
    ("2a", "Gross rents"),
    ("2b", "Other income related to rental real estate activity"),
    ("2c", "Total rental real estate income. Add lines 2a and 2b"),
    ("3", "Advertising"),
    ("4", "Auto and travel"),
    ("5", "Cleaning and maintenance"),
    ("6", "Commissions"),
    ("7", "Insurance"),
    ("8", "Interest"),
    ("9", "Legal and other professional fees"),
    ("10", "Real estate taxes"),
    ("11", "Repairs"),
    ("12", "Utilities"),
    ("13", "Wages and salaries"),
    ("14", "Depreciation"),
    ("17", "Other deductions"),
    ("18", "Total rental real estate expenses. Add lines 3 through 17"),
    ("19", "Income or (loss). Subtract line 18 from line 2c"),
]

LINE_ITEM_CODES_BY_SECTION = {
    "income": [("2a", "gross_rents"), ("2b", "other_income")],
    "expense": [
        ("3", "advertising"),
        ("4", "auto_travel"),
        ("5", "cleaning_maintenance"),
        ("6", "commissions"),
        ("7", "insurance"),
        ("8", "interest"),
        ("9", "legal_professional"),
        ("10", "real_estate_taxes"),
        ("11", "repairs"),
        ("12", "utilities"),
        ("13", "wages_salaries"),
        ("14", "depreciation"),
        ("17", "other_deductions"),
    ],
}

FILER_NAME = "Test Multi-Property LLC"
FILER_EIN = "98-7654321"

# Column (b)/(d)/(e) entries for each property. Not part of the extracted
# JSON, but a real filer fills them in, and they sit close enough to the
# address cell that leaving them empty would hide a whole class of bug.
PROPERTY_DETAILS = {
    "A": {"type_code": "2", "fair_rental_days": "365", "personal_use_days": "0"},
    "B": {"type_code": "1", "fair_rental_days": "300", "personal_use_days": "12"},
    "C": {"type_code": "4", "fair_rental_days": "365", "personal_use_days": "0"},
}


def _line_value(prop: dict, code: str) -> int | None:
    for section, pairs in LINE_ITEM_CODES_BY_SECTION.items():
        for line_code, key in pairs:
            if line_code == code:
                section_key = "income_line_items" if section == "income" else "expense_line_items"
                return prop[section_key][key]
    if code in ("2c", "18", "19"):
        totals = compute_totals(prop)
        return {
            "2c": totals["total_rental_income"],
            "18": totals["total_expenses"],
            "19": totals["net_income"],
        }[code]
    return None


def _format_amount(value: int) -> str:
    return f"{value:,}"


# --------------------------------------------------------------------------
# Primary fixture: the real fillable IRS form
# --------------------------------------------------------------------------

def _qualified_name(field) -> str:
    """Fully qualified AcroForm field name, e.g. topmostSubform[0].Page1[0]...."""
    name = str(field.get("/T") or "")
    parent = field.get("/Parent")
    while parent is not None:
        parent = parent.get_object()
        part = str(parent.get("/T") or "")
        if part:
            name = f"{part}.{name}"
        parent = parent.get("/Parent")
    return name


def _page_widgets(page) -> list:
    """The page's widget annotation references."""
    annots = page.get("/Annots")
    return list(annots.get_object()) if annots is not None else []


HEADING_MAX_TOP = 120.0  # the name/EIN row sits above the line-1 property table


def _index_fields(page) -> tuple[dict[str, list[str]], dict[str, dict[str, str]], list[str]]:
    """Map the template's fields to what they mean, by name and position.

    Returns (line_fields, row_fields, heading_fields):
      line_fields["2a"]  -> the four value field names, ordered A, B, C, D
      row_fields["A"]    -> {"a": <address field>, "b": <type>, ...} for line 1
      heading_fields     -> the name and EIN fields, left to right

    The IRS names the value fields f1_23, f1_24, ... with nothing in the name
    to say which property column they belong to, so the column comes from the
    widget's x position: the fields of one line, sorted left to right, are
    columns A through D.
    """
    lines: dict[str, list[tuple[float, str]]] = {}
    rows: dict[str, dict[str, str]] = {}
    headings: list[tuple[float, str]] = []
    page_height = float(page.mediabox.height)

    for ref in _page_widgets(page):
        field = ref.get_object()
        name = _qualified_name(field)
        left, top = float(field["/Rect"][0]), page_height - float(field["/Rect"][3])

        line_match = re.search(r"\.Line([\w-]+?)\[0\]\.", name)
        if line_match:
            lines.setdefault(line_match.group(1), []).append((left, name))
            continue

        row_match = re.search(r"\.Row([A-D])\[0\]\.Col_([a-e])\[0\]\.", name)
        if row_match:
            rows.setdefault(row_match.group(1), {})[row_match.group(2)] = name
            continue

        if top < HEADING_MAX_TOP:
            headings.append((left, name))

    line_fields = {
        code: [name for _, name in sorted(widgets)] for code, widgets in lines.items()
    }
    return line_fields, rows, [name for _, name in sorted(headings)]


def _reset_form(writer: pypdf.PdfWriter) -> None:
    """Blank the template and leave one source of truth for its field values.

    The template ships filled in with the client's own numbers, and clearing
    the widgets on the page isn't enough: the file also carries a second,
    parallel set of field objects in /AcroForm/Fields - different objects,
    with their own values and their own cached appearance streams. Leave those
    behind and a viewer happily renders the client's original numbers over the
    simulated ones, even though the page widgets say otherwise.

    So both sets are blanked, and /AcroForm/Fields is then repointed at the
    page widgets. Each widget carries its own fully qualified /T and no
    /Parent, so they form a valid flat field tree on their own.
    """
    widgets = []
    for page in writer.pages:
        for ref in _page_widgets(page):
            _blank(ref.get_object())
            widgets.append(ref)

    acroform = writer.root_object[NameObject("/AcroForm")]
    for ref in acroform.get("/Fields") or []:
        _blank(ref.get_object())
    acroform[NameObject("/Fields")] = ArrayObject(widgets)


def _blank(field) -> None:
    for key in ("/V", "/AP"):
        field.pop(key, None)


def generate_fillable_pdf(properties: list[dict], path: Path) -> None:
    reader = pypdf.PdfReader(TEMPLATE_PATH)
    writer = pypdf.PdfWriter(clone_from=reader)
    _reset_form(writer)

    page = writer.pages[0]
    line_fields, row_fields, heading_fields = _index_fields(page)
    column_index = {letter_: i for i, letter_ in enumerate("ABCD")}

    values: dict[str, str] = {}
    for field, value in zip(heading_fields, (FILER_NAME, FILER_EIN)):
        values[field] = value

    for prop in properties:
        letter_ = prop["property_name"]
        index = column_index[letter_]

        cells = row_fields.get(letter_, {})
        details = PROPERTY_DETAILS.get(letter_, {})
        for key, value in (
            ("a", prop["property_address"]),
            ("b", details.get("type_code", "")),
            ("d", details.get("fair_rental_days", "")),
            ("e", details.get("personal_use_days", "")),
        ):
            if value and key in cells:
                values[cells[key]] = value

        for code, _ in ROWS:
            amount = _line_value(prop, code)
            if not amount:  # the IRS form is left blank, not zero-filled
                continue
            values[line_fields[code][index]] = _format_amount(amount)

    writer.update_page_form_field_values(page, values, auto_regenerate=False)
    # Belt and braces for viewers that ignore pypdf's generated appearances.
    writer.set_need_appearances_writer(True)
    with open(path, "wb") as f:
        writer.write(f)


# --------------------------------------------------------------------------
# Secondary fixture: a flattened form in the older column geometry
# --------------------------------------------------------------------------

# Header x0 positions follow the Rev. 11-2018 form (evenly spaced, ~62.5pt
# apart). Only A/B/C are used; D is left out to prove the extractor doesn't
# assume all four columns are populated.
COLUMN_X0 = {"A": 354.4, "B": 416.9, "C": 479.4}
VALUE_RIGHT_OFFSET = 31.5  # matches that form's right-aligned value column
LABEL_COL_X = 308.0  # line-number reprint column
LINE_LABEL_X = 40.0
DESC_X = 60.0
ROW_TOP_START = 280.0
ROW_SPACING = 15.0
ROW_TOP = {code: ROW_TOP_START + i * ROW_SPACING for i, (code, _) in enumerate(ROWS)}
PROPERTY_ROW_TOP = {"A": 170.0, "B": 192.0, "C": 214.0}
ADDRESS_TOP_OFFSET = 5.0
COLUMN_HEADER_TOP = 260.0


def _y(top: float) -> float:
    """Convert a pdfplumber-style 'distance from top' to a reportlab y."""
    return PAGE_HEIGHT - top


def generate_flat_pdf(properties: list[dict], path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(36, _y(30), "Form 8825 (simulated test file - Task 2, flattened)")
    c.setFont("Helvetica", 9)
    c.drawString(36, _y(48), "Rental Real Estate Income and Expenses of a Partnership or an S Corporation")
    c.drawString(36, _y(62), "Name: Test Multi-Property LLC")
    c.drawString(300, _y(62), "Employer identification number: 98-7654321")

    c.setFont("Helvetica", 8)
    c.drawString(36, _y(90), "1  Enter the address and type of each rental real estate property.")

    by_letter = {p["property_name"]: p for p in properties}
    for letter_, top in PROPERTY_ROW_TOP.items():
        c.setFont("Helvetica", 9)
        c.drawString(LINE_LABEL_X, _y(top), letter_)
        prop = by_letter.get(letter_)
        if prop:
            c.drawString(DESC_X, _y(top - ADDRESS_TOP_OFFSET), prop["property_address"])

    c.setFont("Helvetica-Bold", 9)
    c.drawString(60, _y(COLUMN_HEADER_TOP - 12), "Properties")
    for letter_, x0 in COLUMN_X0.items():
        c.drawString(x0, _y(COLUMN_HEADER_TOP), letter_)

    c.setFont("Helvetica", 8)
    for code, description in ROWS:
        top = ROW_TOP[code]
        c.drawString(LINE_LABEL_X, _y(top), code)
        c.drawString(DESC_X, _y(top), description)
        c.drawString(LABEL_COL_X, _y(top), code)

        for letter_, prop in by_letter.items():
            amount = _line_value(prop, code)
            if amount is None or amount == 0:
                continue
            right_edge = COLUMN_X0[letter_] + VALUE_RIGHT_OFFSET
            text = _format_amount(amount) if amount >= 0 else f"({_format_amount(-amount)}"
            c.drawRightString(right_edge, _y(top), text)

    c.showPage()
    c.save()


def build_expected_json(properties: list[dict]) -> list[dict]:
    result = []
    for prop in properties:
        result.append({
            "property_name": prop["property_name"],
            "property_address": prop["property_address"],
            "income_line_items": dict(prop["income_line_items"]),
            "expense_line_items": dict(prop["expense_line_items"]),
            "totals": compute_totals(prop),
        })
    return result


def main() -> None:
    generate_fillable_pdf(SOURCE_PROPERTIES, PDF_PATH)
    generate_flat_pdf(SOURCE_PROPERTIES, FLAT_PDF_PATH)
    expected = build_expected_json(SOURCE_PROPERTIES)
    JSON_PATH.write_text(json.dumps(expected, indent=2) + "\n")
    print(f"Wrote {PDF_PATH}")
    print(f"Wrote {FLAT_PDF_PATH}")
    print(f"Wrote {JSON_PATH}")


if __name__ == "__main__":
    main()
