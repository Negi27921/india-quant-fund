"""Pydantic v2 models bound to the StockInsights.ai OpenAPI spec (India).

Source: https://stockinsights-ai-main-95a26a0.zuplo.app  /api/in/v0
Spec:   https://docs.stockinsights.ai/api-reference/openapi-india.json
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class SIMeta(BaseModel):
    total_count: int
    page: int
    limit: int


class SIResponse(BaseModel):
    status: str
    meta: Optional[SIMeta] = None
    data: Any = None


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class MarketCap(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = None


class Prices(BaseModel):
    currency: Optional[str] = None
    current: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None


class MarketSnapshot(BaseModel):
    market_cap: Optional[MarketCap] = None
    prices: Optional[Prices] = None
    as_of: Optional[datetime] = None


class ExchangeInfo(BaseModel):
    exchange: str
    scrip_code: Optional[str] = None
    symbol: Optional[str] = None
    url: Optional[str] = None


class IndustryInfo(BaseModel):
    macro: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    basic_industry: Optional[str] = None


class SICompany(BaseModel):
    id: str
    isin: Optional[str] = None
    company_name: str
    company_website: Optional[str] = None
    ticker: str
    marketcap_category: Optional[str] = None
    market_snapshot: Optional[MarketSnapshot] = None
    exchange_info: Optional[list[ExchangeInfo]] = None
    industry_info: Optional[IndustryInfo] = None

    def bse_code(self) -> Optional[str]:
        for e in (self.exchange_info or []):
            if e.exchange == "BSE":
                return e.scrip_code
        return None

    def nse_symbol(self) -> Optional[str]:
        for e in (self.exchange_info or []):
            if e.exchange == "NSE":
                return e.symbol
        return None


# ---------------------------------------------------------------------------
# Financial Statements
# ---------------------------------------------------------------------------

class XbrlStatementData(BaseModel):
    company_id: Optional[str] = None
    profile: Optional[str] = None          # bank | non-bank
    statement_type: Optional[str] = None
    statement_scope: Optional[str] = None  # standalone | consolidated
    reporting_type: Optional[str] = None   # quarterly | annual
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    period_end_date: Optional[date] = None
    audit_status: Optional[str] = None
    currency: Optional[str] = None
    scale: Optional[str] = None
    financials: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Results Calendar
# ---------------------------------------------------------------------------

class SICalendarResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    company_id: Optional[str] = None
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    result_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    result_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Filings (Documents)
# ---------------------------------------------------------------------------

class SIDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: Optional[str] = None
    pdf_link: Optional[str] = None
    html_link: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    exchange_tickers: Optional[list[Any]] = None
    year: Optional[int] = None
    month: Optional[int] = None
    quarter: Optional[int] = None
    published_date: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Announcements Tagged Feed
# ---------------------------------------------------------------------------

class AIInsights(BaseModel):
    model_config = ConfigDict(extra="allow")

    announcement_type_id: Optional[str] = None
    announcement_type: Optional[str] = None
    summary_header: Optional[str] = None
    summary_text: Optional[str] = None
    sentiment: Optional[str] = None
    significance: Optional[bool] = None
    title: Optional[str] = None
    description: Optional[str] = None


class ExchangeTicker(BaseModel):
    model_config = ConfigDict(extra="allow")

    exchange: Optional[str] = None
    ticker: Optional[str] = None
    id: Optional[str] = None
    url: Optional[str] = None


class SIAnnouncement(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: Optional[str] = None
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    company_id: Optional[str] = None
    exchange_tickers: Optional[list[ExchangeTicker]] = None
    source_link: Optional[str] = None
    company_page_url: Optional[str] = None
    ai_insights: Optional[AIInsights] = None
    published_date: Optional[datetime] = None
    year: Optional[str] = None


# ---------------------------------------------------------------------------
# Embeddings / Keyword Search
# ---------------------------------------------------------------------------

class DocumentChunkWithScore(BaseModel):
    model_config = ConfigDict(extra="allow")

    score: Optional[float] = None
    document_id: Optional[str] = None
    chunk_index: Optional[int] = None
    text: Optional[str] = None
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    document_type: Optional[str] = None
    year: Optional[int] = None
    quarter: Optional[int] = None
    published_date: Optional[datetime] = None
