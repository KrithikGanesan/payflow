# 05 · Extraction

> PayFlow; code still says "Verdict" in places (see `00_INDEX.md`). All references are `backend/app/extraction/`.

## Entrypoint & provider factory (`interface.py`)
`extract(pdf_path) -> InvoiceExtract`:
```
sha = cache.sha256_of_pdf(path)
cached = cache.cache_read(sha)          # always allowed (deterministic replay)
if cached: return validate(cached)      # re-validate — idempotent, fills validation + _overall
result = get_provider().extract(path)   # provider chosen by EXTRACTION_PROVIDER
result = validate(result)
cache.cache_write(result, sha)          # only if EXTRACTION_CACHE=1 and no file yet
return result
```
`get_provider(name=None)` reads `EXTRACTION_PROVIDER` (default `gemini`) and **lazily** imports the chosen
provider — selecting `fixture` never imports `google-generativeai`; selecting `gemini` never needs Ollama.
Valid values: `gemini | ollama | fixture` (anything else raises `ValueError`).

## Gemini provider (`gemini.py`, default; model `gemini-2.0-flash`)
Sends the PDF **two ways at once** for accuracy:
1. **Raw PDF bytes** inline (`{"mime_type":"application/pdf","data":…}`) — Gemini reads layout and OCRs scanned pages.
2. **pdfplumber text layer** (`extract_text_layer`) — exact glyphs on machine-readable PDFs, so the model transcribes digits rather than guessing. Empty string on scanned PDFs (falls back to pure vision).

`build_prompt(text_layer)` = the schema prompt + the text layer marked "authoritative for exact digits" (or a
"no text layer, OCR the image" note). Generation config pins `temperature: 0.0` and
`response_mime_type: "application/json"`. The provider **constructs without a key**; only `extract()` requires
`GEMINI_API_KEY` (else a clear `RuntimeError` pointing at `EXTRACTION_PROVIDER=fixture`).

### The forced JSON schema (`SCHEMA_PROMPT`)
Pins the exact `InvoiceExtract` shape and hard rules: `doc_type` ∈ {INVOICE, CREDIT_MEMO, STATEMENT, OTHER};
**"NEVER GUESS — return null (or [] for line_items)"**; numbers raw (no symbols/separators); **credit memos as
negative numbers**; `tax_rate` as a decimal fraction (8% → 0.08); a per-field `confidence` map (0..1); prefer the
text layer's digits when it disagrees with the image. `parse_invoice_json` defensively coerces the response:
strips code fences / prose to the outer `{…}`, normalizes `doc_type` (unknown → OTHER), rebuilds `line_items`
into `LineItem`s, forces `confidence` to `{str: float}`, and **drops any provider-supplied `validation`** (never
trusted — PayFlow computes it).

## Fixture provider (`fixture_provider.py`, key-free)
`extract(pdf)` = `sha256(pdf)` → `cache_read(sha)`; returns the stored `data/fixtures/<sha>.json`, or raises a
clear `FileNotFoundError` naming the expected path if none exists. This is the same store the cache writes to,
so hand-authored ground-truth fixtures and previously-cached live runs are both honoured — the whole app runs
with no key. It is the default for the demo and for `scripts/smoke_test.py`.

## Ollama provider (`ollama.py`, local fallback)
Text-layer only (`urllib` to `http://localhost:11434/api/generate`, `format:"json"`, `temperature:0`), reusing
the gemini prompt + parser. Errors clearly on a scanned PDF (no text layer) or an unreachable server. Import-safe
with no server running.

## Cache (`cache.py`) — content-addressed, append-only
- **Key:** `sha256_of_pdf(path)` (hex of the file bytes). Fixture path = `data/fixtures/<sha>.json`.
- **`cache_read(sha)`:** always allowed (independent of `EXTRACTION_CACHE`) so fixtures/prior runs replay deterministically; a corrupt file returns `None` (degrades to a fresh extraction rather than crashing).
- **`cache_write(extract, sha)`:** a **no-op unless `EXTRACTION_CACHE=1`**, and **never clobbers** an existing file (append-only) — a ground-truth fixture is never overwritten. Returns the path if written.
- **Why:** deterministic demos (same PDF → same JSON), key-free operation, and a novel upload still hits the model (its hash isn't in the store).

## Validation & confidence (`validate.py`) — pure, idempotent
`validate(extract)` runs after the provider and before the engine, mutating and returning the same object.

**1. Arithmetic** (the strongest signal), written to `extract.validation`:
- `check_line_items_sum`: Σ `line_items.amount` ≈ `subtotal` → `validation["line_items_sum_ok"]`.
- `check_subtotal_plus_tax`: `subtotal + tax + freight − discount` ≈ `total` → `validation["subtotal_plus_tax_ok"]`.
- Comparison uses a mixed tolerance `_approx` = `abs(a−b) ≤ max(0.01, 0.005·max|a,b|)` (a cent or 0.5%). Non-verifiable (missing fields) → `False`.

**2. Format plausibility** — currency ∈ a broad ISO-4217 set; each present date parses (`dateutil`); per-line and derived tax rate within 0–30%. A failed currency/date **lowers that field's confidence** to ≤ 0.30 (`_lower_field_conf`) so downstream gates can see which field is shaky. (Tax-rate failure feeds only the `_overall` signal — there is no `HOLD_TAX`.)

**3. Overall confidence** → `confidence["_overall"]` (a reserved meta key; underscore keys are meta, not fields):
```
overall = mean(self-reported per-field confidence, ignoring _-keys; 0.5 if none)
if not arithmetic_ok: overall = min(overall, 0.50) * 0.7   # heaviest, multiplicative penalty
if not currency_ok:   overall *= 0.90
if not dates_ok:      overall *= 0.92
if not tax_ok:        overall *= 0.90
overall = round(clamp(overall, 0, 1), 4)
```
A document whose money doesn't reconcile can never read as high-confidence, however confident the model claimed.

### Why `confidence_gate` ignores `_overall`
`_overall` is a **derived meta signal**, not a field the model read. `policy.confidence_gate` iterates
`confidence` for values `< 0.80` but skips keys starting `_` (`if not k.startswith("_")`). Before this fix a
live upload — where the provider returns strong per-field confidences but the *derived* `_overall` can sit just
under 0.80 — would spuriously `HOLD_LOW_CONFIDENCE`. Now only genuine per-field weakness (or an arithmetic
failure) trips the gate. Note the separate `decide._overall_confidence` (the number shown on the verdict) is
`min(min(all confidence values), gl.confidence)` — it does include `_overall` in its min, by design, as a
conservative display signal; it does **not** drive the HOLD.
