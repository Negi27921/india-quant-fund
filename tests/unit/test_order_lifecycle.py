"""Unit tests for OMS order lifecycle and idempotency."""
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import date
import pandas as pd

from execution.oms import OMS
from execution.brokers.base import OrderSide, OrderType, ProductType, OrderStatus


@pytest.fixture
def mock_router():
    router = MagicMock()
    router.place_order.return_value = MagicMock(
        success=True,
        broker_order_id="DHAN-12345",
        status=OrderStatus.PENDING,
        message="Order placed",
    )
    return router


@pytest.fixture
def oms(mock_router, mock_risk_limits):
    with patch("execution.oms.db") as mock_db:
        mock_db.query_df.return_value = pd.DataFrame()
        oms = OMS(router=mock_router, limits=mock_risk_limits)
        yield oms


class TestIdempotency:
    def test_duplicate_order_is_blocked(self, oms):
        """Same strategy:date:ticker:side combination must not be submitted twice."""
        order = {
            "ticker": "RELIANCE.NS",
            "side": OrderSide.BUY,
            "quantity": 10,
            "price": 2500.0,
            "strategy": "momentum_st",
            "order_type": OrderType.LIMIT,
        }

        with patch("execution.oms.db") as mock_db:
            # Simulate existing order with same idempotency key
            existing = pd.DataFrame([{
                "idempotency_key": f"momentum_st:{date.today()}:RELIANCE.NS:BUY",
                "status": "PENDING",
            }])
            mock_db.query_df.return_value = existing
            result = oms.submit(order)

        assert result is None or (hasattr(result, "success") and not result.success)

    def test_unique_order_is_submitted(self, oms, mock_router):
        """Different ticker should result in new submission."""
        order = {
            "ticker": "INFY.NS",
            "side": OrderSide.BUY,
            "quantity": 5,
            "price": 1800.0,
            "strategy": "momentum_st",
            "order_type": OrderType.LIMIT,
        }

        with patch("execution.oms.db") as mock_db:
            mock_db.query_df.return_value = pd.DataFrame()  # no existing orders
            oms.submit(order)

        # Router should have been called
        mock_router.place_order.assert_called_once()


class TestOrderPersistence:
    def test_submitted_order_is_stored(self, oms, mock_router):
        """OMS must persist order to DB on submission."""
        order = {
            "ticker": "TCS.NS",
            "side": OrderSide.SELL,
            "quantity": 8,
            "price": 3800.0,
            "strategy": "factor",
            "order_type": OrderType.LIMIT,
        }

        with patch("execution.oms.db") as mock_db:
            mock_db.query_df.return_value = pd.DataFrame()
            oms.submit(order)
            # DB insert should be called
            assert mock_db.insert_df.called or mock_db.upsert_df.called


class TestSellsBeforeBuys:
    def test_execution_order_sells_first(self):
        """Execution flow must process SELL orders before BUY orders."""
        from orchestration.flows.execution_flow import _order_priority
        buy_order = {"side": "BUY", "ticker": "X"}
        sell_order = {"side": "SELL", "ticker": "Y"}
        orders = [buy_order, sell_order]
        sorted_orders = sorted(orders, key=_order_priority)
        assert sorted_orders[0]["side"] == "SELL"


class TestT1Settlement:
    def test_same_day_sell_blocked_for_t1_buy(self):
        """T+1: cannot sell a stock bought today (intraday prohibited for CNC)."""
        from execution.oms import is_t1_eligible
        today = date.today()
        assert not is_t1_eligible(today, today), "Same-day sell of CNC buy must be blocked"
        from datetime import timedelta
        yesterday = today - timedelta(days=1)
        assert is_t1_eligible(yesterday, today), "Next-day sell of CNC buy must be allowed"
