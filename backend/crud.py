from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from backend.models import Document, ExtractionRun, LineItem, LineItemChange, Property
from backend.schemas import DocumentOut, DocumentSummary, LineItemOut, PropertyOut, TotalsOut
from form8825.extract import extract_pdf
from form8825.schema import EXPENSE_KEYS, INCOME_KEYS


def ingest_pdf(session: Session, filename: str, pdf_path: str) -> Document:
    """Run extraction on pdf_path and persist a document/run/properties/
    line_items tree. This is the only place extraction results get
    written to the DB - everything after this is edits via update_line_item.
    """
    properties, warnings = extract_pdf(pdf_path)

    document = Document(filename=filename)
    session.add(document)
    session.flush()  # assigns document.id

    run = ExtractionRun(
        document_id=document.id,
        warnings_json=json.dumps([w.message for w in warnings]),
    )
    session.add(run)
    session.flush()

    for prop in properties:
        db_property = Property(
            extraction_run_id=run.id,
            property_name=prop["property_name"],
            property_address=prop["property_address"],
        )
        session.add(db_property)
        session.flush()

        for key in INCOME_KEYS:
            _add_line_item(session, db_property.id, "income", key, prop["income_line_items"][key])
        for key in EXPENSE_KEYS:
            _add_line_item(session, db_property.id, "expense", key, prop["expense_line_items"][key])

    session.commit()
    session.refresh(document)
    return document


def _add_line_item(session: Session, property_id: int, section: str, key: str, value: int) -> LineItem:
    item = LineItem(property_id=property_id, section=section, key=key, value=value, source="extracted")
    session.add(item)
    session.flush()
    session.add(LineItemChange(line_item_id=item.id, old_value=None, new_value=value, changed_by="extractor"))
    return item


def _latest_run(session: Session, document_id: int) -> ExtractionRun | None:
    return session.exec(
        select(ExtractionRun)
        .where(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
    ).first()


def _totals(income: dict[str, LineItemOut], expense: dict[str, LineItemOut]) -> TotalsOut:
    total_income = sum(item.value for item in income.values())
    total_expenses = sum(item.value for item in expense.values())
    return TotalsOut(
        total_rental_income=total_income,
        total_expenses=total_expenses,
        net_income=total_income - total_expenses,
    )


def serialize_document(session: Session, document: Document) -> DocumentOut:
    run = _latest_run(session, document.id)
    property_rows: list[Property] = []
    warnings: list[str] = []
    if run is not None:
        warnings = json.loads(run.warnings_json)
        property_rows = session.exec(
            select(Property).where(Property.extraction_run_id == run.id)
        ).all()

    properties_out: list[PropertyOut] = []
    for prop in property_rows:
        line_items = session.exec(select(LineItem).where(LineItem.property_id == prop.id)).all()
        income = {li.key: LineItemOut(**li.model_dump()) for li in line_items if li.section == "income"}
        expense = {li.key: LineItemOut(**li.model_dump()) for li in line_items if li.section == "expense"}
        properties_out.append(PropertyOut(
            id=prop.id,
            property_name=prop.property_name,
            property_address=prop.property_address,
            income_line_items=income,
            expense_line_items=expense,
            totals=_totals(income, expense),
        ))

    return DocumentOut(
        id=document.id,
        filename=document.filename,
        uploaded_at=document.uploaded_at,
        warnings=warnings,
        properties=properties_out,
        grand_total_net_income=sum(p.totals.net_income for p in properties_out),
    )


def list_documents(session: Session) -> list[DocumentSummary]:
    documents = session.exec(select(Document).order_by(Document.uploaded_at.desc())).all()
    summaries = []
    for doc in documents:
        run = _latest_run(session, doc.id)
        count = 0
        if run is not None:
            count = len(session.exec(select(Property).where(Property.extraction_run_id == run.id)).all())
        summaries.append(DocumentSummary(
            id=doc.id, filename=doc.filename, uploaded_at=doc.uploaded_at, property_count=count,
        ))
    return summaries


def update_line_item(session: Session, line_item_id: int, new_value: int, changed_by: str, note: str | None) -> LineItem:
    item = session.get(LineItem, line_item_id)
    if item is None:
        raise ValueError(f"line item {line_item_id} not found")

    old_value = item.value
    item.value = new_value
    item.source = "manual"
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
    session.add(LineItemChange(
        line_item_id=item.id, old_value=old_value, new_value=new_value,
        changed_by=changed_by, note=note,
    ))
    session.commit()
    session.refresh(item)
    return item


def line_item_history(session: Session, line_item_id: int) -> list[LineItemChange]:
    return session.exec(
        select(LineItemChange)
        .where(LineItemChange.line_item_id == line_item_id)
        .order_by(LineItemChange.changed_at.asc())
    ).all()


def get_property_id_for_line_item(session: Session, line_item_id: int) -> int | None:
    item = session.get(LineItem, line_item_id)
    return item.property_id if item else None


def get_document_id_for_property(session: Session, property_id: int) -> int | None:
    prop = session.get(Property, property_id)
    if prop is None:
        return None
    run = session.get(ExtractionRun, prop.extraction_run_id)
    return run.document_id if run else None


def delete_document(session: Session, document_id: int) -> bool:
    """Delete a document and everything under it (runs, properties, line
    items, and their change history). Returns False if it didn't exist.
    """
    document = session.get(Document, document_id)
    if document is None:
        return False

    runs = session.exec(select(ExtractionRun).where(ExtractionRun.document_id == document_id)).all()
    for run in runs:
        properties = session.exec(select(Property).where(Property.extraction_run_id == run.id)).all()
        for prop in properties:
            line_items = session.exec(select(LineItem).where(LineItem.property_id == prop.id)).all()
            for item in line_items:
                changes = session.exec(
                    select(LineItemChange).where(LineItemChange.line_item_id == item.id)
                ).all()
                for change in changes:
                    session.delete(change)
                session.delete(item)
            session.delete(prop)
        session.delete(run)
    session.delete(document)
    session.commit()
    return True
