import { useState } from "react"
import { formatDateTime } from "../format"
import type { DocumentSummary } from "../types"

interface Props {
  documents: DocumentSummary[]
  selectedId: number | null
  onSelect: (id: number) => void
  onDelete: (id: number) => Promise<void>
}

export function DocumentSidebar({ documents, selectedId, onSelect, onDelete }: Props) {
  const [confirmingId, setConfirmingId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  if (documents.length === 0) {
    return <p className="empty-state">No documents uploaded yet.</p>
  }

  const handleDelete = async (id: number) => {
    setDeletingId(id)
    try {
      await onDelete(id)
    } finally {
      setDeletingId(null)
      setConfirmingId(null)
    }
  }

  return (
    <ul className="document-list">
      {documents.map((doc) => (
        <li key={doc.id}>
          <div className={doc.id === selectedId ? "document-row selected" : "document-row"}>
            <button className="document-select" onClick={() => onSelect(doc.id)}>
              <span className="filename">{doc.filename}</span>
              <span className="meta">
                {doc.property_count} propert{doc.property_count === 1 ? "y" : "ies"} · {formatDateTime(doc.uploaded_at)}
              </span>
            </button>
            {confirmingId === doc.id ? (
              <span className="delete-confirm">
                <button
                  className="confirm-delete-button"
                  disabled={deletingId === doc.id}
                  onClick={() => handleDelete(doc.id)}
                >
                  {deletingId === doc.id ? "…" : "Delete?"}
                </button>
                <button className="cancel-delete-button" onClick={() => setConfirmingId(null)}>
                  ✕
                </button>
              </span>
            ) : (
              <button
                className="delete-button"
                title="Delete document"
                aria-label={`Delete ${doc.filename}`}
                onClick={() => setConfirmingId(doc.id)}
              >
                🗑
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
