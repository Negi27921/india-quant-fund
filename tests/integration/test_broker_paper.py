"""
Integration tests for paper trading broker.
These run against the actual broker adapters in paper mode.
Requires PAPER_TRADING=true and valid credentials in .env.
"""
import os
import pytest
from datetime import date

pytestmark = pytest.mark.integration  # run with: pytest -m integration


@pytest.fixture(autouse=True)
def require_paper_mode():
    """Guard: integration tests only run in paper trading mode."""
    if os.getenv("PAPER_TRADING", "true").lower() != "true":
        pytest.skip("Integration tests require PAPER_TRADING=true")


class TestDhanPaperBroker:
    @pytest.mark.skipif(
        not os.getenv("DHAN_CLIENT_ID"),
        reason="DHAN_CLIENT_ID not configured"
    )
    def test_paper_order_returns_fake_id(self):
        from execution.brokers.dhan import DhanBroker
        from execution.brokers.base import OrderSide, OrderType, ProductType

        broker = DhanBroker()
        result = broker.place_order(
            ticker="RELIANCE.NS",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=2500.0,
            product_type=ProductType.CNC,
        )
        assert result.success, f"Paper order failed: {result.message}"
        assert result.broker_order_id is not None
        assert result.broker_order_id.startswith("PAPER-")

    @pytest.mark.skipif(
        not os.getenv("DHAN_CLIENT_ID"),
        reason="DHAN_CLIENT_ID not configured"
    )
    def test_paper_positions_returns_list(self):
        from execution.brokers.dhan import DhanBroker
        broker = DhanBroker()
        positions = broker.get_positions()
        assert isinstance(positions, list)


class TestSmartRouter:
    def test_router_uses_primary_broker(self):
        from execution.router import SmartOrderRouter
        from execution.brokers.dhan import DhanBroker
        from execution.brokers.shoonya import ShoonyaBroker
        from unittest.mock import MagicMock

        primary = MagicMock(spec=DhanBroker)
        primary.place_order.return_value = MagicMock(
            success=True, broker_order_id="PAPER-001", message=""
        )
        fallback = MagicMock(spec=ShoonyaBroker)

        router = SmartOrderRouter(primary=primary, fallback=fallback)
        from execution.brokers.base import OrderSide, OrderType, ProductType

        router.place_order(
            ticker="INFY.NS",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=1800.0,
            product_type=ProductType.CNC,
        )
        primary.place_order.assert_called_once()
        fallback.place_order.assert_not_called()

    def test_router_switches_to_fallback_on_failure(self):
        from execution.router import SmartOrderRouter
        from execution.brokers.dhan import DhanBroker
        from execution.brokers.shoonya import ShoonyaBroker
        from execution.brokers.base import OrderSide, OrderType, ProductType
        from unittest.mock import MagicMock

        primary = MagicMock(spec=DhanBroker)
        primary.place_order.return_value = MagicMock(
            success=False, broker_order_id=None, message="Connection error"
        )
        fallback = MagicMock(spec=ShoonyaBroker)
        fallback.place_order.return_value = MagicMock(
            success=True, broker_order_id="SHOONYA-001", message=""
        )

        router = SmartOrderRouter(primary=primary, fallback=fallback)
        result = router.place_order(
            ticker="INFY.NS",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=1800.0,
            product_type=ProductType.CNC,
        )
        # Fallback should have been tried
        assert result.broker_order_id == "SHOONYA-001"
