# Frontend logic (`frontend/`)

A single-page React UI for uploading a Form 8825 PDF, reviewing what was
extracted per property, correcting any number by hand, and inspecting the
change history of every value. It holds no business rules of its own: the
server computes the totals and owns the data.

- [Stack](#stack)
- [Running](#running)
- [File map](#file-map)
- [Component tree](#component-tree)
- [State ownership](#state-ownership)
- [Data flows](#data-flows)
- [API layer](#api-layer)
- [Types and label mapping](#types-and-label-mapping)
- [Component reference](#component-reference)
- [Formatting](#formatting)
- [Styling](#styling)
- [Error handling](#error-handling)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)

---

## Stack

| Piece | Choice |
|---|---|
| UI | React 19 (function components + hooks), no router, no state library |
| Language | TypeScript 6 (`verbatimModuleSyntax`, `noUnusedLocals`, `erasableSyntaxOnly`) |
| Build / dev server | Vite 8 with `@vitejs/plugin-react` |
| Lint | Oxlint (`react/rules-of-hooks` as error) |
| HTTP | Native `fetch`; no axios/react-query |
| Styling | One plain CSS file (`App.css`), class-based, no CSS framework |

The only runtime dependencies are `react` and `react-dom`.

---

## Running

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc -b && vite build
npm run lint       # oxlint
```

The backend must be running on port 8000. `vite.config.ts` proxies every
`/api` request to `http://127.0.0.1:8000`, so the browser sees a single
origin and the code uses relative URLs (`/api/documents`). No API base URL
configuration exists or is needed in dev.

---

## File map

```
frontend/
  index.html                    mount point, loads /src/main.tsx
  vite.config.ts                React plugin + /api proxy
  src/
    main.tsx                    createRoot + <StrictMode><App/>
    App.tsx                     top-level state, data loading, all handlers
    api.ts                      typed fetch wrappers, one per endpoint
    types.ts                    TypeScript mirrors of the API's JSON
    labels.ts                   line-key → display label, and display order
    format.ts                   currency and date formatting
    App.css / index.css         layout + component styles / page base
    components/
      UploadPanel.tsx           file picker + "Extracting…" state
      DocumentSidebar.tsx       list of documents, select, two-step delete
      PropertyCard.tsx          one property: income, expenses, totals
      LineItemRow.tsx           one editable row
      HistoryPopover.tsx        change-history table for one row
```

---

## Component tree

```
App
├── <aside class="sidebar">
│   ├── UploadPanel                  onUpload(file)
│   └── DocumentSidebar              documents, selectedId, onSelect, onDelete
│
└── <main class="main">
    ├── error banner                 (App-level error string)
    ├── empty-state message          (no document selected)
    └── selected document
        ├── header: filename + warnings list
        ├── PropertyCard × N         one per property, in API order
        │   └── LineItemRow × 15     2 income + 13 expense
        │       └── HistoryPopover   only while open
        └── footer: grand total net income
```

Layout is a fixed 280px sidebar plus a flexible main area. Property cards sit
in an auto-fit grid (`minmax(340px, 1fr)`), so three properties lay out
side by side on a wide screen and stack on a narrow one.

---

## State ownership

All server data lives in `App`. Children are almost entirely props-in,
callbacks-out.

| State | Owner | Purpose |
|---|---|---|
| `documents: DocumentSummary[]` | `App` | Sidebar list |
| `selectedId: number \| null` | `App` | Which document is open |
| `document: Document \| null` | `App` | The full open document, with nested properties and totals |
| `error: string \| null` | `App` | Banner shown above the document |
| `confirmingId`, `deletingId` | `DocumentSidebar` | Two-step delete UI state |
| `busy`, `error` | `UploadPanel` | Upload spinner text, local error |
| `draft`, `saving`, `showHistory` | `LineItemRow` | The text being typed, a save in flight, popover open |
| `changes`, `error` | `HistoryPopover` | Fetched history rows |

There is **no client-side computation of totals**. Every number shown in a
totals row or the grand total comes from the server response.

---

## Data flows

### Initial load

```
mount → listDocuments() → setDocuments
```

Nothing is selected, so the main area shows *"Select or upload a document to
view its extracted data."*

### Select a document

```
onSelect(id) → setSelectedId(id)
   └─ effect on [selectedId]:
        AbortController → getDocument(id, signal) → setDocument
        cleanup: controller.abort()
```

The `AbortController` matters: if the user clicks document 1 then quickly
document 2, the effect cleanup aborts the request for 1. A slow response for
the previously selected document can therefore never overwrite the current
one. `AbortError` is filtered out and not shown as an error.

### Upload

```
UploadPanel: file chosen
  → App.handleUpload(file)
      → extractDocument(file)         POST /api/extract (multipart)
      → refreshDocumentList()
      → setSelectedId(doc.id); setDocument(doc)
```

The POST response is the full extracted document, so it is shown immediately.
Because `selectedId` changed, the select effect then fires one more
`getDocument`, a redundant but harmless re-fetch. The file input is reset
(`value = ""`) in `finally`, so choosing the same file twice re-triggers
`onChange`.

### Edit a number

```mermaid
sequenceDiagram
    participant U as User
    participant R as LineItemRow
    participant A as App
    participant S as Server

    U->>R: types in input (draft state only)
    U->>R: blur or Enter
    R->>R: parse; NaN → revert; unchanged → stop
    R->>A: onSave(item.id, parsed)
    A->>S: PATCH /api/line-items/{id}
    S-->>A: 200 (or an error)
    A->>S: GET /api/documents/{selectedId}  (always, in finally)
    S-->>A: fresh document with recomputed totals
    A->>R: re-render with server values
```

Rules in `LineItemRow.commit`:

1. `Number(draft)`. If `NaN`, put back the current value and do nothing.
2. If it equals the current value, do nothing (no request, no history row).
3. Otherwise disable the input (`saving`), call `onSave`, re-enable in `finally`.

Enter blurs the input, so Enter and blur share the same `commit` path.

`App.handleLineItemSave` reloads the document in `finally`: on success to pick
up new totals, on failure so the totals shown are the persisted ones. The
reload is the reason totals are always trustworthy: the client never sums
anything.

The edit is sent with `changed_by = "user"` (hardcoded) and no note.

### View history

```
click "history" → showHistory = true → <HistoryPopover>
   effect: getLineItemHistory(lineItemId) → setChanges
click "×" → showHistory = false → popover unmounts
```

History is fetched every time the popover opens (it unmounts on close), so it
is always current. Rows are shown oldest first: *When, By, Old, New, Note*. A
missing old value (the initial extraction) shows as `—`.

### Delete a document

```
click 🗑 → confirmingId = id  → shows [Delete?] [✕]
click Delete? → deletingId = id → App.handleDelete(id)
    → deleteDocument(id) → refreshDocumentList()
    → if it was open: setSelectedId(null); setDocument(null)
```

Deletion is a two-step confirm inline in the row, with no modal. The confirm
button shows `…` and disables while the request runs. Cancel (`✕`) clears the
confirming state.

---

## API layer

`api.ts` exports one function per endpoint. All go through a shared
`handle<T>(res)` that returns parsed JSON on success and otherwise throws
`Error("<status> <statusText>: <response body>")`. That includes the backend's
FastAPI `{"detail": "..."}` body, so the user sees the server's reason.

| Function | Request | Returns |
|---|---|---|
| `listDocuments()` | `GET /api/documents` | `DocumentSummary[]` |
| `getDocument(id, signal?)` | `GET /api/documents/{id}` | `Document` |
| `extractDocument(file)` | `POST /api/extract`, `FormData{file}` | `Document` |
| `updateLineItem(id, value, changedBy, note?)` | `PATCH /api/line-items/{id}`, JSON | `LineItem` |
| `getLineItemHistory(id)` | `GET /api/line-items/{id}/history` | `LineItemChange[]` |
| `deleteDocument(id)` | `DELETE /api/documents/{id}` | `void` (204, no JSON parse) |

`deleteDocument` repeats the error formatting instead of using `handle`,
because a 204 has no body to parse. `extractDocument` does not set
`Content-Type`, so the browser adds the multipart boundary itself.

Endpoint behaviour is documented in [BACKEND_LOGIC.md](BACKEND_LOGIC.md).

---

## Types and label mapping

**`types.ts`** mirrors `backend/schemas.py` field for field: `LineItem`,
`Totals`, `Property`, `Document`, `DocumentSummary`, `LineItemChange`.
`LineItem.source` is the union `"extracted" | "manual"`. Datetimes are
`string` (ISO). Line items are `Record<string, LineItem>` keyed by the
form-line key (`gross_rents`, `advertising`, ...).

**`labels.ts`** turns keys into what the tax form prints:

```ts
INCOME_LABELS   = { gross_rents: "2a  Gross rents", other_income: "2b  Other income" }
EXPENSE_LABELS  = { advertising: "3  Advertising", ..., other_deductions: "17  Other deductions" }
INCOME_ORDER    = Object.keys(INCOME_LABELS)
EXPENSE_ORDER   = Object.keys(EXPENSE_LABELS)
```

The `*_ORDER` arrays come from key insertion order, which fixes the row
sequence to match the form (2a, 2b, 3 … 14, 17). `PropertyCard` iterates
these arrays, not the API object, so the display order never depends on
JSON key order, and a key the UI does not know about is not rendered.

`labels.ts` is a **manual mirror** of `form8825/schema.py`'s `LINE_ITEM_MAP`;
the two are in different languages with no shared schema tooling. Change one
and you must change the other. See
[EXTRACTION_LOGIC.md](EXTRACTION_LOGIC.md#schemapy-the-vocabulary).

---

## Component reference

### `App`
Owns the four pieces of server state and every handler
(`handleUpload`, `handleDelete`, `handleLineItemSave`,
`reloadSelectedDocument`). Renders the shell, the error banner, the warnings
list, the property cards, and the grand-total footer.

Warnings from the extractor appear under the filename as amber `⚠` notices,
one per message.

### `UploadPanel`
A styled `<label>` wrapping a hidden `<input type="file" accept="application/pdf">`.
Shows `Extracting…` and disables the input while `onUpload` is pending.

### `DocumentSidebar`
Lists `filename`, `N property/properties · <date>`, highlights the selected
row, and hosts the inline delete confirm. Shows *"No documents uploaded yet."*
when empty. Pluralisation is handled (`1 property`, `3 properties`).

### `PropertyCard`
Header: `Property <letter>` and the address, or `(no address)` if empty. Body:
an *Income* section then an *Expenses* section of `LineItemRow`s, then a
totals block: **Total rental income (2c)**, **Total expenses (18)**,
**Net income (19)** (emphasised). The line numbers in those labels are static
text; the values come from `property.totals`.

### `LineItemRow`
One `<tr>`: label, number input, an `edited` badge, a `history` link.

- Rows with `source === "manual"` get a `manual-row` class (amber input border and background) and the `edited` badge, so corrected values are visible at a glance.
- The input is `type="number"`, right-aligned.
- Local `draft` holds the text while typing, so nothing is sent per keystroke.

### `HistoryPopover`
Absolutely positioned under the `history` link (`.history-cell` is
`position: relative`). Three states: *Loading…*, an error, or the table /
*No changes recorded.*

---

## Formatting

`format.ts`:

- `formatCurrency(n)`: `$1,234`, with the sign in front of the dollar sign for negatives: `-$1,234`. Whole dollars, `en-US` grouping.
- `formatDateTime(iso)`: `new Date(iso).toLocaleString()` in the viewer's locale and timezone.

Numbers inside inputs are shown raw (`182400`), not formatted, because
`type="number"` cannot display grouping separators.

---

## Styling

`App.css` holds everything: flex shell, sidebar, cards, tables, history
popover, warning and error colours. `index.css` sets the page background and
`color-scheme: light`, and the value inputs also set `color-scheme: light`
explicitly. There is no dark theme. Colour language: blue for actions, amber
for "manually edited" and warnings, red for errors and delete, near-black for
the grand-total bar.

---

## Error handling

There are two independent error slots, both plain strings:

| Slot | Set by | Shown |
|---|---|---|
| `App.error` | initial list load, document load, upload, delete, save, reload | red text above the document |
| `UploadPanel.error` | exceptions thrown out of `onUpload` | red text under the upload button |

The string is `String(e)`, so it reads `Error: 400 Bad Request: {"detail":"..."}`.
`App.error` is cleared at the start of an upload, delete, or save.

Server-side extraction *warnings* are not errors: they arrive on the document
and render as amber notices next to a successfully shown document.

---

## Design decisions

- **Server is the single source of truth for numbers.** The client re-fetches after every edit instead of patching local state, so the totals, `source` flag, and `updated_at` shown always match what the database and audit log hold.
- **Save on blur/Enter, not on keystroke.** One request and one history row per intentional edit.
- **Cancel stale requests.** `AbortController` on document loads avoids the classic out-of-order response bug.
- **No client cache or state library.** With one open document and a handful of endpoints, `useState` plus refetch is the smallest thing that is correct.
- **Display order is defined by the UI** (`*_ORDER`), independent of the API.

---

## Known limitations

- **A rejected edit leaves the rejected number in the input.** `LineItemRow` initialises `draft` from `item.value` once and never re-syncs. On a failed save, `App` reloads the document (so the totals are correct and the error shows), but the row is keyed by `item.id` and keeps its old `draft`, so the input still displays the value that was not saved. Successful saves are fine because `draft` already equals the new value. Fix: sync `draft` from `item.value` in an effect, or key the row on `item.value` and `item.updated_at`.
- **An empty input saves `0`.** `Number("")` is `0`, not `NaN`, so clearing a field and tabbing out records a change to zero.
- **Decimals are accepted by the input but rejected by the server.** The API takes whole-dollar integers, so `12.5` returns `422` and is shown as an error.
- **Timestamps display shifted.** The backend sends UTC without a timezone marker, and `new Date()` reads that as local time, so `formatDateTime` is off by the viewer's UTC offset until the backend attaches one. See [BACKEND_LOGIC.md](BACKEND_LOGIC.md#known-limitations).
- **`changed_by` is hardcoded to `"user"`.** There is no login.
- **Two error slots.** `App` catches upload errors itself, so `UploadPanel`'s own `catch` is effectively unused; upload failures appear in the main banner, not under the button.
- **History popover has no click-outside or Escape handling**; it closes only via `×`.
- **Extra fetch after upload** (see [Upload](#upload)).
- **`labels.ts` must be kept in sync by hand** with the Python schema.
- **No automated UI tests.** The frontend has no test tooling installed; see [WHATS_NEXT.md](WHATS_NEXT.md).
- **Page `<title>` is the Vite default** (`frontend`).
