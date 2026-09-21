import { useState } from "react"
import { HistoryPopover } from "./HistoryPopover"
import type { LineItem } from "../types"

interface Props {
  label: string
  item: LineItem
  onSave: (lineItemId: number, newValue: number) => Promise<void>
}

export function LineItemRow({ label, item, onSave }: Props) {
  const [draft, setDraft] = useState(String(item.value))
  const [saving, setSaving] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  const commit = async () => {
    const parsed = Number(draft)
    if (Number.isNaN(parsed)) {
      setDraft(String(item.value))
      return
    }
    if (parsed === item.value) return
    setSaving(true)
    try {
      await onSave(item.id, parsed)
    } finally {
      setSaving(false)
    }
  }

  return (
    <tr className={item.source === "manual" ? "manual-row" : undefined}>
      <td className="label-cell">{label}</td>
      <td className="value-cell">
        <input
          type="number"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur()
          }}
          disabled={saving}
        />
      </td>
      <td className="source-cell">
        {item.source === "manual" && <span className="badge">edited</span>}
      </td>
      <td className="history-cell">
        <button className="link-button" onClick={() => setShowHistory(true)}>
          history
        </button>
        {showHistory && (
          <HistoryPopover lineItemId={item.id} onClose={() => setShowHistory(false)} />
        )}
      </td>
    </tr>
  )
}
