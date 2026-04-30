"""System health and control API."""
from datetime import datetime
from fastapi import APIRouter
from data.storage import db
from monitoring.audit import AuditLogger

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


@router.get("/audit-log")
async def audit_log(limit: int = 50):
    try:
        df = db.query_df(f"""
            SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT {limit}
        """)
        return df.to_dict("records") if not df.empty else []
    except Exception as e:
        return {"error": str(e)}


@router.get("/kill-switch/status")
async def kill_switch_status():
    from risk.limits import get_limits
    from risk.kill_switch import KillSwitch
    ks = KillSwitch(get_limits())
    return ks.status()


@router.post("/kill-switch/reset")
async def reset_kill_switch(reason: str = "Manual reset via API"):
    from risk.limits import get_limits
    from risk.kill_switch import KillSwitch
    ks = KillSwitch(get_limits())
    ks.reset(reason)
    AuditLogger.log("KILL_SWITCH", "api", "reset", payload={"reason": reason})
    return {"status": "reset", "reason": reason}
