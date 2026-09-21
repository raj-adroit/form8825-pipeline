from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from backend import crud
from backend.db import get_session, init_db
from backend.models import Document
from backend.schemas import DocumentOut, DocumentSummary, LineItemChangeOut, LineItemOut, UpdateLineItemRequest
from form8825.extract import ExtractionError

app = FastAPI(title="Form 8825 Extraction API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SessionDep = Annotated[Session, Depends(get_session)]


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.post("/api/extract", response_model=DocumentOut)
def extract_document(file: UploadFile, session: SessionDep) -> DocumentOut:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "only PDF files are supported")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        document = crud.ingest_pdf(session, file.filename, tmp_path)
    except ExtractionError as exc:
        # A file we can't open at all is the caller's problem, not a server error.
        # Report the reason against the name they uploaded, not our temp path.
        raise HTTPException(400, f"could not read {file.filename} as a PDF: {exc.__cause__}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return crud.serialize_document(session, document)


@app.get("/api/documents", response_model=list[DocumentSummary])
def list_documents(session: SessionDep) -> list[DocumentSummary]:
    return crud.list_documents(session)


@app.get("/api/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, session: SessionDep) -> DocumentOut:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "document not found")
    return crud.serialize_document(session, document)


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: int, session: SessionDep) -> None:
    if not crud.delete_document(session, document_id):
        raise HTTPException(404, "document not found")


@app.patch("/api/line-items/{line_item_id}", response_model=LineItemOut)
def patch_line_item(line_item_id: int, body: UpdateLineItemRequest, session: SessionDep) -> LineItemOut:
    try:
        item = crud.update_line_item(session, line_item_id, body.value, body.changed_by, body.note)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return LineItemOut(**item.model_dump())


@app.get("/api/line-items/{line_item_id}/history", response_model=list[LineItemChangeOut])
def get_line_item_history(line_item_id: int, session: SessionDep) -> list[LineItemChangeOut]:
    changes = crud.line_item_history(session, line_item_id)
    return [LineItemChangeOut(**c.model_dump()) for c in changes]
