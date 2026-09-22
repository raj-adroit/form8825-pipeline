"""Task 4.2: are total income (2c), total expenses (18) and net income (19)
accurate for every extracted property, and does the grand total roll them up
correctly?

    Line 2c  total income   = 2a (gross_rents) + 2b (other_income)
    Line 18  total expenses = sum of all expense line items
    Line 19  net income     = total income - total expenses
    Grand total net income  = sum of net income across all properties

Exercises form8825/validate.py, which is the same module the CLI and the
Task 3 API use to validate extracted/edited data - so these tests cover the
actual validation logic, not a reimplementation of it.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from form8825.extract import extract_pdf
from form8825.validate import validate_properties, validate_property

ROOT = Path(__file__).parent.parent

FIXTURES = [
    pytest.param(ROOT / "task_input_files" / "f8825.pdf", id="single-property"),
    pytest.param(ROOT / "f8825_multi.pdf", id="multi-property-fillable"),
    pytest.param(ROOT / "f8825_multi_flat.pdf", id="multi-property-flattened"),
]


@pytest.mark.parametrize("pdf_path", FIXTURES)
def test_no_validation_issues_on_clean_fixtures(pdf_path: Path) -> None:
    properties, _warnings = extract_pdf(str(pdf_path))
    issues, _grand_total = validate_properties(properties)
    assert issues == [], f"{pdf_path.name}: unexpected validation issues: {issues}"


@pytest.mark.parametrize("pdf_path", FIXTURES)
def test_line_2c_total_income(pdf_path: Path) -> None:
    """Line 2c = 2a + 2b for every property."""
    properties, _warnings = extract_pdf(str(pdf_path))
    for prop in properties:
        income = prop["income_line_items"]
        expected = income["gross_rents"] + income["other_income"]
        actual = prop["totals"]["total_rental_income"]
        assert actual == expected, (
            f"{pdf_path.name} property {prop['property_name']}: total_rental_income "
            f"is {actual}, expected {expected} (2a + 2b)"
        )


@pytest.mark.parametrize("pdf_path", FIXTURES)
def test_line_18_total_expenses(pdf_path: Path) -> None:
    """Line 18 = sum of every expense line item."""
    properties, _warnings = extract_pdf(str(pdf_path))
    for prop in properties:
        expected = sum(prop["expense_line_items"].values())
        actual = prop["totals"]["total_expenses"]
        assert actual == expected, (
            f"{pdf_path.name} property {prop['property_name']}: total_expenses "
            f"is {actual}, expected {expected} (sum of expense line items)"
        )


@pytest.mark.parametrize("pdf_path", FIXTURES)
def test_line_19_net_income(pdf_path: Path) -> None:
    """Line 19 = total income (2c) - total expenses (18)."""
    properties, _warnings = extract_pdf(str(pdf_path))
    for prop in properties:
        totals = prop["totals"]
        expected = totals["total_rental_income"] - totals["total_expenses"]
        actual = totals["net_income"]
        assert actual == expected, (
            f"{pdf_path.name} property {prop['property_name']}: net_income "
            f"is {actual}, expected {expected} (2c - 18)"
        )


@pytest.mark.parametrize("pdf_path", FIXTURES)
def test_grand_total_net_income(pdf_path: Path) -> None:
    """Grand total net income = sum of net income across all properties."""
    properties, _warnings = extract_pdf(str(pdf_path))
    _issues, grand_total = validate_properties(properties)
    expected = sum(p["totals"]["net_income"] for p in properties)
    assert grand_total == expected


@pytest.mark.parametrize(
    "broken_field, section",
    [
        ("total_rental_income", "2c"),
        ("total_expenses", "18"),
        ("net_income", "19"),
    ],
)
def test_validation_catches_each_broken_total(broken_field: str, section: str) -> None:
    """Negative-path check: validate_property must flag an injected
    inconsistency in each of the three totals, confirming the check actually
    fires rather than only ever passing on already-correct data."""
    properties, _warnings = extract_pdf(str(ROOT / "task_input_files" / "f8825.pdf"))
    broken = copy.deepcopy(properties[0])
    broken["totals"][broken_field] += 1

    issues = validate_property(broken)
    assert any(broken_field in issue.message for issue in issues), (
        f"validate_property failed to catch a broken {broken_field} (line {section})"
    )
