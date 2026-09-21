# Form 8825 extraction pipeline

Original assignment: [task_input_files/README.txt](task_input_files/README.txt). PDF failure modes, text-layer detection and scanned-input design (Task 1 questions): [NOTES.md](NOTES.md). What's left (Task 4 bonus + OCR next steps): [WHATS_NEXT.md](WHATS_NEXT.md).

## Layout

```
form8825/          extraction script (Task 1 & 2) - the core PDF -> JSON pipeline, standalone CLI
testdata/          generates the multi-property test fixture (Task 2)
task_input_files/  the original assignment files, untouched
backend/           FastAPI + SQLite API (Task 3) - imports form8825 to run extraction on upload
frontend/          Vite + React UI (Task 3)
```

`form8825/` has no dependency on `backend/` - it's a standalone library with its own CLI. `backend/` depends on `form8825/` (via `backend/crud.py`), not the other way around.

## Setup

Prerequisites: Python 3.11+ and Node.js 20+.

**1. Clone the repo and set up the Python environment (plain venv + pip, no uv needed):**

```bash
git clone https://github.com/raj-adroit/form8825-pipeline.git
cd form8825-pipeline

python -m venv .venv

# activate it
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate         # Windows (cmd or PowerShell)

pip install -r requirements.txt
```

Every command below assumes this venv is activated (you'll see `(.venv)` in your prompt).

**2. Set up the frontend:**

```bash
cd frontend
npm install
cd ..
```

That's it - see the commands below to run the extractor CLI or the full stack.

<details>
<summary>Prefer <a href="https://docs.astral.sh/uv/">uv</a> instead of plain pip?</summary>

```bash
pip install uv   # or the installer script from the uv docs
uv sync          # replaces the venv/pip steps above
```

Then prefix every Python command below with `uv run` (e.g. `uv run python -m form8825.cli ...`, `uv run uvicorn backend.main:app --reload --port 8000`) instead of activating the venv.
</details>

## Task 1 & 2 - run the extractor

```bash
python -m form8825.cli task_input_files/f8825.pdf -o out.json
python -m form8825.cli f8825_multi.pdf -o out_multi.json
```

Regenerate the Task 2 fixtures from `testdata/source.py`:

```bash
python -m testdata.make_fixture
```

That writes three files from one set of source data, so the PDFs and the expected JSON can't drift apart:

| File | What it is |
|---|---|
| `f8825_multi.pdf` | Properties A/B/C written into the IRS's own fillable Rev. 12-2025 form — the same revision, and the same AcroForm shape, as the client's input |
| `f8825_multi_flat.pdf` | The same data as a flattened form in the older Rev. 11-2018 geometry, covering 8825s that arrive printed-to-PDF |
| `f8825_multi_expected.json` | The expected extraction result; **both** PDFs must extract to it |

## Task 3 - run the full stack

Backend (from the repo root):

```bash
uvicorn backend.main:app --reload --port 8000
```

Frontend (in a second terminal):

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. Upload a PDF, edit any income/expense number, and the totals and grand total recalculate immediately; every edit is recorded and visible via the "history" link on each row. The SQLite file (`backend/form8825.db`) is created on first run and is gitignored.

## Design notes

- **DB schema**: `documents` -> `extraction_runs` -> `properties` -> `line_items`, with an append-only `line_item_changes` audit log. Totals are never stored - they're computed from `line_items` on every read, so they can't drift from the underlying numbers. See [backend/models.py](backend/models.py).
- **API**: `POST /api/extract` (upload, runs extraction, persists), `GET /api/documents`, `GET /api/documents/{id}`, `PATCH /api/line-items/{id}` (edit + audit), `GET /api/line-items/{id}/history`. See [backend/main.py](backend/main.py).
- **Extraction algorithm**: see the module docstring in [form8825/extract.py](form8825/extract.py) - values are matched to a form line by a reprinted line-number anchor, and to a property column by comparing each value's right edge against the column header x-positions, so it generalizes across 1-4 populated columns. Both the anchor column and the header row are located on the page rather than hardcoded, because the IRS moves them between form revisions.
- **Fillable vs. flattened forms**: on the IRS's own fillable 8825 the page text is just the blank template and every entry lives in an AcroForm field, so text extraction alone silently returns an empty form. Filled fields are converted to word-shaped records using their widget rectangles and merged into the same word list as the printed text, which means one code path covers both shapes - and covers the Rev. 12-2025 continuation page, where even the property letters are typed in rather than printed. See [NOTES.md](NOTES.md).
