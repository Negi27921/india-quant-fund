"""
Strategy Agent — One Piece Quant (Hermes-inspired)

Analyses paper trade performance across all screeners daily.
Uses Groq function-calling (Hermes-2 style) to identify patterns,
suggest parameter improvements, and write learnings to Supabase.

Architecture follows NousResearch/hermes-agent approach:
  - Agent loop: observe → reason (with tools) → act → record
  - Tools: query_trades, compute_stats, update_strategy_notes
  - Memory: strategy_notes table in Supabase (persistent across runs)

Schedule: runs daily at 10 PM as part of the daily report.
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
sys.path.insert(0, str(Path(__file__).parent.parent))

SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

STRATEGY_PARAMS = {
    "vcp":          {"target_pct": 8.0,  "sl_pct": 4.0},
    "ipo_base":     {"target_pct": 12.0, "sl_pct": 5.0},
    "rocket_base":  {"target_pct": 15.0, "sl_pct": 6.0},
    "breakout":     {"target_pct": 7.0,  "sl_pct": 3.0},
    "rsi_reversal": {"target_pct": 6.0,  "sl_pct": 3.0},
    "golden_cross": {"target_pct": 10.0, "sl_pct": 4.0},
    "multibagger":  {"target_pct": 20.0, "sl_pct": 7.0},
    "custom":       {"target_pct": 10.0, "sl_pct": 5.0},
}


# ── Supabase helpers ───────────────────────────────────────────────────────────

def _sb_request(method: str, path: str, body: dict | None = None) -> Any:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
        "User-Agent":    "curl/8.4.0",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  SB {method} {path}: {e}")
        return []


def sb_get(table: str, params: str = "") -> list[dict]:
    r = _sb_request("GET", f"{table}?{params}")
    return r if isinstance(r, list) else []


def sb_upsert(table: str, body: dict) -> None:
    headers_extra = {"Prefer": "resolution=merge-duplicates,return=minimal"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    data = json.dumps(body).encode()
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates,return=minimal",
        "User-Agent":    "curl/8.4.0",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20):
            pass
    except Exception as e:
        print(f"  SB UPSERT {table}: {e}")


# ── Tool definitions (Hermes-style) ───────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_trade_performance",
            "description": "Query paper trade performance for a strategy over N days",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy": {
                        "type": "string",
                        "description": "Strategy name: vcp, ipo_base, rocket_base, breakout, rsi_reversal, golden_cross, multibagger, custom",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Lookback days (default 30)",
                        "default": 30,
                    },
                },
                "required": ["strategy"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_overall_stats",
            "description": "Get overall paper trading stats across all strategies",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 30},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_strategy_insight",
            "description": "Save an improvement insight or parameter recommendation for a strategy",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy": {"type": "string"},
                    "insight":  {"type": "string", "description": "The insight or recommendation"},
                    "action":   {"type": "string", "description": "Concrete action taken or suggested"},
                    "win_rate": {"type": "number", "description": "Observed win rate 0-100"},
                },
                "required": ["strategy", "insight"],
            },
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────────

def query_trade_performance(strategy: str, days: int = 30) -> dict:
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = sb_get(
        "paper_trades",
        f"strategy=eq.{strategy}&entry_date=gte.{since}&status=neq.open&select=*",
    )
    if not rows:
        return {"strategy": strategy, "trades": 0, "win_rate": None, "message": "No completed trades"}

    total    = len(rows)
    wins     = [r for r in rows if float(r.get("pnl") or 0) > 0]
    losses   = [r for r in rows if float(r.get("pnl") or 0) <= 0]
    total_pnl = sum(float(r.get("pnl") or 0) for r in rows)
    avg_pnl  = total_pnl / total
    win_rate = len(wins) / total * 100 if total else 0
    avg_conf = sum(int(r.get("confidence") or 0) for r in rows) / total if total else 0

    target_hits = [r for r in rows if r.get("status") == "target_hit"]
    sl_hits     = [r for r in rows if r.get("status") == "sl_hit"]
    expired     = [r for r in rows if r.get("status") == "expired"]

    return {
        "strategy":    strategy,
        "period_days": days,
        "trades":      total,
        "wins":        len(wins),
        "losses":      len(losses),
        "win_rate":    round(win_rate, 1),
        "avg_pnl":     round(avg_pnl, 2),
        "total_pnl":   round(total_pnl, 2),
        "avg_confidence": round(avg_conf, 1),
        "target_hits": len(target_hits),
        "sl_hits":     len(sl_hits),
        "expired":     len(expired),
        "best_trade":  max((float(r.get("pnl_pct") or 0) for r in rows), default=0),
        "worst_trade": min((float(r.get("pnl_pct") or 0) for r in rows), default=0),
    }


def get_overall_stats(days: int = 30) -> dict:
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = sb_get("paper_trades", f"entry_date=gte.{since}&status=neq.open&select=*")
    if not rows:
        return {"trades": 0, "message": "No completed trades in period"}

    total    = len(rows)
    wins     = sum(1 for r in rows if float(r.get("pnl") or 0) > 0)
    total_pnl = sum(float(r.get("pnl") or 0) for r in rows)

    by_strategy: dict[str, dict] = {}
    for r in rows:
        s = r.get("strategy", "unknown")
        if s not in by_strategy:
            by_strategy[s] = {"total": 0, "wins": 0, "pnl": 0.0}
        by_strategy[s]["total"] += 1
        if float(r.get("pnl") or 0) > 0:
            by_strategy[s]["wins"] += 1
        by_strategy[s]["pnl"] += float(r.get("pnl") or 0)

    ranked = sorted(
        by_strategy.items(),
        key=lambda x: x[1]["wins"] / max(x[1]["total"], 1),
        reverse=True,
    )

    return {
        "period_days":   days,
        "total_trades":  total,
        "overall_wins":  wins,
        "overall_win_rate": round(wins / total * 100, 1) if total else 0,
        "total_pnl":     round(total_pnl, 2),
        "by_strategy":   {
            s: {
                "trades":   d["total"],
                "win_rate": round(d["wins"] / d["total"] * 100, 1) if d["total"] else 0,
                "pnl":      round(d["pnl"], 2),
            }
            for s, d in by_strategy.items()
        },
        "best_strategy":  ranked[0][0] if ranked else None,
        "worst_strategy": ranked[-1][0] if ranked else None,
    }


def save_strategy_insight(strategy: str, insight: str, action: str = "", win_rate: float = 0) -> dict:
    sb_upsert("strategy_notes", {
        "strategy":    strategy,
        "insight":     insight,
        "action":      action,
        "win_rate":    win_rate,
        "updated_at":  date.today().isoformat(),
    })
    return {"saved": True, "strategy": strategy}


def execute_tool(name: str, args: dict) -> str:
    if name == "query_trade_performance":
        result = query_trade_performance(**args)
    elif name == "get_overall_stats":
        result = get_overall_stats(**args)
    elif name == "save_strategy_insight":
        result = save_strategy_insight(**args)
    else:
        result = {"error": f"Unknown tool: {name}"}
    return json.dumps(result)


# ── LLM call (Groq → OpenRouter fallback) ─────────────────────────────────────

def _call_llm(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Call Groq with tool support; fallback to OpenRouter."""
    endpoints = []

    if GROQ_API_KEY:
        endpoints.append({
            "url":     "https://api.groq.com/openai/v1/chat/completions",
            "model":   "llama-3.3-70b-versatile",
            "headers": {"Authorization": f"Bearer {GROQ_API_KEY}"},
        })
    if OPENROUTER_KEY:
        endpoints.append({
            "url":     "https://openrouter.ai/api/v1/chat/completions",
            "model":   "mistralai/mixtral-8x7b-instruct",
            "headers": {"Authorization": f"Bearer {OPENROUTER_KEY}"},
        })

    for ep in endpoints:
        payload: dict = {"model": ep["model"], "messages": messages, "temperature": 0.2}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        body = json.dumps(payload).encode()
        headers = {**ep["headers"], "Content-Type": "application/json", "User-Agent": "curl/8.4.0"}
        req = urllib.request.Request(ep["url"], data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"  LLM {ep['url']} failed: {e}")

    return {}


# ── Agent loop (Hermes-style) ──────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the One Piece Quant Strategy Agent — an autonomous AI analyst
for an Indian equity paper trading system. Your mission: analyse screener performance,
identify winning/losing patterns, and suggest concrete parameter improvements.

You have access to tools to query trade data and save insights.
Be data-driven. Focus on win rate, avg PNL, and patterns in exits (target_hit vs sl_hit vs expired).

When you find an insight, call save_strategy_insight to persist it.
After analysing all strategies, provide a concise summary report in this format:

AGENT SUMMARY
=============
[2-3 bullet points with the most important findings and actions taken]
BEST STRATEGY: [name] ([win_rate]%)
NEEDS IMPROVEMENT: [name] ([win_rate]%)
RECOMMENDATION: [one concrete suggestion]"""


def run_agent() -> str:
    """Run the Hermes-style agent loop. Returns the final summary text."""
    if not (GROQ_API_KEY or OPENROUTER_KEY):
        print("  No LLM key configured — running static analysis")
        return _static_analysis()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Today is {date.today()}. Analyse all strategy performance for the last 30 days. "
                "Use the tools to query each strategy, compute overall stats, identify the best and "
                "worst performing strategies, and save your key insights. Then give me your summary."
            ),
        },
    ]

    max_iterations = 12
    for i in range(max_iterations):
        response = _call_llm(messages, tools=TOOLS)
        if not response:
            break

        choice = response.get("choices", [{}])[0]
        msg    = choice.get("message", {})
        messages.append(msg)

        # Check for tool calls
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "")
                fn_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                result  = execute_tool(fn_name, fn_args)
                print(f"  Tool: {fn_name}({fn_args}) → {result[:120]}...")
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content":      result,
                })
        else:
            # No more tool calls — agent is done
            return msg.get("content", "")

    return messages[-1].get("content", "Analysis complete.") if messages else "Analysis complete."


def _static_analysis() -> str:
    """Fallback when no LLM key is available — pure data analysis."""
    stats = get_overall_stats(30)
    lines = ["AGENT SUMMARY (Static Analysis)", "=" * 35]

    if stats.get("trades", 0) == 0:
        return "No completed paper trades in the last 30 days. Keep running the screener!"

    lines.append(f"Total trades (30d): {stats['total_trades']}")
    lines.append(f"Overall win rate:   {stats['overall_win_rate']}%")
    lines.append(f"Total PNL:          ₹{stats['total_pnl']:,.2f}")
    lines.append("")

    by_s = stats.get("by_strategy", {})
    for strategy, data in sorted(by_s.items(), key=lambda x: -x[1]["win_rate"]):
        lines.append(
            f"  {strategy:<14} {data['trades']:>3} trades | "
            f"{data['win_rate']:>5.1f}% wins | ₹{data['pnl']:>+8,.0f}"
        )

    best  = stats.get("best_strategy")
    worst = stats.get("worst_strategy")
    lines.append(f"\nBEST STRATEGY:     {best} ({by_s.get(best, {}).get('win_rate', 0):.1f}%)")
    lines.append(f"NEEDS IMPROVEMENT: {worst} ({by_s.get(worst, {}).get('win_rate', 0):.1f}%)")

    # Save insights
    for strategy, data in by_s.items():
        if data["trades"] >= 3:
            wr = data["win_rate"]
            if wr >= 70:
                insight = f"High win rate ({wr:.0f}%) — strategy performing well"
                action  = "Maintain current parameters; consider slight target increase"
            elif wr < 40:
                insight = f"Low win rate ({wr:.0f}%) — needs review"
                action  = "Consider tightening entry conditions; review SL placement"
            else:
                insight = f"Moderate performance ({wr:.0f}%) — monitor closely"
                action  = "Continue monitoring; no parameter change yet"
            save_strategy_insight(strategy, insight, action, wr)

    return "\n".join(lines)


# ── Public interface ───────────────────────────────────────────────────────────

def get_latest_insights() -> list[dict]:
    """Fetch today's saved insights for use in daily report."""
    rows = sb_get("strategy_notes", "select=*&order=updated_at.desc&limit=20")
    return rows


def run_and_report() -> str:
    """Run agent and return summary string for daily report."""
    print("\n[Strategy Agent] Running Hermes-style analysis...")
    summary = run_agent()
    print(f"\n{summary}")
    return summary


if __name__ == "__main__":
    result = run_and_report()
    print("\n" + "=" * 60)
    print(result)
