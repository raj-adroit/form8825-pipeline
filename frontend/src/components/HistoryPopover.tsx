import { useEffect, useState } from "react"
import { getLineItemHistory } from "../api"
import { formatCurrency, formatDateTime } from "../format"
import type { LineItemChange } from "../types"

export function HistoryPopover({ lineItemId, onClose }: { lineItemId: number; onClose: () => void }) {
  const [changes, setChanges] = useState<LineItemChange[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getLineItemHistory(lineItemId)
      .then(setChanges)
      .catch((e) => setError(String(e)))
  }, [lineItemId])

  return (
    <div className="history-popover">
      <div className="history-popover-header">
        <strong>Change history</strong>
        <button onClick={onClose} aria-label="Close">×</button>
      </div>
      {error && <p className="error">{error}</p>}
      {!changes && !error && <p>Loading…</p>}
      {changes && changes.length === 0 && <p>No changes recorded.</p>}
      {changes && changes.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>By</th>
              <th>Old</th>
              <th>New</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {changes.map((c) => (
              <tr key={c.id}>
                <td>{formatDateTime(c.changed_at)}</td>
                <td>{c.changed_by}</td>
                <td>{c.old_value === null ? "—" : formatCurrency(c.old_value)}</td>
                <td>{formatCurrency(c.new_value)}</td>
                <td>{c.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
