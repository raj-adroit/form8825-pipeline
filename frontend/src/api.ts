import type { Document, DocumentSummary, LineItem, LineItemChange } from "./types"

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json() as Promise<T>
}

export function listDocuments(): Promise<DocumentSummary[]> {
  return fetch("/api/documents").then((r) => handle(r))
}

export function getDocument(id: number, signal?: AbortSignal): Promise<Document> {
  return fetch(`/api/documents/${id}`, { signal }).then((r) => handle(r))
}

export function extractDocument(file: File): Promise<Document> {
  const form = new FormData()
  form.append("file", file)
  return fetch("/api/extract", { method: "POST", body: form }).then((r) => handle(r))
}

export function updateLineItem(
  id: number,
  value: number,
  changedBy: string,
  note?: string,
): Promise<LineItem> {
  return fetch(`/api/line-items/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value, changed_by: changedBy, note }),
  }).then((r) => handle(r))
}

export function getLineItemHistory(id: number): Promise<LineItemChange[]> {
  return fetch(`/api/line-items/${id}/history`).then((r) => handle(r))
}

export async function deleteDocument(id: number): Promise<void> {
  const res = await fetch(`/api/documents/${id}`, { method: "DELETE" })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
}
