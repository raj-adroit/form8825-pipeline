"""Pydantic request/response shapes. Kept separate from the SQLModel
tables in models.py so the API's JSON shape (nested, grouped into
income/expense, with computed totals) doesn't have to match the flat
row-per-line-item table layout.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LineItemOut(BaseModel):
    id: int
    key: str
    value: int
    source: str
    updated_at: datetime


class TotalsOut(BaseModel):
    total_rental_income: int
    total_expenses: int
    net_income: int


class PropertyOut(BaseModel):
    id: int
    property_name: str
    property_address: str
    income_line_items: dict[str, LineItemOut]
    expense_line_items: dict[str, LineItemOut]
    totals: TotalsOut


class DocumentOut(BaseModel):
    id: int
    filename: str
    uploaded_at: datetime
    warnings: list[str]
    properties: list[PropertyOut]
    grand_total_net_income: int


class DocumentSummary(BaseModel):
    id: int
    filename: str
    uploaded_at: datetime
    property_count: int


class UpdateLineItemRequest(BaseModel):
    value: int
    changed_by: str = "user"
    note: str | None = None


class LineItemChangeOut(BaseModel):
    id: int
    old_value: int | None
    new_value: int
    changed_by: str
    note: str | None
    changed_at: datetime
