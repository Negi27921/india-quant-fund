"""Risk limits — loaded from risk_limits.yaml, single source of truth."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PositionLimits:
    max_single_stock_pct: float = 5.0
    max_stocks_in_portfolio: int = 40
    min_stock_market_cap_cr: float = 500.0
    min_stock_price: float = 50.0
    max_stocks_per_strategy: int = 20


@dataclass
class SectorLimits:
    max_sector_exposure_pct: float = 20.0
    max_top3_sectors_pct: float = 50.0


@dataclass
class LiquidityLimits:
    max_order_as_pct_of_10d_adv: float = 5.0
    min_adv_cr: float = 5.0


@dataclass
class PortfolioLimits:
    max_portfolio_beta: float = 1.2
    min_portfolio_beta: float = 0.0
    vol_target_annual_pct: float = 10.0
    max_gross_exposure_pct: float = 100.0


@dataclass
class DrawdownLimits:
    daily_loss_limit_pct: float = 2.0
    weekly_loss_limit_pct: float = 4.0
    drawdown_alert_pct: float = 8.0
    drawdown_reduce_pct: float = 10.0
    drawdown_kill_switch_pct: float = 12.0
    max_consecutive_loss_days: int = 5


@dataclass
class CircuitBreakerLimits:
    nse_upper_circuit_buffer_pct: float = 1.0
    nse_lower_circuit_buffer_pct: float = 1.0
    vix_india_reduce_threshold: float = 25.0
    vix_india_halt_threshold: float = 35.0


@dataclass
class KillSwitchConfig:
    drawdown_pct: float = 12.0
    daily_loss_pct: float = 3.0
    broker_down_minutes: float = 15.0
    reconciliation_mismatch_pct: float = 5.0
    consecutive_failed_orders: int = 5


@dataclass
class OrderLimits:
    min_order_value: float = 5000.0
    max_order_value_pct: float = 5.0
    max_orders_per_day: int = 50
    order_timeout_minutes: int = 30


@dataclass
class RiskLimits:
    position: PositionLimits = field(default_factory=PositionLimits)
    sector: SectorLimits = field(default_factory=SectorLimits)
    liquidity: LiquidityLimits = field(default_factory=LiquidityLimits)
    portfolio: PortfolioLimits = field(default_factory=PortfolioLimits)
    drawdown: DrawdownLimits = field(default_factory=DrawdownLimits)
    circuit: CircuitBreakerLimits = field(default_factory=CircuitBreakerLimits)
    kill_switch: KillSwitchConfig = field(default_factory=KillSwitchConfig)
    order: OrderLimits = field(default_factory=OrderLimits)

    @classmethod
    def from_yaml(cls, path: str | Path = "config/risk_limits.yaml") -> "RiskLimits":
        with open(path) as f:
            cfg = yaml.safe_load(f)

        return cls(
            position=PositionLimits(**cfg.get("position_limits", {})),
            sector=SectorLimits(**cfg.get("sector_limits", {})),
            liquidity=LiquidityLimits(**cfg.get("liquidity_limits", {})),
            portfolio=PortfolioLimits(**cfg.get("portfolio_limits", {})),
            drawdown=DrawdownLimits(**cfg.get("drawdown_limits", {})),
            circuit=CircuitBreakerLimits(**cfg.get("circuit_breakers", {})),
            kill_switch=KillSwitchConfig(**cfg.get("kill_switch", {}).get("triggers", {})),
            order=OrderLimits(**cfg.get("order_limits", {})),
        )


_limits: RiskLimits | None = None


def get_limits() -> RiskLimits:
    global _limits
    if _limits is None:
        try:
            _limits = RiskLimits.from_yaml()
        except Exception:
            _limits = RiskLimits()  # safe defaults
    return _limits
