"""Single source of truth for the multi-property test fixture (Task 2).

Both `f8825_multi.pdf` and `f8825_multi_expected.json` are generated from
this data by make_fixture.py, so the two can never drift apart. Values are
intentionally varied and put zeros in different fields per property (e.g.
A has no commissions, B has no auto/travel or utilities, C has no
advertising) so the fixture exercises "empty cell -> 0" handling across
every column, not just column A the way the single-property input does.
"""

from __future__ import annotations

SOURCE_PROPERTIES = [
    {
        "property_name": "A",
        "property_address": "123 lake ave",
        "income_line_items": {
            "gross_rents": 182400,
            "other_income": 1200,
        },
        "expense_line_items": {
            "advertising": 0,
            "auto_travel": 1450,
            "cleaning_maintenance": 8200,
            "commissions": 0,
            "insurance": 6100,
            "interest": 42300,
            "legal_professional": 1800,
            "real_estate_taxes": 15400,
            "repairs": 5200,
            "utilities": 3100,
            "wages_salaries": 0,
            "depreciation": 28750,
            "other_deductions": 2200,
        },
    },
    {
        "property_name": "B",
        "property_address": "45 market st",
        "income_line_items": {
            "gross_rents": 96000,
            "other_income": 0,
        },
        "expense_line_items": {
            "advertising": 3600,
            "auto_travel": 0,
            "cleaning_maintenance": 4100,
            "commissions": 5760,
            "insurance": 2900,
            "interest": 21000,
            "legal_professional": 950,
            "real_estate_taxes": 8700,
            "repairs": 6300,
            "utilities": 0,
            "wages_salaries": 12000,
            "depreciation": 15400,
            "other_deductions": 1100,
        },
    },
    {
        "property_name": "C",
        "property_address": "900 maple ct",
        "income_line_items": {
            "gross_rents": 310500,
            "other_income": 4800,
        },
        "expense_line_items": {
            "advertising": 0,
            "auto_travel": 2100,
            "cleaning_maintenance": 11400,
            "commissions": 0,
            "insurance": 9800,
            "interest": 68500,
            "legal_professional": 3200,
            "real_estate_taxes": 27600,
            "repairs": 9100,
            "utilities": 5400,
            "wages_salaries": 42000,
            "depreciation": 51200,
            "other_deductions": 6700,
        },
    },
]


def compute_totals(prop: dict) -> dict:
    income = prop["income_line_items"]
    expense = prop["expense_line_items"]
    total_income = income["gross_rents"] + income["other_income"]
    total_expenses = sum(expense.values())
    return {
        "total_rental_income": total_income,
        "total_expenses": total_expenses,
        "net_income": total_income - total_expenses,
    }
