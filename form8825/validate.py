"""Validation rules for extracted (or manually edited) Form 8825 data.

Operates on plain dicts matching the output JSON schema (property_name,
property_address, income_line_items, expense_line_items, totals) so it can
be reused by the CLI, the Task 3 API (to validate edits before saving),
and the Task 4 test script - not just the extractor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationIssue:
    property_name: str
    message: str


def validate_property(prop: dict) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    name = prop.get("property_name", "?")
    income = prop["income_line_items"]
    expense = prop["expense_line_items"]
    totals = prop["totals"]

    expected_income = income["gross_rents"] + income["other_income"]
    if totals["total_rental_income"] != expected_income:
        issues.append(ValidationIssue(
            name,
            f"total_rental_income is {totals['total_rental_income']}, expected "
            f"{expected_income} (gross_rents + other_income, line 2c = 2a + 2b)",
        ))

    expected_expenses = sum(expense.values())
    if totals["total_expenses"] != expected_expenses:
        issues.append(ValidationIssue(
            name,
            f"total_expenses is {totals['total_expenses']}, expected "
            f"{expected_expenses} (sum of all expense line items, line 18)",
        ))

    expected_net = totals["total_rental_income"] - totals["total_expenses"]
    if totals["net_income"] != expected_net:
        issues.append(ValidationIssue(
            name,
            f"net_income is {totals['net_income']}, expected {expected_net} "
            "(total_rental_income - total_expenses, line 19)",
        ))

    return issues


def validate_properties(properties: list[dict]) -> tuple[list[ValidationIssue], int]:
    """Returns (all issues across all properties, grand total net income)."""
    issues: list[ValidationIssue] = []
    for prop in properties:
        issues.extend(validate_property(prop))
    grand_total_net_income = sum(p["totals"]["net_income"] for p in properties)
    return issues, grand_total_net_income
