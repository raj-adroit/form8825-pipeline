import { useEffect, useState } from "react"
import { deleteDocument, extractDocument, getDocument, listDocuments, updateLineItem } from "./api"
import { DocumentSidebar } from "./components/DocumentSidebar"
import { PropertyCard } from "./components/PropertyCard"
import { UploadPanel } from "./components/UploadPanel"
import { formatCurrency } from "./format"
import type { Document, DocumentSummary } from "./types"
import "./App.css"

function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [document, setDocument] = useState<Document | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshDocumentList = async () => {
    const docs = await listDocuments()
    setDocuments(docs)
    return docs
  }

  useEffect(() => {
    refreshDocumentList().catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (selectedId === null) {
      setDocument(null)
      return
    }
    // Abort the in-flight fetch when the selection changes again, so a slow
    // response for a previously-selected document can't overwrite the current one.
    const controller = new AbortController()
    getDocument(selectedId, controller.signal)
      .then(setDocument)
      .catch((e) => {
        if (e instanceof DOMException && e.name === "AbortError") return
        setError(String(e))
      })
    return () => controller.abort()
  }, [selectedId])

  // Fetch the document back from the server rather than recomputing totals in the
  // client, so the UI totals always match the single source of truth (line_items).
  const reloadSelectedDocument = async () => {
    if (selectedId === null) return
    const fresh = await getDocument(selectedId)
    setDocument(fresh)
  }

  const handleUpload = async (file: File) => {
    setError(null)
    try {
      const doc = await extractDocument(file)
      await refreshDocumentList()
      setSelectedId(doc.id)
      setDocument(doc)
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDelete = async (id: number) => {
    setError(null)
    try {
      await deleteDocument(id)
      await refreshDocumentList()
      if (selectedId === id) {
        setSelectedId(null)
        setDocument(null)
      }
    } catch (e) {
      setError(String(e))
    }
  }

  const handleLineItemSave = async (lineItemId: number, newValue: number) => {
    setError(null)
    try {
      await updateLineItem(lineItemId, newValue, "user")
    } catch (e) {
      setError(String(e))
    } finally {
      // Resync from the server on both success and failure so a rejected edit
      // doesn't leave the UI showing a value that was never persisted.
      await reloadSelectedDocument().catch((e) => setError(String(e)))
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Form 8825</h1>
        <UploadPanel onUpload={handleUpload} />
        <DocumentSidebar
          documents={documents}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onDelete={handleDelete}
        />
      </aside>

      <main className="main">
        {error && <p className="error">{error}</p>}
        {!document && <p className="empty-state">Select or upload a document to view its extracted data.</p>}
        {document && (
          <>
            <div className="document-header">
              <h2>{document.filename}</h2>
              {document.warnings.length > 0 && (
                <div className="warnings">
                  {document.warnings.map((w, i) => (
                    <p key={i} className="warning">⚠ {w}</p>
                  ))}
                </div>
              )}
            </div>

            <div className="properties">
              {document.properties.map((property) => (
                <PropertyCard key={property.id} property={property} onLineItemSave={handleLineItemSave} />
              ))}
            </div>

            <footer className="grand-total">
              Grand total net income: {formatCurrency(document.grand_total_net_income)}
            </footer>
          </>
        )}
      </main>
    </div>
  )
}

export default App
