"""SQLModel tables backing Task 3.

documents        - one row per uploaded PDF
extraction_runs  - one row per extraction attempt on a document (keeps the
                    door open for re-running extraction on the same file
                    without losing the previous result)
properties       - one row per property (A/B/C/D) found by a run
line_items       - current value of each income/expense field; `source`
                    distinguishes an untouched extracted value from a
                    manual correction
line_item_changes - append-only audit log: every edit, extracted or
                    manual, is recorded here and never overwritten
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    uploaded_at: datetime = Field(default_factory=_utcnow)

    runs: List["ExtractionRun"] = Relationship(back_populates="document")


class ExtractionRun(SQLModel, table=True):
    __tablename__ = "extraction_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="documents.id")
    created_at: datetime = Field(default_factory=_utcnow)
    warnings_json: str = Field(default="[]")  # JSON-encoded list[str]

    document: Optional[Document] = Relationship(back_populates="runs")
    properties: List["Property"] = Relationship(back_populates="run")


class Property(SQLModel, table=True):
    __tablename__ = "properties"

    id: Optional[int] = Field(default=None, primary_key=True)
    extraction_run_id: int = Field(foreign_key="extraction_runs.id")
    property_name: str
    property_address: str = ""

    run: Optional[ExtractionRun] = Relationship(back_populates="properties")
    line_items: List["LineItem"] = Relationship(back_populates="property")


class LineItem(SQLModel, table=True):
    __tablename__ = "line_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="properties.id")
    section: str  # "income" | "expense"
    key: str  # e.g. "gross_rents"
    value: int
    source: str = "extracted"  # "extracted" | "manual"
    updated_at: datetime = Field(default_factory=_utcnow)

    property: Optional[Property] = Relationship(back_populates="line_items")
    changes: List["LineItemChange"] = Relationship(back_populates="line_item")


class LineItemChange(SQLModel, table=True):
    __tablename__ = "line_item_changes"

    id: Optional[int] = Field(default=None, primary_key=True)
    line_item_id: int = Field(foreign_key="line_items.id")
    old_value: Optional[int]
    new_value: int
    changed_by: str = "system"
    note: Optional[str] = None
    changed_at: datetime = Field(default_factory=_utcnow)

    line_item: Optional[LineItem] = Relationship(back_populates="changes")
