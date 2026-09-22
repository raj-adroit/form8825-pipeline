"""Task 4.1: does the extractor produce the expected JSON for each property?

Runs form8825.extract.extract_pdf() against every fixture PDF and compares
the result to its expected JSON, field by field, so a mismatch points at
exactly which line item / property drifted instead of just "not equal".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from form8825.extract import extract_pdf

ROOT = Path(__file__).parent.parent

FIXTURES = [
    pytest.param(
        ROOT / "task_input_files" / "f8825.pdf",
        ROOT / "task_input_files" / "8825_output.json",
        id="single-property",
    ),
    pytest.param(
        ROOT / "f8825_multi.pdf",
        ROOT / "f8825_multi_expected.json",
        id="multi-property-fillable",
    ),
    pytest.param(
        ROOT / "f8825_multi_flat.pdf",
        ROOT / "f8825_multi_expected.json",
        id="multi-property-flattened",
    ),
]


def _load_expected(path: Path) -> dict[str, dict]:
    return {p["property_name"]: p for p in json.loads(path.read_text())}


@pytest.mark.parametrize("pdf_path, expected_path", FIXTURES)
def test_no_extraction_warnings(pdf_path: Path, expected_path: Path) -> None:
    _properties, warnings = extract_pdf(str(pdf_path))
    assert not warnings, (
        f"{pdf_path.name}: expected a clean extraction, got warnings: "
        f"{[w.message for w in warnings]}"
    )


@pytest.mark.parametrize("pdf_path, expected_path", FIXTURES)
def test_property_set_matches_expected(pdf_path: Path, expected_path: Path) -> None:
    properties, _warnings = extract_pdf(str(pdf_path))
    actual_names = {p["property_name"] for p in properties}
    expected_names = set(_load_expected(expected_path))
    assert actual_names == expected_names, (
        f"{pdf_path.name}: extracted properties {sorted(actual_names)} != "
        f"expected {sorted(expected_names)}"
    )


@pytest.mark.parametrize("pdf_path, expected_path", FIXTURES)
def test_extraction_matches_expected_json_exactly(pdf_path: Path, expected_path: Path) -> None:
    properties, _warnings = extract_pdf(str(pdf_path))
    actual_by_name = {p["property_name"]: p for p in properties}
    expected_by_name = _load_expected(expected_path)

    for name, expected_prop in expected_by_name.items():
        actual_prop = actual_by_name.get(name)
        assert actual_prop is not None, f"{pdf_path.name}: property {name} missing from extraction"
        assert actual_prop == expected_prop, (
            f"{pdf_path.name} property {name}: extracted\n{json.dumps(actual_prop, indent=2)}\n"
            f"!= expected\n{json.dumps(expected_prop, indent=2)}"
        )


@pytest.mark.parametrize(
    "field",
    [
        "income_line_items.gross_rents",
        "income_line_items.other_income",
        "expense_line_items.advertising",
        "expense_line_items.auto_travel",
        "expense_line_items.cleaning_maintenance",
        "expense_line_items.commissions",
        "expense_line_items.insurance",
        "expense_line_items.interest",
        "expense_line_items.legal_professional",
        "expense_line_items.real_estate_taxes",
        "expense_line_items.repairs",
        "expense_line_items.utilities",
        "expense_line_items.wages_salaries",
        "expense_line_items.depreciation",
        "expense_line_items.other_deductions",
    ],
)
@pytest.mark.parametrize("pdf_path, expected_path", FIXTURES)
def test_each_line_item_matches_expected(pdf_path: Path, expected_path: Path, field: str) -> None:
    """Same comparison as test_extraction_matches_expected_json_exactly, but one
    assertion per (fixture, property, line item) so a single wrong number fails
    its own test case instead of getting lost inside one big dict diff."""
    section, key = field.split(".")
    properties, _warnings = extract_pdf(str(pdf_path))
    actual_by_name = {p["property_name"]: p for p in properties}
    expected_by_name = _load_expected(expected_path)

    for name, expected_prop in expected_by_name.items():
        actual_prop = actual_by_name.get(name, {})
        expected_value = expected_prop[section][key]
        actual_value = actual_prop.get(section, {}).get(key)
        assert actual_value == expected_value, (
            f"{pdf_path.name} property {name} {field}: got {actual_value}, expected {expected_value}"
        )
