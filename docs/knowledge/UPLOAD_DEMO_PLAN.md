# PayFlow — Live Upload Demo Plan
_Research + plan only. No code was changed to produce this. Goal: upload a real invoice PDF in the browser → it's read LIVE by Gemini → runs the full pipeline. Enables a happy path + 3 edge cases on camera._

## 0. TL;DR
- The backend upload path **already exists** (`POST /runs/upload`) and `orchestrator.resolve_pdf` already looks in `data/uploads/`. **Only the frontend needs wiring** (~45 lines across 2 files) + a client-side object-URL for preview. **No backend change required.**
- Provider **must be `gemini`** for uploads (fixture mode can't extract a file it has no fixture for). It is currently `gemini` in `backend/.env`.
- A **freshly-made PDF has a novel sha256 → cache miss → real live Gemini call**, then it's cached (append-only) so a re-run in the demo is instant. The cache can never return a stale fixture for a new file (lookup is by content hash).

---

## 1. Wiring plan (frontend only — precise, not implemented)

| File | Add | ~LOC | Notes |
|------|-----|------|-------|
| `frontend/src/api.ts` | `uploadRun(file: File): Promise<string>` | ~15 | **Must use raw `fetch(\`${API_BASE}/runs/upload\`, {method:"POST", body: formData})` — NOT `tryFetch`.** `tryFetch` injects `Content-Type: application/json`, which breaks multipart (the browser must set its own `multipart/form-data; boundary=…`). Build a `FormData`, `fd.append("file", file)`. Return `(await res.json()).run_id`. Fall back to mock id on failure like `createRun`. |
| `frontend/src/pages/LiveRun.tsx` | file `<input type="file" accept="application/pdf">` (hidden, triggered by the drop-zone), `uploadedFile` + `uploadedUrl` state, a real `onDrop`/`onChange`, and a branch in `start()` | ~30 | See below. |

**LiveRun changes:**
- The drop-zone `onDrop` (currently line ~153) only does `setFileName(f.name)` — it does **not** upload. Change it (and add an `onChange` on a hidden file input) to: `setUploadedFile(f); setUploadedUrl(URL.createObjectURL(f)); setFileName(f.name);`
- In `start()` (line ~47): `const id = uploadedFile ? await uploadRun(uploadedFile) : await createRun(fileName);` — then `streamRun(id, …)` exactly as today.
- **Preview:** uploads are **not** served by `/api/invoices` (that route only serves `data/invoices/`). Simplest fix = **client-side object URL**: pass `fileUrl={uploadedFile ? uploadedUrl : invoiceUrl(fileName)}` to `<DocumentPreview>`. `DocumentPreview` already renders any `fileUrl` in an `<iframe>`. Zero backend change. (Alternative: add `GET /uploads/{name}` serving `data/uploads/` — more work, unnecessary.)
- On `reset()`/new pick, `URL.revokeObjectURL(uploadedUrl)` and clear `uploadedFile` so choosing a corpus invoice from the dropdown still works.

**Data-source mode:** set the sidebar toggle to **"live"** (or "auto") so `useMock()` is false and the real backend is hit. In "mock" mode upload is bypassed.

---

## 2. Uploadable demo invoices — specs (consistent with the seeded masters)

All values below are quoted from `data/masters/*.json`. Use **fresh invoice numbers/dates** (shown) so each PDF has a novel hash → real Gemini. Print the **vendor legal name exactly** and **"PO Number: PO-XXXX"** clearly so extraction matches the masters.

### ✅ HAPPY PATH → APPROVE  (3-way match, clean)
- **Vendor:** `Acme Corporation Inc.` (V001, approved, GL 5010 / CC-300) · **PO:** `PO-1001` (po_total **$12,000**, `requires_goods_receipt=true`, GR-9001 received $12,000)
- **Line:** Enterprise Laptop 14in i7/32GB · qty 10 · unit $1,200 · **$12,000** · **Subtotal 12,000 / Tax 0 / Total 12,000 USD**
- **Invoice #** `ACM-2026-501` · **Date** 2026-08-27
- **Why APPROVE:** vendor name = 100% match; 3-way: invoice 12,000 == PO 12,000 == GR 12,000; within tolerance; GL coding full-confidence (0.95); no dup (history is 11,800/12,200 → >$118 apart, no amount hit); not anomalous. → `OK_MATCH` / `OK_CLEAN`.

### ⏸️ EDGE 1 — Amount over PO → HOLD  (financial control + tax nuance)
- **Vendor:** `Stark Logistics LLC` (V005, approved) · **PO:** `PO-1004` (po_total **$10,000**, 2-way, `cumulative_billed=0`)
- **Line:** Regional freight & distribution - Q3 (rate revision) · qty 1 · unit **$10,300** · **Subtotal 10,300 / Tax 800 / Total 11,100 USD**
- **Invoice #** `STK-2026-880` · **Date** 2026-08-27
- **Why HOLD:** engine compares **goods subtotal 10,300 vs PO 10,000 = +3.0%**, over the tighter of ±1%/±$25 (=$25). Tax/freight excluded from the check. Fires `HOLD_OVERBILL` (billed 10,300 > PO×1.01 = 10,100; also `HOLD_TOLERANCE`). **Narration gold:** "the total is $11,100, but I only compare the $10,300 of *goods* to the $10,000 PO — still 3% over, so hold. The tax wasn't the problem."

### ⏸️ EDGE 2 — Spend anomaly → HOLD  (fraud instinct)
- **Vendor:** `Cyberdyne Systems Corp` (V007, approved, GL 5010/CC-300) · **PO:** `PO-1006` (po_total **$40,000**, 3-way, GR-9006 $40,000)
- **Line:** Data center server rack (fully populated) · qty 4 · unit $10,000 · **Subtotal 40,000 / Tax 0 / Total 40,000 USD**
- **Invoice #** `CY-2026-990` · **Date** 2026-08-27
- **Why HOLD:** invoice matches PO **and** GR perfectly — but Cyberdyne's history is $1,900/$2,100/$2,000/$2,200 (mean ≈ $2,050, max $2,200). $40,000 is **>5× mean** and **>2× max** → `HOLD_ANOMALY` (precedence: anomaly HOLD beats the clean match). **Narration gold:** "it matches the PO on paper, but it's ~20× this vendor's normal spend — exactly how a keying error or a compromised vendor slips through, so a human confirms first."

### ✅ EDGE 3 — PO-bypass under threshold → APPROVE + finance notice  (policy, nothing silent)
- **Vendor:** `Umbrella Facilities Corp` (V004, approved, **`po_bypass_allowed=true`**, GL 5040/CC-100) · **PO:** none
- **Line:** Emergency HVAC filter replacement · qty 1 · unit $385 · **Subtotal 385 / Tax 0 / Total 385 USD** — **do NOT print a PO number**
- **Invoice #** `UMB-2026-118` · **Date** 2026-08-27
- **Why APPROVE+notify:** no PO, amount **$385 < $500** bypass limit, vendor approved + bypass-allowed → `OK_BYPASS`, auto-approve **and emit a finance notification**. **Narration gold:** "small spend from a trusted facilities vendor — no PO needed, auto-approved, but it pings finance so it's never silent."

**Recommended set = these 4 (happy + 3).** They span match/tolerance, fraud pattern, and policy — three different kinds of judgment, two APPROVEs and two HOLDs.

**Swap-in alternates (if you want a REJECT or a duplicate):**
| Scenario | Vendor / PO | Amount | Trigger | Decision |
|---|---|---|---|---|
| Fuzzy duplicate | `Wayne Consulting Group` V006 / PO-1010 | $7,500, inv# `INV-WC-2002`, date 2026-06-18 | matches historical INV-WC-2001 ($7,500, 2026-06-15) on amount+date+near inv# → score ≥70 | `HOLD_DUP_FUZZY` |
| Unapproved vendor | `Ghost Supplies LLC` V008 / PO-1007 | $3,000 | vendor `approved=false` | `HOLD_VENDOR_UNAPPROVED` |
| Exact duplicate | `Wayne Consulting Group` V006 | $7,500, inv# `INV-WC-2001`, date 2026-06-15 | exact key hit vs history | `REJECT_DUP_EXACT` |

---

## 3. How to produce the PDFs (specify — do NOT build now)
- **Recommended:** a small standalone script `scripts/make_demo_uploads.py` that reuses the reportlab layout helpers from `scripts/generate_corpus.py`, writing the 4 PDFs to a **non-corpus** folder (e.g. `~/Desktop/payflow_demo/` or `/tmp/payflow_demo/`). **Do NOT write into `data/invoices/`** — that's the cached corpus; a file there would get a pinned fixture and skip live Gemini.
- **Even more convincing on camera:** make one or two in a real invoice template (Google Docs / Canva / an online invoice generator) and export to PDF — guaranteed novel hash, looks like a real vendor document. Keep the vendor legal name + PO number + line items + totals exactly as specified above.
- Each fresh PDF → novel sha256 → live Gemini extraction on first upload; it then caches so re-runs are instant.

---

## 4. Upload-demo run sheet

**Pre-flight (once, before recording):** `./demo` up; browser at `http://localhost:5173`; sidebar **Data source → live** (green dot); optionally set `STAGE_DELAY_MS=150` in `backend/.env` for snappier non-extraction stages; have the 4 PDFs on the desktop. Do a **private practice upload** of each so you know the timing (this also warms the cache, but for the *recording* use fresh copies / a fresh filename if you want a truly cold live call).

| # | Action | What you'll see | One-line narration |
|---|--------|-----------------|--------------------|
| 1 | Drag **Acme $12,000** into the drop-zone | stepper runs, PDF left, fields right → ✅ APPROVE | "Real invoice, never seen before — Gemini reads it live, it 3-way matches the PO and goods receipt, straight-through approve." |
| 2 | Drag **Stark $10,300** | ⏸️ HOLD | "Goods are 3% over the PO — held. Notice it ignored the tax and only compared the goods value." |
| 3 | Drag **Cyberdyne $40,000** | ⏸️ HOLD (anomaly) | "Matches the PO exactly — but it's 20× this vendor's normal spend, so we flag it before paying." |
| 4 | Drag **Umbrella $385** | ✅ APPROVE + notice | "Tiny spend from a trusted vendor, no PO needed — auto-approved, but finance gets pinged. Nothing happens silently." |
| 5 | Click **Open audit trail** on a HOLD | stage timeline w/ rule + values + actor | "Every decision cites the exact numbers it compared — this is what the AP clerk and the auditor see." |
| 6 | Go to **Dashboard** | KPIs, status donut, top exceptions | "Across all runs: our straight-through rate, and why the rest were held." |

**Gemini latency on camera:** the `EXTRACTED` stage shows a "Reading document…" spinner for ~2–6s on a real call — **talk over it** ("it's reading the layout, line items, tax now"); the spinner *proves* it's live. Other stages are fast (`STAGE_DELAY_MS`). If a call is ever slow/stalls, you can re-drag the same file — the second time is cached and instant.

---

## 5. Rename Verdict → PayFlow — one-pass checklist

**MUST change (user-visible):**
| File / line | Current | → |
|---|---|---|
| `frontend/src/components/Layout.tsx:61` | sidebar brand **"Verdict"** | **PayFlow** |
| `frontend/index.html:10` | `<title>Verdict — Invoice-to-Decision</title>` | PayFlow — … |
| `frontend/src/components/Stepper.tsx:23` | DECIDED label **"Verdict + route"** | "Decision + route" |
| `backend/app/main.py:27` | `FastAPI(title="Verdict", …)` (shows in /docs) | title="PayFlow" |
| `README.md:1`, docs headers in `docs/knowledge/*.md`, `docs/superpowers/specs/2026-08-30-verdict-design.md:1` | "Verdict" titles | PayFlow |
| `demo:2` comment | "Boots Verdict…" | PayFlow |
| `scripts/generate_corpus.py:463` | PDF footer "Verdict AP - synthetic test document" | PayFlow AP … |

**Optional / internal (safe to leave; changing localStorage keys just resets local prefs):**
- Component identifier `VerdictCard` (`frontend/src/components/VerdictCard.tsx` + imports in LiveRun/RunDetail) — internal name, not shown to users. Renaming touches 4 files; cosmetic.
- localStorage keys `verdict-mode` / `verdict-theme` / `verdict-actions` (api.ts, Layout.tsx, notes.ts) — internal.
- `frontend/package.json:2` name `verdict-frontend`; module docstrings across `backend/app/**`; `DB_PATH=verdict.db`.
- **Do NOT rename the repo folder** `~/payflow/` — the running servers, `./demo`, and all relative paths depend on it; renaming mid-demo breaks everything. The folder name is invisible in the product.

**Minimal high-impact pass = the 3 on-screen strings:** Layout brand, index.html `<title>`, Stepper DECIDED label. Those are the only "Verdict" words a viewer actually sees in the app.
