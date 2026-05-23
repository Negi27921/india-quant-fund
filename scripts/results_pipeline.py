"""
results_pipeline.py
───────────────────
Real-time BSE Earnings Results Pipeline

Flow:
  1. Fetch recent BSE filings — filter to Financial Results categories
  2. Deduplicate against quarterly_results Supabase table via filing_id
  3. For each new filing:
       a. Try to download & extract PDF text (pdfminer)
       b. Call DeepSeek R1 via NVIDIA NIM for structured JSON extraction
       c. Deterministic rating computed from extracted numbers (not AI opinion)
       d. Fetch live CMP + market cap via yfinance fast_info
       e. Upsert to quarterly_results table
       f. Push Telegram alert
  4. Exit cleanly — designed to run from GitHub Actions every 20 min

AI Model: NVIDIA NIM — deepseek-ai/deepseek-r1
  Why NIM over OpenRouter:
    • Direct NVIDIA inference — lower latency, dedicated capacity
    • DeepSeek R1 (reasoning model) produces more accurate number extraction
      from dense financial PDF text than V3 chat model
    • No routing overhead, no model-switch risk
  Fallback: OpenRouter deepseek/deepseek-chat if NIM key absent

Rating logic (deterministic Python, not AI opinion):
  Score = PAT_YoY_pts (0-4) + Rev_YoY_pts (0-1) + QoQ_momentum (-0.5 to +0.5)
    PAT YoY ≥ 30%  → 4 pts → Excellent 🚀
    PAT YoY 15-30% → 3 pts → Great     🟢
    PAT YoY  5-15% → 2 pts → Good      🔵
    PAT YoY -5–5%  → 1 pt  → Ok        🟡
    PAT YoY < -5%  → 0 pts → Weak      🔴
  Revenue YoY adds ±0.5 pts, QoQ momentum adds ±0.5 pts.
  When no numbers available: AI's rating field used as fallback.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from io import BytesIO

# ── Config ──────────────────────────────────────────────────────────────────
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY", "")
NVIDIA_API_KEY  = os.getenv("NVIDIA_API_KEY", "")        # primary
OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY", "")    # fallback
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "")

# NVIDIA NIM — DeepSeek R1 (reasoning, best for structured financial extraction)
NIM_MODEL       = "deepseek-ai/deepseek-r1"
NIM_ENDPOINT    = "https://integrate.api.nvidia.com/v1/chat/completions"
# Fallback via OpenRouter
OR_MODEL        = "deepseek/deepseek-chat"
OR_ENDPOINT     = "https://openrouter.ai/api/v1/chat/completions"

DASHBOARD_URL   = "https://luffy-labs.vercel.app"

# BSE categories that signal a results announcement
RESULT_CATEGORIES = {
    "Financial Results",
    "Financial Results-Audited",
    "Financial Results-UnAudited",
    "Outcome of Board Meeting",
    "Quarterly/Annual Financial Results",
}

RESULT_KEYWORDS = {
    "financial result", "quarterly result", "annual result",
    "half year result", "pat", "revenue", "profit", "earnings",
    "net profit", "q1 fy", "q2 fy", "q3 fy", "q4 fy",
}


# ── BSE Filing Fetch ─────────────────────────────────────────────────────────

def _fetch_bse_filings(pages: int = 2) -> list[dict]:
    """Pull recent BSE announcements across all categories."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":    "https://www.bseindia.com/",
        "Accept":     "application/json",
    }
    items: list[dict] = []
    for page in range(1, pages + 1):
        url = (
            "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
            f"?pageno={page}&strCat=-1&strPrevDate=&strScrip=&strSearch=P"
            "&strToDate=&strType=C&subcategory=-1"
        )
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            items.extend(data.get("Table", []))
        except Exception as exc:
            print(f"  [BSE] page {page} failed: {exc}")
        time.sleep(0.4)
    return items


def _is_results_filing(item: dict) -> bool:
    category = item.get("CATEGORYNAME", "").strip()
    headline = item.get("NEWSSUB", "").lower()
    if category in RESULT_CATEGORIES:
        return True
    return any(kw in headline for kw in RESULT_KEYWORDS)


# ── PDF Text Extraction ───────────────────────────────────────────────────────

def _extract_pdf_text(pdf_url: str, max_chars: int = 4000) -> str:
    """Download BSE PDF and extract plain text. Returns '' on any failure."""
    if not pdf_url or not pdf_url.endswith(".pdf"):
        return ""
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer":    "https://www.bseindia.com/",
        }
        req = urllib.request.Request(pdf_url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            pdf_bytes = resp.read()

        out = BytesIO()
        extract_text_to_fp(BytesIO(pdf_bytes), out, laparams=LAParams(), output_type="text")
        text = out.getvalue().decode("utf-8", errors="ignore")
        # strip noise: long runs of whitespace, form-feed chars
        text = re.sub(r"\f", "\n", text)
        text = re.sub(r" {4,}", "  ", text)
        text = re.sub(r"\n{4,}", "\n\n", text).strip()
        return text[:max_chars]
    except Exception as exc:
        print(f"  [PDF] extract failed for {pdf_url}: {exc}")
        return ""


# ── DeepSeek R1 via NVIDIA NIM (+ OpenRouter fallback) ───────────────────────

_SYSTEM = (
    "You are a senior Indian equity analyst. Extract financial results from BSE filing data. "
    "Return ONLY a valid JSON object — no markdown, no explanation, no code fences. "
    "For numbers in the PDF, use Crores (Cr) as the unit. "
    "If the PDF uses Lakhs, divide by 100 to convert to Crores."
)

_PROMPT_TMPL = """BSE Corporate Filing — Extract Quarterly Financial Results

Company  : {company}
BSE Scrip: {scrip_code}
Filed    : {dt}
Category : {category}
Headline : {headline}
{pdf_section}
---
TASK: Extract the financial results from the above data.
- Use EXACT numbers from the PDF/headline where present.
- For prior-quarter comparisons use numbers stated in the filing.
- Do NOT guess or hallucinate numbers — use null when genuinely unavailable.
- Identify which quarter (Q1/Q2/Q3/Q4 FY20XX) this result covers.

Return ONLY this JSON (no extra text, no markdown fences):
{{
  "quarter"         : "Q4 FY2026",
  "revenue_cr"      : 0,
  "other_income_cr" : null,
  "op_cr"           : null,
  "opm_pct"         : null,
  "pat_cr"          : 0,
  "eps"             : null,
  "revenue_qoq"     : null,
  "revenue_yoy"     : null,
  "op_qoq"          : null,
  "op_yoy"          : null,
  "pat_qoq"         : null,
  "pat_yoy"         : null,
  "eps_qoq"         : null,
  "eps_yoy"         : null,
  "revenue_prev_q"  : null,
  "revenue_prev_y"  : null,
  "pat_prev_q"      : null,
  "pat_prev_y"      : null,
  "eps_prev_q"      : null,
  "eps_prev_y"      : null,
  "sector"          : "Technology",
  "industry"        : "IT Services",
  "ai_rating"       : "Good",
  "insight"         : "Two concise sentences analysing this result and its market implications.",
  "report_time"     : "After Market Hours",
  "currency_unit"   : "Cr"
}}
"""


def _call_nim_deepseek(company: str, scrip_code: str, dt: str,
                        category: str, headline: str, pdf_text: str) -> dict | None:
    """Call NVIDIA NIM DeepSeek R1 (primary), fall back to OpenRouter DeepSeek-V3."""
    pdf_section = (
        f"\nPDF Extract ({len(pdf_text)} chars):\n{pdf_text}\n"
        if pdf_text else ""
    )
    prompt = _PROMPT_TMPL.format(
        company=company, scrip_code=scrip_code, dt=dt,
        category=category, headline=headline, pdf_section=pdf_section,
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": prompt},
    ]

    # ── Try NVIDIA NIM first ──────────────────────────────────────────────────
    if NVIDIA_API_KEY:
        print("    Using NVIDIA NIM — DeepSeek R1")
        payload = {
            "model": NIM_MODEL,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.1,
            "stream": False,
        }
        req = urllib.request.Request(
            NIM_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type":  "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
            raw = data["choices"][0]["message"]["content"].strip()
            # DeepSeek R1 wraps reasoning in <think>…</think> — strip it
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
            return json.loads(raw)
        except Exception as exc:
            print(f"    [NIM] failed: {exc} — falling back to OpenRouter")

    # ── Fallback: OpenRouter DeepSeek-V3 ─────────────────────────────────────
    if OPENROUTER_KEY:
        print("    Using OpenRouter — DeepSeek-V3")
        payload = {
            "model": OR_MODEL,
            "messages": messages,
            "max_tokens": 900,
            "temperature": 0.1,
        }
        req = urllib.request.Request(
            OR_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type":  "application/json",
                "HTTP-Referer":  DASHBOARD_URL,
                "X-Title":       "One Piece Quant — Results Pipeline",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            raw = data["choices"][0]["message"]["content"].strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
            return json.loads(raw)
        except Exception as exc:
            print(f"    [OpenRouter] failed: {exc}")

    print("    No AI key available — skipping extraction")
    return None


# ── Deterministic Rating Engine ───────────────────────────────────────────────
# Rating is computed from extracted numbers, NOT from AI opinion.
# AI's "ai_rating" field is only used when no numbers are available.
#
# Scoring table:
#   PAT YoY growth    Points   Base rating
#   ≥ 30%               4      Excellent
#   15 – 30%            3      Great
#    5 – 15%            2      Good
#   -5 –  5%            1      Ok
#    < -5%              0      Weak
#
# Modifiers (each ± 0.5):
#   Revenue YoY ≥ 15%  → +0.5
#   Revenue YoY  5-15% → +0.25
#   Revenue YoY < -5%  → -0.5
#   PAT QoQ ≥ 10%      → +0.5  (momentum)
#   PAT QoQ < -10%     → -0.5
#   OPM > 20%          → +0.25 (margin quality)
#   OPM < 5%           → -0.25
#
# Final score  ≥ 4.25 → Excellent | 3.25-4.25 → Great | 2-3.25 → Good
#              1-2    → Ok        | <1        → Weak

_SCORE_TO_RATING = [
    (4.25, "Excellent", "🚀"),
    (3.25, "Great",     "🟢"),
    (2.00, "Good",      "🔵"),
    (1.00, "Ok",        "🟡"),
    (0.00, "Weak",      "🔴"),
]

_RATING_NOTES = {
    "Excellent": "Strong broad-based growth — significant earnings beat",
    "Great":     "Solid YoY expansion, positive operating leverage",
    "Good":      "In-line to modest beat, stable fundamentals",
    "Ok":        "Mixed quarter — muted growth, watch guidance",
    "Weak":      "Earnings miss / profit decline — review triggers",
}


def _compute_rating(ai: dict) -> tuple[str, str]:
    """
    Returns (rating, rating_note). Uses deterministic scoring when numbers
    are available; falls back to AI's ai_rating field otherwise.
    """
    pat_yoy = ai.get("pat_yoy")
    rev_yoy = ai.get("revenue_yoy")
    pat_qoq = ai.get("pat_qoq")
    opm     = ai.get("opm_pct")

    # no numbers at all → use AI opinion
    if pat_yoy is None and rev_yoy is None:
        ai_r = ai.get("ai_rating", "Good")
        valid = {"Excellent", "Great", "Good", "Ok", "Weak"}
        r = ai_r if ai_r in valid else "Good"
        return r, _RATING_NOTES[r]

    # PAT YoY base score
    if pat_yoy is not None:
        if pat_yoy >= 30:   score = 4.0
        elif pat_yoy >= 15: score = 3.0
        elif pat_yoy >= 5:  score = 2.0
        elif pat_yoy >= -5: score = 1.0
        else:               score = 0.0
    elif rev_yoy is not None:
        # no PAT number — use revenue as proxy with compressed range
        if rev_yoy >= 20:   score = 3.0
        elif rev_yoy >= 10: score = 2.0
        elif rev_yoy >= 0:  score = 1.5
        else:               score = 0.5
    else:
        score = 1.0

    # Revenue YoY modifier
    if rev_yoy is not None:
        if rev_yoy >= 15:   score += 0.5
        elif rev_yoy >= 5:  score += 0.25
        elif rev_yoy < -5:  score -= 0.5

    # QoQ momentum modifier
    if pat_qoq is not None:
        if pat_qoq >= 10:   score += 0.5
        elif pat_qoq < -10: score -= 0.5

    # Margin quality modifier
    if opm is not None:
        if opm > 20:  score += 0.25
        elif opm < 5: score -= 0.25

    for threshold, label, _ in _SCORE_TO_RATING:
        if score >= threshold:
            return label, _RATING_NOTES[label]
    return "Weak", _RATING_NOTES["Weak"]


# ── yfinance Price Fetch ──────────────────────────────────────────────────────

def _fetch_price(symbol: str) -> dict:
    """Returns {cmp, market_cap, pe, ticker} using fast_info (never ticker.info)."""
    try:
        import yfinance as yf
        for suffix in (".NS", ".BO", ""):
            ticker = symbol + suffix
            t = yf.Ticker(ticker)
            fi = t.fast_info
            cmp = getattr(fi, "last_price", None) or getattr(fi, "regular_market_price", None)
            if cmp and cmp > 0:
                mc = getattr(fi, "market_cap", 0) or 0
                mc_cr = mc / 1e7 if mc else 0  # convert to Crores
                pe = None
                try:
                    pe = round(cmp / (t.fast_info.last_price / 1), 1) if cmp else None
                except Exception:
                    pe = None
                return {"cmp": round(float(cmp), 2), "market_cap": round(mc_cr, 2), "pe": pe, "ticker": ticker}
    except Exception:
        pass
    return {"cmp": None, "market_cap": 0, "pe": None, "ticker": None}


# ── Build Metrics Struct ──────────────────────────────────────────────────────

def _build_metrics(ai: dict) -> dict:
    def _mv(q1, q2, q3, qoq, yoy):
        return {"q1": q1 or 0, "q2": q2 or 0, "q3": q3 or 0, "qoq": qoq, "yoy": yoy}

    rev   = ai.get("revenue_cr") or 0
    rpq   = ai.get("revenue_prev_q") or 0
    rpy   = ai.get("revenue_prev_y") or 0
    pat   = ai.get("pat_cr") or 0
    ppq   = ai.get("pat_prev_q") or 0
    ppy   = ai.get("pat_prev_y") or 0
    eps   = ai.get("eps") or 0
    epq   = ai.get("eps_prev_q") or 0
    epy   = ai.get("eps_prev_y") or 0
    op    = ai.get("op_cr")
    opm   = ai.get("opm_pct")
    oi    = ai.get("other_income_cr")

    return {
        "sales":        _mv(rpq, rpy, rev, ai.get("revenue_qoq"), ai.get("revenue_yoy")),
        "other_income": _mv(0, 0, oi or 0, None, None),
        "op":           _mv(0, 0, op or 0, ai.get("op_qoq"), ai.get("op_yoy")),
        "opm":          _mv(0, 0, opm or 0, None, None),
        "pat":          _mv(ppq, ppy, pat, ai.get("pat_qoq"), ai.get("pat_yoy")),
        "eps":          _mv(epq, epy, eps, ai.get("eps_qoq"), ai.get("eps_yoy")),
    }


# ── Supabase Helpers ──────────────────────────────────────────────────────────

def _sb_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }


def _get_processed_filing_ids() -> set[str]:
    """Return set of already-processed filing_id values (last 7 days)."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return set()
    url = f"{SUPABASE_URL}/rest/v1/quarterly_results?select=filing_id&limit=500"
    try:
        req = urllib.request.Request(url, headers=_sb_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read())
        return {r["filing_id"] for r in rows if r.get("filing_id")}
    except Exception as exc:
        print(f"  [SB] get_processed_ids failed: {exc}")
        return set()


def _upsert_result(row: dict) -> bool:
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("  [SB] No credentials — skipping upsert")
        return False
    url = f"{SUPABASE_URL}/rest/v1/quarterly_results"
    headers = _sb_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    data = json.dumps(row, default=str).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as exc:
        print(f"  [SB] upsert failed: {exc}")
        return False


# ── Telegram Push ─────────────────────────────────────────────────────────────

_RATING_EMOJI = {
    "Excellent": "🚀", "Great": "🟢", "Good": "🔵", "Ok": "🟡", "Weak": "🔴",
}


def _send_telegram(row: dict) -> None:
    if not (TG_TOKEN and TG_CHAT_ID):
        return

    rating   = row.get("rating", "Good")
    emoji    = _RATING_EMOJI.get(rating, "📊")
    company  = row.get("company", "?")
    symbol   = row.get("symbol", "?")
    quarter  = row.get("quarter", "")
    insight  = row.get("insight", "")
    cmp      = row.get("cmp")
    pdf_url  = row.get("pdf_url", "")
    metrics  = row.get("metrics") or {}
    note     = row.get("rating_note", "")

    def _fmt(val, suffix="Cr"):
        if val is None or val == 0:
            return "—"
        if val >= 1_00_000:
            return f"₹{val/1_00_000:.1f}L {suffix}"
        if val >= 1_000:
            return f"₹{val/1_000:.1f}k {suffix}"
        return f"₹{val:.0f} {suffix}"

    def _pct(val):
        if val is None:
            return "—"
        sign = "+" if val > 0 else ""
        return f"{sign}{val:.1f}%"

    pat_row   = metrics.get("pat", {})
    rev_row   = metrics.get("sales", {})
    eps_row   = metrics.get("eps", {})
    rev_val   = rev_row.get("q3") or rev_row.get("q1") or 0
    pat_val   = pat_row.get("q3") or pat_row.get("q1") or 0
    eps_val   = eps_row.get("q3") or eps_row.get("q1") or 0

    lines = [
        f"{emoji} *{company}* ({symbol}) — {quarter}",
        f"Rating: *{rating}*  _{note}_",
        "",
        f"Revenue : {_fmt(rev_val)}  YoY {_pct(rev_row.get('yoy'))}  QoQ {_pct(rev_row.get('qoq'))}",
        f"PAT     : {_fmt(pat_val)}  YoY {_pct(pat_row.get('yoy'))}  QoQ {_pct(pat_row.get('qoq'))}",
        f"EPS     : ₹{eps_val:.1f}  YoY {_pct(eps_row.get('yoy'))}",
    ]
    if cmp:
        lines.append(f"CMP     : ₹{cmp:,.0f}")
    lines += ["", f"💡 {insight}"]
    if pdf_url:
        lines.append(f"\n📄 [BSE Filing]({pdf_url})")
    lines.append(f"🔗 [Dashboard]({DASHBOARD_URL}/results)")
    lines.append("\n_Source: BSE India · Parsed by DeepSeek AI_")

    text = "\n".join(lines)
    payload = json.dumps({
        "chat_id":    TG_CHAT_ID,
        "text":       text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        print(f"  [TG] sent: {company} {quarter}")
    except Exception as exc:
        print(f"  [TG] send failed: {exc}")


# ── Symbol Mapping ────────────────────────────────────────────────────────────

def _scrip_to_symbol(scrip_code: str, company: str) -> str:
    """Best-effort NSE symbol from BSE scrip code or company name."""
    # Common mappings (BSE scrip → NSE symbol)
    _MAP = {
        "500325": "RELIANCE", "532540": "TCS",        "500209": "INFY",
        "500180": "HDFCBANK", "532174": "ICICIBANK",  "532215": "AXISBANK",
        "500112": "SBIN",     "500696": "HINDUNILVR", "500010": "HDFC",
        "500034": "BAJFINANCE","500570": "TITAN",     "500790": "NESTLEIND",
        "523642": "BAJAJFINSV","500875": "ITC",       "532281": "HCLTECH",
        "532454": "BHARTIARTL","500312": "ONGC",      "500470": "TATASTEEL",
        "500400": "TATAPOWER","532755": "TECHM",      "507685": "WIPRO",
        "524715": "SUNPHARMA","532921": "ADANIPORTS", "543320": "ZOMATO",
        "543396": "DELHIVERY","543115": "IRFC",       "500440": "HINDALCO",
        "500295": "LTIM",     "532538": "ULTRACEMCO", "532488": "DRREDDY",
        "500825": "ASIANPAINT","500103": "BPCL",      "502103": "GRASIM",
        "500010": "HDFCBANK", "532500": "MARUTI",     "500696": "HINDUNILVR",
    }
    sym = _MAP.get(str(scrip_code))
    if sym:
        return sym
    # fallback: clean company name
    name = re.sub(r"\b(limited|ltd|pvt|private|india|industries|corp)\b", "", company, flags=re.I)
    return re.sub(r"[^A-Z]", "", name.upper())[:12]


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print(f"Results Pipeline  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. Fetch BSE filings
    print("\n[1] Fetching BSE filings...")
    raw_items = _fetch_bse_filings(pages=2)
    print(f"    Got {len(raw_items)} announcements")

    # 2. Filter to results filings
    results_items = [it for it in raw_items if _is_results_filing(it)]
    print(f"    {len(results_items)} match results categories")

    if not results_items:
        print("    Nothing to process.")
        return

    # 3. Load already-processed filing IDs
    print("\n[2] Loading processed filing IDs from Supabase...")
    processed = _get_processed_filing_ids()
    print(f"    {len(processed)} already processed")

    # 4. Filter to new ones
    new_items = []
    for it in results_items:
        attachment = it.get("ATTACHMENTNAME", "").strip()
        filing_id  = attachment or f"{it.get('SCRIP_CD','')}_{it.get('DT_TM','')}"
        if filing_id and filing_id not in processed:
            new_items.append((it, filing_id))

    print(f"    {len(new_items)} new filings to process")
    if not new_items:
        print("    All up-to-date.")
        return

    # 5. Process each new filing
    processed_count = 0
    for it, filing_id in new_items[:8]:  # max 8 per run to stay within Actions time
        company    = it.get("SHORT_NAME", "Unknown").title()
        scrip_code = str(it.get("SCRIP_CD", ""))
        headline   = it.get("NEWSSUB", "")
        category   = it.get("CATEGORYNAME", "Financial Results")
        dt         = it.get("DT_TM", "")
        attachment = it.get("ATTACHMENTNAME", "")
        pdf_url    = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}" if attachment else ""

        symbol = _scrip_to_symbol(scrip_code, company)
        print(f"\n  → {company} ({symbol}) | {category} | {dt[:16]}")
        print(f"    Headline: {headline[:80]}")

        # 5a. Extract PDF text
        pdf_text = ""
        if pdf_url:
            print("    Extracting PDF text...")
            pdf_text = _extract_pdf_text(pdf_url)
            print(f"    Got {len(pdf_text)} chars from PDF")

        # 5b. Call DeepSeek R1 (NIM → OpenRouter fallback)
        print("    Calling DeepSeek R1 for structured extraction...")
        ai = _call_nim_deepseek(company, scrip_code, dt, category, headline, pdf_text)
        if not ai:
            print("    AI extraction failed — skipping")
            continue

        # 5c. Deterministic rating (overrides AI opinion)
        rating, rating_note = _compute_rating(ai)
        ai["rating"]      = rating
        ai["rating_note"] = rating_note

        quarter = ai.get("quarter", "")
        print(f"    Extracted: {quarter} | rating={rating} | PAT YoY={ai.get('pat_yoy')} | PAT={ai.get('pat_cr')}")

        # 5c. Fetch live price
        print("    Fetching live price...")
        price_data = _fetch_price(symbol)
        print(f"    CMP: {price_data.get('cmp')} | ticker: {price_data.get('ticker')}")

        # 5d. Build row
        report_date = dt[:10] if dt else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        metrics     = _build_metrics(ai)

        # Trend arrays from prev quarters (q1=prev-prev, q2=prev, q3=current)
        rev = metrics["sales"]
        pat = metrics["pat"]
        eps = metrics["eps"]

        row_id = f"{scrip_code}_{filing_id[:40].replace('/', '_')}"

        row = {
            "id":             row_id,
            "symbol":         symbol,
            "ticker":         price_data.get("ticker") or f"{symbol}.NS",
            "company":        company,
            "exchange":       "BSE",
            "sector":         ai.get("sector", ""),
            "industry":       ai.get("industry", ""),
            "quarter":        quarter,
            "report_date":    report_date,
            "report_time":    ai.get("report_time", "After Market Hours"),
            "rating":         rating,
            "rating_note":    rating_note,
            "insight":        ai.get("insight", ""),
            "metrics":        metrics,
            "revenue_trend":  [rev["q1"], rev["q2"], rev["q3"]],
            "pat_trend":      [pat["q1"], pat["q2"], pat["q3"]],
            "eps_trend":      [eps["q1"], eps["q2"], eps["q3"]],
            "quarter_labels": ["Q-2", "Q-1", quarter],
            "cmp":            price_data.get("cmp"),
            "market_cap":     price_data.get("market_cap") or 0,
            "pe":             price_data.get("pe"),
            "currency_unit":  ai.get("currency_unit", "Cr"),
            "pdf_url":        pdf_url,
            "filing_id":      filing_id,
        }

        # 5e. Upsert to Supabase
        if _upsert_result(row):
            print("    ✓ Saved to Supabase")
            processed_count += 1
        else:
            print("    ✗ Supabase upsert failed")
            continue

        # 5f. Telegram notification
        _send_telegram(row)

        time.sleep(1)  # be polite to APIs

    print(f"\n{'='*60}")
    print(f"Done — processed {processed_count} new results")


if __name__ == "__main__":
    main()
    sys.exit(0)
