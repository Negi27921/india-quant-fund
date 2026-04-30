"""Trade reconciliation — broker positions vs internal state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from data.storage import db
from execution.router import SmartOrderRouter


@dataclass
class ReconciliationResult:
    date: str
    matched: list[str]
    broker_only: list[str]    # In broker but not internal
    internal_only: list[str]  # In internal but not broker
    quantity_mismatches: list[dict]
    mismatch_pct: float
    passed: bool


class Reconciliation:
    """
    Compares broker positions (live) with internal position table (DuckDB).
    Raises alert if mismatch > 5%.
    """

    def __init__(self, router: SmartOrderRouter, mismatch_threshold_pct: float = 5.0):
        self.router = router
        self.threshold = mismatch_threshold_pct

    def run(self) -> ReconciliationResult:
        broker_positions = {
            p.ticker: p
            for p in self.router.get_all_positions()
            if p.quantity > 0
        }

        internal = db.query_df("SELECT ticker, quantity, avg_buy_price FROM positions")
        internal_positions = {
            row["ticker"]: row
            for _, row in internal.iterrows()
        }

        matched = []
        broker_only = []
        internal_only = []
        qty_mismatches = []

        for ticker, bp in broker_positions.items():
            if ticker not in internal_positions:
                broker_only.append(ticker)
                logger.warning(f"Reconciliation: {ticker} in broker but not internal")
            else:
                ip = internal_positions[ticker]
                if abs(bp.quantity - ip["quantity"]) > 1:
                    qty_mismatches.append({
                        "ticker": ticker,
                        "broker_qty": bp.quantity,
                        "internal_qty": int(ip["quantity"]),
                        "diff": bp.quantity - int(ip["quantity"]),
                    })
                    logger.warning(
                        f"Reconciliation qty mismatch {ticker}: "
                        f"broker={bp.quantity}, internal={ip['quantity']}"
                    )
                else:
                    matched.append(ticker)

        for ticker in internal_positions:
            if ticker not in broker_positions:
                internal_only.append(ticker)
                logger.warning(f"Reconciliation: {ticker} in internal but not broker")

        total = len(broker_positions) + len(internal_positions)
        issues = len(broker_only) + len(internal_only) + len(qty_mismatches)
        mismatch_pct = (issues / max(total, 1)) * 100

        result = ReconciliationResult(
            date=datetime.now().isoformat(),
            matched=matched,
            broker_only=broker_only,
            internal_only=internal_only,
            quantity_mismatches=qty_mismatches,
            mismatch_pct=round(mismatch_pct, 2),
            passed=mismatch_pct <= self.threshold,
        )

        if result.passed:
            logger.info(f"Reconciliation passed: {len(matched)} positions matched")
        else:
            logger.error(
                f"Reconciliation FAILED: {mismatch_pct:.1f}% mismatch "
                f"({issues} issues in {total} positions)"
            )

        return result

    def sync_from_broker(self) -> None:
        """Overwrite internal positions with broker reality after mismatch."""
        positions = self.router.get_all_positions()
        for p in positions:
            if p.quantity > 0:
                db.execute("""
                    INSERT INTO positions (ticker, quantity, avg_buy_price, current_price, buy_date)
                    VALUES (?, ?, ?, ?, CURRENT_DATE)
                    ON CONFLICT (ticker) DO UPDATE SET
                        quantity = excluded.quantity,
                        avg_buy_price = excluded.avg_buy_price,
                        current_price = excluded.current_price,
                        last_updated = CURRENT_TIMESTAMP
                """, [p.ticker, p.quantity, p.avg_price, p.current_price])

        # Remove positions that broker doesn't have
        broker_tickers = {p.ticker for p in positions if p.quantity > 0}
        all_internal = db.query_df("SELECT ticker FROM positions")
        for ticker in all_internal["ticker"].tolist():
            if ticker not in broker_tickers:
                db.execute("DELETE FROM positions WHERE ticker = ?", [ticker])
        logger.info("Internal positions synced from broker")
