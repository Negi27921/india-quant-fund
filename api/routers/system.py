"""System health and control API."""
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from data.storage import db
from monitoring.audit import AuditLogger
from api.middleware.security import require_internal_key, rate_limit

router = APIRouter()


@router.get("/health")
async def system_health():
    try:
        db.query_df("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "database": "ok" if db_ok else "down",
        "api": "ok",
        "timestamp": datetime.now().isoformat(),
        "paper_trading": True,
    }


@router.get("/audit-log", dependencies=[Depends(rate_limit)])
async def audit_log(limit: int = Query(default=50, ge=1, le=500)):
    try:
        safe_limit = int(limit)  # ge/le already validated, explicit cast for clarity
        df = db.query_df(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
            [safe_limit],
        )
        return df.to_dict("records") if not df.empty else []
    except Exception:
        return {"error": "audit log unavailable"}


@router.get("/kill-switch/status")
async def kill_switch_status():
    from risk.limits import get_limits
    from risk.kill_switch import KillSwitch
    ks = KillSwitch(get_limits())
    return ks.status()


@router.post("/kill-switch/reset", dependencies=[Depends(require_internal_key)])
async def reset_kill_switch(reason: str = Query(default="Manual reset via API", max_length=200)):
    from risk.limits import get_limits
    from risk.kill_switch import KillSwitch
    ks = KillSwitch(get_limits())
    ks.reset(reason)
    AuditLogger.log("KILL_SWITCH", "api", "reset", payload={"reason": reason})
    return {"status": "reset", "reason": reason}
