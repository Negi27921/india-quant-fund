"""Base data loader protocol — all loaders implement this interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import pandas as pd


class DataLoaderProtocol(Protocol):
    name: str
    markets: set[str]
    requires_auth: bool

    def is_available(self) -> bool: ...

    def fetch_ohlcv(
        self,
        tickers: list[str],
        start: date,
        end: date,
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]: ...


@dataclass
class LoaderResult:
    success: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    data: dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        total = len(self.success) + len(self.failed)
        return len(self.success) / total if total else 0.0


class BaseLoader(ABC):
    name: str = "base"
    markets: set[str] = set()
    requires_auth: bool = False

    REQUIRED_COLS = {"open", "high", "low", "close", "volume"}

    def is_available(self) -> bool:
        return True

    @abstractmethod
    def fetch_ohlcv(
        self,
        tickers: list[str],
        start: date,
        end: date,
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        ...

    def _validate(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """Enforce standard column names and dtypes."""
        df.columns = [c.lower() for c in df.columns]
        missing = self.REQUIRED_COLS - set(df.columns)
        if missing:
            raise ValueError(f"{ticker}: missing columns {missing}")
        df = df[list(self.REQUIRED_COLS)].copy()
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
        df = df.dropna(subset=["close"])
        df = df[df["close"] > 0]
        return df.sort_index()
