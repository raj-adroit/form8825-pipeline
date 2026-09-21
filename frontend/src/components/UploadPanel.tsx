import { useRef, useState } from "react"

interface Props {
  onUpload: (file: File) => Promise<void>
}

export function UploadPanel({ onUpload }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await onUpload(file)
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <div className="upload-panel">
      <label className="upload-button">
        {busy ? "Extracting…" : "Upload Form 8825 PDF"}
        <input ref={inputRef} type="file" accept="application/pdf" onChange={handleChange} disabled={busy} />
      </label>
      {error && <p className="error">{error}</p>}
    </div>
  )
}
