"""Immutable audit logger — append-only event log."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from data.storage import db


class AuditLogger:
    """
    Append-only audit trail for all system events.
    Records: agent decisions, orders, risk rejections, kill switch events.
    """

    _counter: int = 0

    @classmethod
    def log(
        cls,
        event_type: str,
        actor: str,
        action: str,
        entity_type: str = "",
        entity_id: str = "",
        payload: Any = None,
        result: str = "ok",
        error: str = "",
    ) -> None:
        cls._counter += 1
        try:
            db.execute("""
                INSERT INTO audit_log
                (id, timestamp, event_type, actor, entity_type, entity_id, action, payload, result, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                cls._counter,
                datetime.now(),
                event_type,
                actor,
                entity_type,
                entity_id,
                action,
                json.dumps(payload) if payload else None,
                result,
                error,
            ])
        except Exception as e:
            logger.error(f"Audit log write failed: {e}")

    @classmethod
    def order_submitted(cls, order_id: str, ticker: str, side: str, qty: int, price: float, strategy: str) -> None:
        cls.log(
            event_type="ORDER",
            actor="execution_agent",
            action="submit",
            entity_type="order",
            entity_id=order_id,
            payload={"ticker": ticker, "side": side, "qty": qty, "price": price, "strategy": strategy},
        )

    @classmethod
    def order_rejected(cls, order_id: str, ticker: str, reason: str) -> None:
        cls.log(
            event_type="ORDER",
            actor="risk_agent",
            action="reject",
            entity_type="order",
            entity_id=order_id,
            payload={"ticker": ticker, "reason": reason},
            result="rejected",
        )

    @classmethod
    def kill_switch_triggered(cls, reason: str) -> None:
        cls.log(
            event_type="KILL_SWITCH",
            actor="risk_manager",
            action="trigger",
            payload={"reason": reason},
            result="critical",
        )

    @classmethod
    def agent_decision(cls, agent: str, decision: dict) -> None:
        cls.log(
            event_type="AGENT_DECISION",
            actor=agent,
            action="decide",
            payload=decision,
        )
