"""
Validates environment, API keys, and broker connectivity before go-live.
Run with: python scripts/validate_setup.py
"""
import os
import sys

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
SKIP = "\033[90m-\033[0m"

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, msg: str = "", warn_only: bool = False):
    status = PASS if ok else (WARN if warn_only else FAIL)
    results.append((name, status, msg))
    print(f"  {status} {name}" + (f" — {msg}" if msg else ""))


def section(title: str):
    print(f"\n  {title}")
    print("  " + "─" * (len(title) + 2))


# ── .env loading ─────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

section("Environment")
required_vars = [
    "DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN",
    "DEEPSEEK_API_KEY",
    "INITIAL_CAPITAL",
]
optional_vars = [
    "SHOONYA_USER", "SHOONYA_PASSWORD", "SHOONYA_TOTP_SECRET",
    "GEMINI_API_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
    "REDIS_URL",
]

for var in required_vars:
    val = os.getenv(var, "")
    check(var, bool(val), "" if val else "not set — required")

for var in optional_vars:
    val = os.getenv(var, "")
    check(var, bool(val), "not set (optional)" if not val else "", warn_only=True)

# ── Python packages ───────────────────────────────────────────────────────────
section("Python Packages")
packages = [
    ("duckdb", "duckdb"),
    ("fastapi", "fastapi"),
    ("yfinance", "yfinance"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("openai", "openai"),  # DeepSeek client
    ("dhanhq", "dhanhq"),
    ("pyotp", "pyotp"),
    ("redis", "redis"),
    ("pydantic", "pydantic"),
    ("tenacity", "tenacity"),
    ("scipy", "scipy"),
    ("PyPortfolioOpt", "pypfopt"),
]

for display, module in packages:
    try:
        __import__(module)
        check(display, True)
    except ImportError as e:
        check(display, False, str(e))

# ── Config files ──────────────────────────────────────────────────────────────
section("Configuration Files")
config_files = [
    "config/settings.yaml",
    "config/risk_limits.yaml",
    "config/strategies.yaml",
    "data/storage/schema.sql",
]
for f in config_files:
    check(f, os.path.exists(f))

# ── Database ──────────────────────────────────────────────────────────────────
section("Database")
try:
    from data.storage.db import db
    df = db.query_df("SELECT 1 as ok")
    check("DuckDB connection", not df.empty)

    tables = db.query_df(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    )
    expected_tables = [
        "ohlcv", "signals", "orders", "positions", "daily_pnl",
        "audit_log", "backtest_results",
    ]
    for t in expected_tables:
        check(f"Table: {t}", t in tables["table_name"].values)

except Exception as e:
    check("DuckDB", False, str(e))

# ── Broker connectivity (paper mode) ─────────────────────────────────────────
section("Broker Connectivity")
if os.getenv("DHAN_CLIENT_ID") and os.getenv("DHAN_ACCESS_TOKEN"):
    try:
        from dhanhq import dhanhq
        dhan = dhanhq(os.getenv("DHAN_CLIENT_ID"), os.getenv("DHAN_ACCESS_TOKEN"))
        profile = dhan.get_profile()
        ok = isinstance(profile, dict)
        check("Dhan API", ok, "connected" if ok else str(profile))
    except Exception as e:
        check("Dhan API", False, str(e))
else:
    check("Dhan API", False, "credentials missing", warn_only=True)

# ── LLM APIs ─────────────────────────────────────────────────────────────────
section("LLM APIs")
if os.getenv("DEEPSEEK_API_KEY"):
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
        models = client.models.list()
        check("DeepSeek API", True, "connected")
    except Exception as e:
        check("DeepSeek API", False, str(e))
else:
    check("DeepSeek API", False, "DEEPSEEK_API_KEY not set", warn_only=True)

if os.getenv("GEMINI_API_KEY"):
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        check("Gemini API", True, "configured")
    except Exception as e:
        check("Gemini API", False, str(e))
else:
    check("Gemini API", False, "GEMINI_API_KEY not set (optional)", warn_only=True)

# ── Summary ───────────────────────────────────────────────────────────────────
failures = [r for r in results if FAIL in r[1]]
warnings = [r for r in results if WARN in r[1]]

print(f"\n  {'─' * 40}")
print(f"  Results: {len(results) - len(failures) - len(warnings)} passed, "
      f"{len(warnings)} warnings, {len(failures)} failed\n")

if failures:
    print("  \033[91mFailed checks (must fix before go-live):\033[0m")
    for name, _, msg in failures:
        print(f"    • {name}: {msg}")
    print()
    sys.exit(1)
else:
    print("  \033[92mAll required checks passed!\033[0m\n")
