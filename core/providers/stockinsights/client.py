"""StockInsights.ai async client.

All SI.ai calls are mediated here:
  - Token bucket: 10 req/s sustained, burst 20
  - Retry: tenacity, 3 attempts, exp backoff 1→8s with jitter
  - Dead-letter: persistent failures written to si_dlq via Supabase
  - Observability: counters per endpoint (in-process, no external metrics server)
  - Source primacy: enforced by DATA_PRIMARY_SOURCE config; callers should not
    care — they call this client. The day-8 flip happens in config only.
"""
from __future__ import annotations

import asyncio
import logging
import time
from functools import lru_cache
from typing import Any, Optional

import httpx
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.config import settings
from .models import (
    SICompany,
    SIDocument,
    SIAnnouncement,
    SICalendarResult,
    XbrlStatementData,
    DocumentChunkWithScore,
    SIResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process counters (no Prometheus required on Vercel)
# ---------------------------------------------------------------------------
_counters: dict[str, int] = {}

def _inc(key: str) -> None:
    _counters[key] = _counters.get(key, 0) + 1

def get_counters() -> dict[str, int]:
    return dict(_counters)


# ---------------------------------------------------------------------------
# Token bucket (10 req/s sustained, burst 20)
# ---------------------------------------------------------------------------

class _TokenBucket:
    def __init__(self, rate: float = 10.0, capacity: float = 20.0) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now
            if self._tokens < 1:
                wait = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1


_bucket = _TokenBucket()


# ---------------------------------------------------------------------------
# Retryable exception wrapper
# ---------------------------------------------------------------------------

class SIRetryableError(Exception):
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        super().__init__(f"SI HTTP {status}: {body[:200]}")


class SIFatalError(Exception):
    pass


# ---------------------------------------------------------------------------
# Dead-letter writer (best-effort, non-blocking)
# ---------------------------------------------------------------------------

async def _write_dlq(endpoint: str, params: dict, error_code: int, error_msg: str) -> None:
    try:
        from supabase import create_client
        key = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY
        sb = create_client(settings.SUPABASE_URL, key)
        sb.table("si_dlq").insert({
            "endpoint": endpoint,
            "params": params,
            "error_code": error_code,
            "error_msg": error_msg[:500],
        }).execute()
    except Exception as e:
        logger.warning("DLQ write failed: %s", e)


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class SIClient:
    """Singleton async client for StockInsights.ai India endpoints."""

    def __init__(self) -> None:
        self._base = settings.si_base_url
        self._headers = {
            "Authorization": f"Bearer {settings.SI_API_KEY}",
            "Accept": "application/json",
        }
        self._http: Optional[httpx.AsyncClient] = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                headers=self._headers,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Raw request with token-bucket gating and retry."""
        await _bucket.acquire()
        url = self._base + path
        parts = path.strip("/").split("/")
        _inc(f"si.{parts[-1] if parts else path}.attempts")

        @retry(
            retry=retry_if_exception_type(SIRetryableError),
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=8),
            reraise=True,
        )
        async def _do() -> Any:
            http = await self._get_http()
            r = await http.request(method, url, **kwargs)
            if r.status_code in (429, 503, 502):
                _inc("si.retryable_errors")
                raise SIRetryableError(r.status_code, r.text)
            if r.status_code >= 400:
                _inc("si.fatal_errors")
                raise SIFatalError(f"SI HTTP {r.status_code}: {r.text[:300]}")
            _inc("si.success")
            return r.json()

        try:
            return await _do()
        except (SIRetryableError, SIFatalError) as exc:
            status = getattr(exc, "status", 0)
            await _write_dlq(path, kwargs.get("params", {}), status, str(exc))
            raise

    # -----------------------------------------------------------------------
    # 1. Companies
    # -----------------------------------------------------------------------

    async def get_companies(
        self,
        ticker: Optional[str] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        marketcap_category: Optional[str] = None,
        page: int = 1,
        limit: int = 100,
    ) -> tuple[list[SICompany], int]:
        params = {"page": page, "limit": limit}
        if ticker:
            params["ticker"] = ticker
        if sector:
            params["sector"] = sector
        if industry:
            params["industry"] = industry
        if marketcap_category:
            params["marketcap_category"] = marketcap_category

        raw = await self._request("GET", "/companies", params=params)
        companies = [SICompany.model_validate(c) for c in raw.get("data", [])]
        total = raw.get("meta", {}).get("total_count", 0)
        return companies, total

    async def iter_all_companies(self, limit: int = 100) -> list[SICompany]:
        """Page through all companies exhaustively."""
        all_companies: list[SICompany] = []
        page = 1
        while True:
            batch, total = await self.get_companies(page=page, limit=limit)
            all_companies.extend(batch)
            logger.info("Companies: fetched %d/%d", len(all_companies), total)
            if len(all_companies) >= total or not batch:
                break
            page += 1
        return all_companies

    # -----------------------------------------------------------------------
    # 2. Income Statement
    # -----------------------------------------------------------------------

    async def get_income_statement(
        self,
        ticker: str,
        period_end_date: str,
        reporting_type: str,
        statement_scope: str,
    ) -> Optional[XbrlStatementData]:
        params = {
            "ticker": ticker,
            "period_end_date": period_end_date,
            "reporting_type": reporting_type,
            "statement_scope": statement_scope,
        }
        raw = await self._request("GET", "/financial-statements/income-statement", params=params)
        data = raw.get("data")
        if not data:
            return None
        try:
            return XbrlStatementData.model_validate(data[0] if isinstance(data, list) else data)
        except ValidationError as e:
            logger.warning("income-statement validation error %s: %s", ticker, e)
            return None

    # -----------------------------------------------------------------------
    # 3. Balance Sheet
    # -----------------------------------------------------------------------

    async def get_balance_sheet(
        self,
        ticker: str,
        period_end_date: str,
        statement_scope: str,
    ) -> Optional[XbrlStatementData]:
        params = {
            "ticker": ticker,
            "period_end_date": period_end_date,
            "statement_scope": statement_scope,
        }
        raw = await self._request("GET", "/financial-statements/balance-sheet", params=params)
        data = raw.get("data")
        if not data:
            return None
        try:
            return XbrlStatementData.model_validate(data[0] if isinstance(data, list) else data)
        except ValidationError as e:
            logger.warning("balance-sheet validation error %s: %s", ticker, e)
            return None

    # -----------------------------------------------------------------------
    # 4. Cash Flow
    # -----------------------------------------------------------------------

    async def get_cash_flow(
        self,
        ticker: str,
        period_end_date: str,
        reporting_type: str,
        statement_scope: str,
    ) -> Optional[XbrlStatementData]:
        params = {
            "ticker": ticker,
            "period_end_date": period_end_date,
            "reporting_type": reporting_type,
            "statement_scope": statement_scope,
        }
        raw = await self._request("GET", "/financial-statements/cash-flow", params=params)
        data = raw.get("data")
        if not data:
            return None
        try:
            return XbrlStatementData.model_validate(data[0] if isinstance(data, list) else data)
        except ValidationError as e:
            logger.warning("cash-flow validation error %s: %s", ticker, e)
            return None

    # -----------------------------------------------------------------------
    # 5. Results Calendar
    # -----------------------------------------------------------------------

    async def get_results_calendar(
        self,
        ticker: Optional[str] = None,
        page: int = 1,
        limit: int = 100,
    ) -> tuple[list[SICalendarResult], int]:
        params: dict = {"page": page, "limit": limit}
        if ticker:
            params["ticker"] = ticker
        raw = await self._request("GET", "/results-calendar", params=params)
        results = []
        for item in raw.get("data", []):
            try:
                results.append(SICalendarResult.model_validate(item))
            except ValidationError:
                results.append(SICalendarResult.model_construct(**item))
        total = raw.get("meta", {}).get("total_count", len(results))
        return results, total

    # -----------------------------------------------------------------------
    # 6. Filings Feed
    # -----------------------------------------------------------------------

    async def get_filings_feed(
        self,
        document_type: str,
        ticker: Optional[str] = None,
        sector: Optional[str] = None,
        quarter: Optional[int] = None,
        year: Optional[int] = None,
        page: int = 1,
        limit: int = 100,
    ) -> tuple[list[SIDocument], int]:
        params: dict = {"document_type": document_type, "page": page, "limit": limit}
        if ticker:
            params["ticker"] = ticker
        if sector:
            params["sector"] = sector
        if quarter:
            params["quarter"] = quarter
        if year:
            params["year"] = year
        raw = await self._request("GET", "/documents", params=params)
        docs = []
        for item in raw.get("data", []):
            try:
                docs.append(SIDocument.model_validate(item))
            except ValidationError:
                docs.append(SIDocument.model_construct(**item))
        total = raw.get("meta", {}).get("total_count", len(docs))
        return docs, total

    # -----------------------------------------------------------------------
    # 7. Announcements Tagged Feed
    # -----------------------------------------------------------------------

    async def get_announcements(
        self,
        ticker: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        sentiment: Optional[str] = None,
        announcement_type_id: Optional[str] = None,
        sector: Optional[str] = None,
        page: int = 1,
        limit: int = 100,
    ) -> tuple[list[SIAnnouncement], int]:
        params: dict = {"page": page, "limit": limit}
        if ticker:
            params["ticker"] = ticker
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        if sentiment:
            params["sentiment"] = sentiment
        if announcement_type_id:
            params["announcement_type_id"] = announcement_type_id
        if sector:
            params["sector"] = sector
        raw = await self._request("GET", "/documents/announcement", params=params)
        items = []
        for item in raw.get("data", []):
            try:
                items.append(SIAnnouncement.model_validate(item))
            except ValidationError:
                items.append(SIAnnouncement.model_construct(**item))
        total = raw.get("meta", {}).get("total_count", len(items))
        return items, total

    # -----------------------------------------------------------------------
    # 8. Keyword Search
    # -----------------------------------------------------------------------

    async def keyword_search(
        self,
        query: str,
        types: Optional[list[str]] = None,
        tickers: Optional[list[str]] = None,
    ) -> list[dict]:
        payload: dict = {
            "query": query,
            "filters": {"types": types or ["earnings-transcript", "annual-report"]},
        }
        if tickers:
            payload["filters"]["tickers"] = tickers
        raw = await self._request("POST", "/documents/full-text-search", json=payload)
        return raw.get("data", [])

    # -----------------------------------------------------------------------
    # 9. Embeddings Search (RAG)
    # -----------------------------------------------------------------------

    async def embeddings_search(
        self,
        query: str,
        types: Optional[list[str]] = None,
        tickers: Optional[list[str]] = None,
        top_k: int = 10,
    ) -> list[DocumentChunkWithScore]:
        payload: dict = {
            "query": query,
            "top_k": min(top_k, 100),
            "filters": {"types": types or ["earnings-transcript", "annual-report"]},
        }
        if tickers:
            payload["filters"]["tickers"] = tickers
        raw = await self._request("POST", "/documents/embeddings-search", json=payload)
        chunks = []
        for item in raw.get("data", []):
            try:
                chunks.append(DocumentChunkWithScore.model_validate(item))
            except ValidationError:
                chunks.append(DocumentChunkWithScore.model_construct(**item))
        return chunks


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_si_client() -> SIClient:
    return SIClient()
