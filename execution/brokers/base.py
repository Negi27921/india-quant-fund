"""Abstract broker interface — all brokers implement this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SLM"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ProductType(str, Enum):
    CNC = "CNC"          # Cash and carry (delivery)
    INTRADAY = "MIS"     # Not used — cash only


@dataclass
class BrokerOrder:
    ticker: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float
    trigger_price: float = 0.0
    product: ProductType = ProductType.CNC
    tag: str = ""


@dataclass
class BrokerOrderResult:
    success: bool
    broker_order_id: str = ""
    status: OrderStatus = OrderStatus.FAILED
    error: str = ""
    raw_response: dict | None = None


@dataclass
class BrokerPosition:
    ticker: str
    quantity: int
    avg_price: float
    current_price: float
    unrealized_pnl: float
    product: str = "CNC"


@dataclass
class BrokerOrderStatus:
    broker_order_id: str
    status: OrderStatus
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    error: str = ""


class BrokerInterface(ABC):
    name: str = "base"

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> BrokerOrderResult: ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool: ...

    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus: ...

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    def get_portfolio_value(self) -> float: ...

    @abstractmethod
    def is_healthy(self) -> bool: ...

    def get_name(self) -> str:
        return self.name
