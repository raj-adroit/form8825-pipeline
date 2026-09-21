"""Line-number -> JSON-field mapping for IRS Form 8825, and the row anchors
used to locate each line on the page.

Line numbers/labels are exactly as printed in the narrow "line #" column
that sits just left of the property value columns (see extract.py for how
that column is located).
"""

from __future__ import annotations

# (section, json_key) for each form line that has a per-property dollar value.
# Lines 15 and 16 are "Reserved for future use" and are intentionally omitted.
LINE_ITEM_MAP: dict[str, tuple[str, str]] = {
    "2a": ("income", "gross_rents"),
    "2b": ("income", "other_income"),
    "3": ("expense", "advertising"),
    "4": ("expense", "auto_travel"),
    "5": ("expense", "cleaning_maintenance"),
    "6": ("expense", "commissions"),
    "7": ("expense", "insurance"),
    "8": ("expense", "interest"),
    "9": ("expense", "legal_professional"),
    "10": ("expense", "real_estate_taxes"),
    "11": ("expense", "repairs"),
    "12": ("expense", "utilities"),
    "13": ("expense", "wages_salaries"),
    "14": ("expense", "depreciation"),
    "17": ("expense", "other_deductions"),
}

# Form-level totals, reported once per property. Used only to cross-check
# the sum of the line items above; they are not copied into the output
# JSON's income/expense blocks.
TOTAL_LINE_CODES = {
    "total_income": "2c",
    "total_expenses": "18",
    "net_income": "19",
}

INCOME_KEYS = [key for section, key in LINE_ITEM_MAP.values() if section == "income"]
EXPENSE_KEYS = [key for section, key in LINE_ITEM_MAP.values() if section == "expense"]

PROPERTY_LETTERS = ["A", "B", "C", "D"]
