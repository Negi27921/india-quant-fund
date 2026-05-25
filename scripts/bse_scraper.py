"""
bse_scraper.py
══════════════
BSE Corporate Announcements Scraper

Anti-ban strategy:
  • curl_cffi: impersonates Chrome TLS fingerprint — defeats Cloudflare bot detection
  • Playwright fallback: headless Chrome session for cookie refresh when curl_cffi expires
  • Rate limiter: 0.5–1.5s random jitter per request; exponential backoff on 429/503
  • Session reuse: one curl_cffi Session per scraper instance, refreshed every 25 min
  • Sequential-only: never parallel requests to BSE
  • Ban detection: checks for "Access Denied", "captcha", "cf-mitigated" in responses

Limitation:
  BSE's date-range API (strSearch=D) returns empty from non-browser sessions.
  This scraper uses strSearch=P (latest/pagination) which only returns TODAY's
  announcements. Run during/after market hours (15:30–18:00 IST) to capture
  all same-day result filings.

  For historical data: the NSE API (already in results_pipeline.py) covers all
  NSE-listed companies; BSE-only companies appear via this scraper.

Usage:
    from scripts.bse_scraper import BSEScraper
    scraper = BSEScraper()
    items = scraper.get_result_filings()   # returns today's financial results
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────
_BSE_HOME    = "https://www.bseindia.com/"
_BSE_ANN     = "https://www.bseindia.com/corporates/ann.html"
_BSE_API     = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
_BSE_PDF_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
_SESSION_TTL  = 25 * 60   # refresh session after 25 min

# Financial results keywords for client-side filtering
_RESULT_KEYWORDS = (
    "financial result", "quarterly result", "annual result",
    "standalone financial", "consolidated financial",
    "profit and loss", "q1 fy", "q2 fy", "q3 fy", "q4 fy",
    "half year", "nine months", "full year",
)

# User-agent pool — rotate to reduce fingerprinting
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _jitter(lo: float = 0.5, hi: float = 1.5) -> None:
    """Sleep a random amount between lo and hi seconds."""
    time.sleep(lo + random.random() * (hi - lo))


def _is_financial_result(item: dict) -> bool:
    """Return True if BSE item is a financial results announcement."""
    cat   = (item.get("CATEGORYNAME") or "").lower()
    sub   = (item.get("SUBCATNAME")   or "").lower()
    news  = (item.get("NEWSSUB")      or "").lower()
    combined = f"{cat} {sub} {news}"
    return any(kw in combined for kw in _RESULT_KEYWORDS)


def _build_pdf_url(attachment: str) -> str:
    if not attachment:
        return ""
    if attachment.startswith("http"):
        return attachment
    return f"{_BSE_PDF_BASE}{attachment}"


class BSEScraper:
    """
    Stateful BSE scraper. Create once and reuse across pipeline calls.
    The session is automatically refreshed after SESSION_TTL seconds.
    """

    def __init__(self) -> None:
        self._session    = None
        self._ua         = random.choice(_USER_AGENTS)
        self._sess_born  = 0.0      # timestamp when session was created
        self._headers    = {
            "Referer":         _BSE_ANN,
            "Origin":          "https://www.bseindia.com",
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua":       '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest":  "empty",
            "sec-fetch-mode":  "cors",
            "sec-fetch-site":  "same-site",
        }
        self._scrip_symbol_cache: dict[str, str] = {}

    # ── Session management ────────────────────────────────────────────────────

    def _get_session(self):
        """Return a live curl_cffi session; refresh if stale."""
        age = time.monotonic() - self._sess_born
        if self._session is None or age > _SESSION_TTL:
            self._refresh_session()
        return self._session

    def _refresh_session(self) -> None:
        """Create a new curl_cffi session and warm it with BSE homepage visits."""
        try:
            import curl_cffi.requests as _cf
        except ImportError:
            raise RuntimeError("curl_cffi not installed — run: pip install curl_cffi")

        self._ua = random.choice(_USER_AGENTS)
        sess = _cf.Session(impersonate="chrome124")
        sess.headers.update({"User-Agent": self._ua})

        # Warm-up: visit homepage → ann page (sets session cookies + CF clearance)
        try:
            r0 = sess.get(_BSE_HOME, timeout=15)
            print(f"  [BSE] session warm-up home: {r0.status_code}")
            if self._is_banned(r0):
                print("  [BSE] homepage blocked — trying Playwright session refresh")
                cookies = self._playwright_get_cookies()
                for c in cookies:
                    sess.cookies.set(c["name"], c["value"], domain=c.get("domain", ".bseindia.com"))
            _jitter(1.0, 2.0)
            r1 = sess.get(_BSE_ANN, timeout=10, headers={"Accept": "text/html"})
            print(f"  [BSE] ann page: {r1.status_code}")
            _jitter(0.8, 1.5)
        except Exception as exc:
            print(f"  [BSE] session warm-up failed: {exc}")

        self._session   = sess
        self._sess_born = time.monotonic()

    def _playwright_get_cookies(self) -> list[dict]:
        """Use Playwright stealth to visit BSE and return its cookies."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []
        cookies = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                )
                ctx = browser.new_context(
                    user_agent=self._ua,
                    viewport={"width": 1440, "height": 900},
                    extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
                )
                # Patch navigator.webdriver before any navigation
                ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                page = ctx.new_page()
                page.goto(_BSE_HOME, wait_until="domcontentloaded", timeout=20000)
                time.sleep(2)
                page.goto(_BSE_ANN,  wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
                cookies = ctx.cookies()
                browser.close()
            print(f"  [BSE] Playwright got {len(cookies)} cookies")
        except Exception as exc:
            print(f"  [BSE] Playwright cookie fetch failed: {exc}")
        return cookies

    # ── Ban detection ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_banned(response) -> bool:
        """Detect Cloudflare/WAF blocks: 403, or HTML body containing block markers."""
        if response.status_code == 403:
            return True
        if response.status_code == 429:
            return True
        text = (response.text or "")[:500].lower()
        return any(marker in text for marker in (
            "access denied", "cf-mitigated", "captcha", "blocked", "just a moment",
        ))

    # ── Core request ──────────────────────────────────────────────────────────

    def _get(self, url: str, max_retries: int = 3) -> Optional[dict]:
        """
        GET url with:
          - curl_cffi Chrome impersonation
          - Exponential backoff on 429/503
          - Session refresh on persistent 403
        Returns parsed JSON dict or None on failure.
        """
        delay = 2.0
        for attempt in range(max_retries):
            try:
                sess = self._get_session()
                r = sess.get(url, headers=self._headers, timeout=20)

                if r.status_code == 200:
                    # Check if we got HTML instead of JSON (silent block)
                    ct = r.headers.get("content-type", "")
                    if "json" in ct or r.text.strip().startswith("{"):
                        return r.json()
                    # HTML response = session expired or blocked
                    if "<html" in r.text[:50].lower():
                        print(f"  [BSE] HTML response on attempt {attempt+1} — refreshing session")
                        self._sess_born = 0  # force refresh
                        _jitter(delay, delay * 1.5)
                        delay *= 2
                        continue
                    return r.json()

                if r.status_code == 429:
                    wait = delay + random.uniform(0, 2)
                    print(f"  [BSE] Rate-limited — waiting {wait:.1f}s")
                    time.sleep(wait)
                    delay = min(delay * 2, 60)
                    continue

                if r.status_code in (403, 503):
                    if attempt < max_retries - 1:
                        print(f"  [BSE] {r.status_code} on attempt {attempt+1} — refreshing")
                        self._sess_born = 0
                        _jitter(delay, delay * 2)
                        delay *= 2
                    continue

                print(f"  [BSE] HTTP {r.status_code} on {url[-60:]}")
                return None

            except Exception as exc:
                print(f"  [BSE] request error (attempt {attempt+1}): {exc}")
                if attempt < max_retries - 1:
                    _jitter(delay, delay * 1.5)
                    delay = min(delay * 2, 30)

        return None

    # ── Announcement fetching ─────────────────────────────────────────────────

    def get_result_filings(
        self,
        from_date: Optional[str] = None,
        max_pages: int = 30,
    ) -> list[dict]:
        """
        Return today's BSE financial result filings.

        BSE's date-range API (strSearch=D) does not work from outside their
        network, so this uses strSearch=P (latest pagination) and filters
        client-side. TotalPageCnt tells us when to stop paginating.

        Args:
            from_date: ISO date string 'YYYY-MM-DD'; skip items older than this.
                       Defaults to today.
            max_pages: Hard safety cap on pages fetched (1 page ≈ 20 items).
        Returns:
            List of pipeline-compatible filing dicts (_source='bse', _symbol, etc.)
        """
        today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cutoff    = from_date or today

        results   : list[dict] = []
        seen      : set[str]   = set()
        stop      = False

        print(f"  [BSE] Fetching announcements (cutoff={cutoff})…")

        for page in range(1, max_pages + 1):
            url = (
                f"{_BSE_API}?pageno={page}&strCat=-1&strPrevDate="
                f"&strScrip=&strSearch=P&strToDate=&strType=C&subcategory=-1"
            )
            data = self._get(url)
            if data is None:
                break

            table = data.get("Table", [])
            if not table:
                print(f"  [BSE] p{page}: empty — done")
                break

            total_pages = int(table[0].get("TotalPageCnt") or 1)

            for item in table:
                dt = (item.get("DT_TM") or item.get("NEWS_DT") or "")[:10]
                if dt < cutoff:
                    stop = True  # we've scrolled past our date range
                    break

                attachment = (item.get("ATTACHMENTNAME") or "").strip()
                uid = attachment or f"{item.get('SCRIP_CD')}_{item.get('DT_TM','')}_{page}"
                if uid in seen:
                    continue
                seen.add(uid)

                if not _is_financial_result(item):
                    continue

                scrip_cd = str(item.get("SCRIP_CD") or "")
                company  = (item.get("SLONGNAME") or item.get("NEWSSUB") or scrip_cd).title()
                symbol   = self._scrip_to_symbol(scrip_cd, company)
                pdf_url  = _build_pdf_url(attachment)

                results.append({
                    "_source":      "bse",
                    "SCRIP_CD":     scrip_cd,
                    "SHORT_NAME":   company,
                    "NEWSSUB":      (item.get("NEWSSUB") or "")[:250],
                    "CATEGORYNAME": "Financial Results",
                    "DT_TM":        (item.get("DT_TM") or dt)[:19],
                    "ATTACHMENTNAME": attachment,
                    "_symbol":      symbol,
                    "_pdf_url":     pdf_url,
                    "_exchange":    "BSE",
                })

            count_new = len(results)
            print(f"  [BSE] p{page}/{total_pages}: {len(table)} items, "
                  f"{count_new} fin-results so far")

            if stop or page >= total_pages:
                break
            _jitter(0.5, 1.2)

        print(f"  [BSE] Done — {len(results)} financial result filings")
        return results

    # ── PDF download ──────────────────────────────────────────────────────────

    def download_pdf(self, url: str, max_bytes: int = 5 * 1024 * 1024) -> Optional[bytes]:
        """
        Download a BSE PDF using the established session.
        BSE PDFs at xml-data/corpfiling/AttachLive/ don't require special auth,
        but using the same session avoids triggering anomaly detection.
        Returns raw bytes or None on failure.
        """
        if not url:
            return None
        try:
            sess = self._get_session()
            headers = {
                "Accept":  "application/pdf,application/octet-stream,*/*",
                "Referer": _BSE_ANN,
            }
            r = sess.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                content = r.content
                if len(content) > max_bytes:
                    print(f"  [BSE-PDF] {url[-50:]}: {len(content)//1024}KB (truncating)")
                    return content[:max_bytes]
                return content
            print(f"  [BSE-PDF] HTTP {r.status_code}: {url[-60:]}")
        except Exception as exc:
            print(f"  [BSE-PDF] download failed {url[-50:]}: {exc}")
        return None

    # ── Scrip → Symbol lookup ─────────────────────────────────────────────────

    def _scrip_to_symbol(self, scrip_cd: str, company: str = "") -> str:
        """
        Convert BSE scrip code to NSE symbol (best-effort).
        Uses a lightweight BSE API call; caches results in memory.
        """
        if not scrip_cd:
            return ""
        if scrip_cd in self._scrip_symbol_cache:
            return self._scrip_symbol_cache[scrip_cd]

        symbol = ""
        try:
            sess = self._get_session()
            url = (f"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w"
                   f"?Debtflag=&scripcode={scrip_cd}&seriesid=")
            r = sess.get(url, headers={
                "Referer": _BSE_HOME,
                "Accept":  "application/json",
            }, timeout=8)
            if r.status_code == 200:
                data = r.json()
                # ISIN → NSE symbol lookup via header data
                isin   = (data.get("Isin") or "").strip()
                nsesym = (data.get("NSE_Symbol") or data.get("NSEScrip") or "").strip()
                bsesym = (data.get("BseSymbol") or data.get("BSEScrip") or "").strip()
                symbol = nsesym or bsesym or ""
        except Exception:
            pass

        if not symbol:
            # Fallback: slugify company name
            symbol = re.sub(r"[^A-Z0-9]", "", company.upper())[:10]

        self._scrip_symbol_cache[scrip_cd] = symbol
        return symbol


# ── Module-level singleton ────────────────────────────────────────────────────
_SCRAPER: Optional[BSEScraper] = None

def get_bse_scraper() -> BSEScraper:
    """Return (or create) the module-level BSE scraper singleton."""
    global _SCRAPER
    if _SCRAPER is None:
        _SCRAPER = BSEScraper()
    return _SCRAPER


def fetch_bse_results(from_date: str, to_date: str) -> list[dict]:
    """
    Pipeline-compatible wrapper.
    Returns today's BSE financial result filings where DT_TM >= from_date.
    Note: to_date is accepted for API compatibility but BSE only serves today's data.
    """
    scraper = get_bse_scraper()
    return scraper.get_result_filings(from_date=from_date)
