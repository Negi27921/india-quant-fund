import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Wifi,
  Bell,
  Settings2,
  ExternalLink,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Play,
  ChevronDown,
  Copy,
  Check,
  Bot,
  RefreshCw as RefreshIcon,
  Save,
  Shield,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  useProviders,
  useBrokers,
  useAlertConfig,
  useEnvSummary,
  useProbeProviders,
  useTestTelegram,
  useAgentConfig,
  useUpdateAgentConfig,
  type ProbeResult,
  type AgentConfig,
} from "@/api/settings-queries";
import { useRiskMetrics, useRiskLimits, useDrawdownHistory, useKillSwitchStatus } from "@/api/queries";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import { StatCard } from "@/components/ui/StatCard";
import { formatCurrency, formatPct } from "@/lib/utils";
import { cn } from "@/lib/utils";

// ── Tier badges ───────────────────────────────────────────────────────────────
function TierBadge({ tier }: { tier: string }) {
  const styles: Record<string, React.CSSProperties> = {
    free:  { background: "var(--green-dim)", color: "var(--green)", border: "1px solid var(--green-border)" },
    paid:  { background: "var(--amber-dim)", color: "var(--amber)", border: "1px solid var(--amber-border)" },
    local: { background: "var(--accent-dim)", color: "var(--accent)", border: "1px solid var(--accent-border)" },
  };
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 9999,
      textTransform: "uppercase", letterSpacing: "0.08em",
      ...( styles[tier] ?? styles.paid ),
    }}>
      {tier === "local" ? "local" : tier === "free" ? "free" : "paid"}
    </span>
  );
}

// ── Status icon ───────────────────────────────────────────────────────────────
function StatusIcon({ status }: { status: "ok" | "error" | "no_key" | "empty_response" | "unknown" }) {
  if (status === "ok")             return <CheckCircle className="w-4 h-4 text-success" />;
  if (status === "no_key")         return <AlertTriangle className="w-4 h-4 text-warning" />;
  return <XCircle className="w-4 h-4 text-danger" />;
}

// ── Copy button ───────────────────────────────────────────────────────────────
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button onClick={copy} className="p-1 rounded text-text-muted hover:text-text-primary transition-colors">
      {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

// ── LLM Providers section ─────────────────────────────────────────────────────
function LLMSection() {
  const { data, isLoading } = useProviders();
  const probe = useProbeProviders();
  const [probeResults, setProbeResults] = useState<ProbeResult | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const handleProbe = async () => {
    const result = await probe.mutateAsync();
    setProbeResults(result);
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-primary" />
          <h2 className="text-sm font-semibold text-text-primary">LLM Providers</h2>
          {data && (
            <Badge variant="primary" className="text-[10px]">
              Active: {data.active}
            </Badge>
          )}
        </div>
        <button
          onClick={handleProbe}
          disabled={probe.isPending}
          className="flex items-center gap-1.5 text-xs btn-secondary"
        >
          {probe.isPending ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Play className="w-3 h-3" />
          )}
          {probe.isPending ? "Testing…" : "Test All"}
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {data?.providers.map((p) => {
            const probeResult = probeResults?.[p.id];
            const isActive = data.active === p.id;

            return (
              <motion.div
                key={p.id}
                layout
                className="card overflow-hidden transition-all"
                style={isActive ? { borderColor: "var(--accent-border)", background: "var(--accent-dim)" } : {}}
              >
                {/* Header row */}
                <button
                  className="w-full flex items-center gap-3 p-4 text-left"
                  onClick={() => setExpanded(expanded === p.id ? null : p.id)}
                >
                  {/* Active indicator */}
                  <div style={{
                    width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                    background: isActive ? "var(--accent)" : p.has_key ? "var(--green)" : "var(--surface-3)",
                    opacity: p.has_key && !isActive ? 0.5 : 1,
                  }} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-text-primary">{p.label}</span>
                      <TierBadge tier={p.tier} />
                      {isActive && (
                        <span className="text-[10px] bg-primary text-white px-1.5 py-0.5 rounded font-medium">
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-muted font-mono mt-0.5 truncate">{p.model}</p>
                  </div>

                  {/* Key status */}
                  <div className="flex items-center gap-3 shrink-0">
                    {probeResult ? (
                      <div className="flex items-center gap-1.5">
                        <StatusIcon status={probeResult.status as "ok"} />
                        <span style={{
                          fontSize: 12,
                          color: probeResult.status === "ok" ? "var(--green)" : "var(--red)",
                        }}>
                          {probeResult.status}
                        </span>
                      </div>
                    ) : (
                      <Badge variant={p.has_key ? "success" : "neutral"} dot>
                        {p.has_key ? "Key set" : "No key"}
                      </Badge>
                    )}
                    <ChevronDown className={cn(
                      "w-4 h-4 text-text-muted transition-transform",
                      expanded === p.id && "rotate-180"
                    )} />
                  </div>
                </button>

                {/* Expanded details */}
                <AnimatePresence>
                  {expanded === p.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      style={{ borderTop: "1px solid var(--border)", background: "var(--surface-2)", padding: "12px 16px", display: "flex", flexDirection: "column", gap: 12 }}
                    >
                      {/* Key preview */}
                      {p.has_key && p.key_preview && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-text-muted w-20">API Key</span>
                          <code className="text-xs font-mono text-text-secondary bg-bg-overlay px-2 py-0.5 rounded">
                            {p.key_preview}
                          </code>
                        </div>
                      )}

                      {/* Probe error */}
                      {probeResult?.error && (
                        <div style={{ fontSize: 12, color: "var(--red)", background: "var(--red-dim)", borderRadius: 6, padding: "8px", fontFamily: "var(--font-mono)" }}>
                          {probeResult.error}
                        </div>
                      )}

                      {/* Available models */}
                      <div>
                        <p className="text-xs text-text-muted mb-1.5">Available models</p>
                        <div className="flex flex-wrap gap-1.5">
                          {p.models.map((m) => (
                            <span
                              key={m}
                              style={{
                                fontSize: 10, fontFamily: "var(--font-mono)", padding: "1px 8px", borderRadius: 4,
                                border: `1px solid ${m === p.model ? "var(--accent-border)" : "var(--border)"}`,
                                color: m === p.model ? "var(--accent)" : "var(--text-3)",
                                background: m === p.model ? "var(--accent-dim)" : "var(--surface-3)",
                              }}
                            >
                              {m}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Setup link */}
                      {!p.has_key && (
                        <a
                          href={p.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
                        >
                          Get free API key at {p.url}
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}

                      {/* .env instruction */}
                      <div style={{ background: "var(--surface-3)", borderRadius: 6, padding: 8, fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-3)" }}>
                        <p style={{ color: "var(--text-2)", fontWeight: 600, marginBottom: 4 }}>.env</p>
                        {p.id === "groq"     && <><p>GROQ_API_KEY=gsk_…</p><p>GROQ_MODEL={p.model}</p><p>LLM_PROVIDER=groq</p></>}
                        {p.id === "deepseek" && <><p>DEEPSEEK_API_KEY=sk-…</p><p>LLM_PROVIDER=deepseek</p></>}
                        {p.id === "gemini"   && <><p>GEMINI_API_KEY=AIza…</p><p>LLM_PROVIDER=gemini</p></>}
                        {p.id === "qwen"     && <><p>OPENROUTER_API_KEY=sk-or-…</p><p># Free 120B models (pick one):</p><p>OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free</p><p># or: openai/gpt-oss-120b:free</p><p>LLM_PROVIDER=qwen</p></>}
                        {p.id === "ollama"   && <><p>OLLAMA_BASE_URL=http://localhost:11434</p><p>OLLAMA_MODEL={p.model}</p><p>LLM_PROVIDER=ollama</p></>}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ── Brokers section ───────────────────────────────────────────────────────────
function BrokersSection() {
  const { data, isLoading } = useBrokers();

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Wifi className="w-4 h-4 text-primary" />
        <h2 className="text-sm font-semibold text-text-primary">Brokers</h2>
      </div>
      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : (
        <div className="space-y-2">
          {data?.map((b) => (
            <div key={b.id} className="card p-4 flex items-center gap-4"
              style={{ borderColor: b.has_key ? "var(--green-border)" : "var(--border)" }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, fontWeight: 700,
                background: b.has_key ? "var(--green-dim)" : "var(--surface-3)",
                color: b.has_key ? "var(--green)" : "var(--text-3)",
              }}>
                {b.label[0]}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-text-primary">{b.label}</span>
                  <Badge variant={b.role === "primary" ? "primary" : "neutral"} className="text-[10px]">
                    {b.role}
                  </Badge>
                </div>
                {b.has_key && b.client_id_preview && (
                  <p className="text-xs text-text-muted font-mono mt-0.5">
                    ID: {b.client_id_preview}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {b.has_key ? (
                  <CheckCircle className="w-4 h-4 text-success" />
                ) : (
                  <a href={b.url} target="_blank" rel="noopener noreferrer"
                    className="text-xs text-primary hover:underline flex items-center gap-1">
                    Setup <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ── Alerts section ────────────────────────────────────────────────────────────
function AlertsSection() {
  const { data, isLoading } = useAlertConfig();
  const testTelegram = useTestTelegram();
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string } | null>(null);

  const handleTest = async () => {
    const r = await testTelegram.mutateAsync();
    setTestResult(r);
    setTimeout(() => setTestResult(null), 5000);
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Bell className="w-4 h-4 text-primary" />
        <h2 className="text-sm font-semibold text-text-primary">Alert Channels</h2>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : (
        <div className="space-y-2">
          {/* Telegram */}
          <div className="card p-4 space-y-3"
            style={{ borderColor: data?.telegram.configured ? "var(--green-border)" : "var(--border)" }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text-primary">Telegram</span>
                <Badge variant={data?.telegram.configured ? "success" : "neutral"} dot>
                  {data?.telegram.configured ? "Connected" : "Not configured"}
                </Badge>
              </div>
              {data?.telegram.configured && data.telegram.chat_id_set && (
                <button
                  onClick={handleTest}
                  disabled={testTelegram.isPending}
                  className="flex items-center gap-1.5 text-xs btn-secondary"
                >
                  {testTelegram.isPending ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Play className="w-3 h-3" />
                  )}
                  Send test
                </button>
              )}
            </div>

            {data?.telegram.token_preview && (
              <p className="text-xs font-mono text-text-muted">
                Token: {data.telegram.token_preview}
              </p>
            )}

            <AnimatePresence>
              {testResult && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  style={{
                    fontSize: 12, padding: 8, borderRadius: 6, display: "flex", alignItems: "center", gap: 8,
                    background: testResult.ok ? "var(--green-dim)" : "var(--red-dim)",
                    color: testResult.ok ? "var(--green)" : "var(--red)",
                  }}
                >
                  {testResult.ok ? (
                    <><CheckCircle className="w-3.5 h-3.5" /> Message delivered successfully</>
                  ) : (
                    <><XCircle className="w-3.5 h-3.5" /> {testResult.error}</>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {!data?.telegram.configured && (
              <div style={{ fontSize: 12, color: "var(--text-3)", background: "var(--surface-2)", borderRadius: 6, padding: 12 }}>
                <p style={{ fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>Setup steps:</p>
                <p>1. Message <span className="text-primary">@BotFather</span> → /newbot</p>
                <p>2. Copy the token → add to <code className="text-warning">.env</code> as <code>TELEGRAM_BOT_TOKEN</code></p>
                <p>3. Send a message to your bot, then visit:</p>
                <p className="font-mono text-[10px] break-all text-text-muted pl-3">
                  https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates
                </p>
                <p>4. Copy <code>"chat":{"{"}id:…{"}"}</code> → add as <code>TELEGRAM_CHAT_ID</code></p>
              </div>
            )}

            {data?.telegram.configured && !data.telegram.chat_id_set && (
              <p className="text-xs text-warning">
                ⚠ TELEGRAM_CHAT_ID not set — bot cannot send messages yet
              </p>
            )}
          </div>

          {/* Email */}
          <div className="card p-4"
            style={{ borderColor: data?.email.configured ? "var(--green-border)" : "var(--border)" }}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text-primary">Email (SMTP)</span>
                <Badge variant={data?.email.configured ? "success" : "neutral"} dot>
                  {data?.email.configured ? data.email.smtp_host : "Not configured"}
                </Badge>
              </div>
              {data?.email.user_preview && (
                <p className="text-xs font-mono text-text-muted">{data.email.user_preview}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ── Environment summary ───────────────────────────────────────────────────────
function EnvSection() {
  const { data, isLoading } = useEnvSummary();

  const rows = data
    ? [
        { label: "Environment",    value: data.env,                              mono: false },
        { label: "Paper Trading",  value: data.paper_trading ? "Yes (safe)" : "⚠ LIVE", mono: false },
        { label: "Initial Capital",value: formatCurrency(data.initial_capital),  mono: true },
        { label: "LLM Provider",   value: data.llm_provider,                    mono: true },
        { label: "Log Level",      value: data.log_level,                        mono: true },
        { label: "Redis",          value: data.redis_url,                        mono: true },
        { label: "Database",       value: data.db_path,                          mono: true },
      ]
    : [];

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Settings2 className="w-4 h-4 text-primary" />
        <h2 className="text-sm font-semibold text-text-primary">Environment</h2>
      </div>
      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-5 w-full" />
            ))}
          </div>
        ) : (
          <table className="w-full">
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border)", transition: "background 100ms" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <td style={{ padding: "10px 16px", fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)", width: 160 }}>{row.label}</td>
                  <td style={{
                    padding: "10px 16px", fontSize: 12,
                    fontFamily: row.mono ? "var(--font-mono)" : "var(--font-body)",
                    color: row.label === "Paper Trading" && !data?.paper_trading ? "var(--red)" : "var(--text-1)",
                    fontWeight: row.label === "Paper Trading" && !data?.paper_trading ? 700 : 400,
                  }}>
                    {row.value}
                  </td>
                  <td style={{ padding: "10px 16px", width: 32 }}>
                    {row.mono && <CopyButton text={row.value} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

// ── Trading Agent section ─────────────────────────────────────────────────────
function TradingAgentSection() {
  const { data: cfg, isLoading } = useAgentConfig();
  const update = useUpdateAgentConfig();
  const [draft, setDraft] = useState<Partial<AgentConfig> | null>(null);
  const current = draft ?? cfg;

  const field = (key: keyof AgentConfig, label: string, min: number, max: number, step: number, unit: string) => (
    <div key={key} className="space-y-1.5">
      <div className="flex justify-between items-center">
        <span className="text-xs text-text-muted">{label}</span>
        <span className="text-xs font-mono text-text-primary font-semibold">
          {current?.[key] as number}{unit}
        </span>
      </div>
      <input
        type="range" min={min} max={max} step={step}
        value={(current?.[key] as number) ?? min}
        onChange={e => setDraft(d => ({ ...(d ?? cfg ?? {}), [key]: parseFloat(e.target.value) }))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
        style={{ accentColor: "var(--accent)" }}
      />
      <div className="flex justify-between text-[10px] text-text-muted">
        <span>{min}{unit}</span><span>{max}{unit}</span>
      </div>
    </div>
  );

  const strategyLabels: Record<string, string> = {
    vcp: "VCP", ipo_base: "IPO Base", rocket_base: "Rocket Base",
    breakout: "Breakout", rsi_reversal: "RSI Reversal",
    golden_cross: "Golden Cross", multibagger: "Multibagger",
  };
  const allStrategies = Object.keys(strategyLabels);

  const toggleStrategy = (s: string) => {
    const active = (current?.strategies ?? allStrategies);
    const next = active.includes(s) ? active.filter(x => x !== s) : [...active, s];
    setDraft(d => ({ ...(d ?? cfg ?? {}), strategies: next }));
  };

  const handleSave = async () => {
    if (!draft) return;
    await update.mutateAsync(draft);
    setDraft(null);
  };

  const stratParams = cfg?.strategy_params ?? {};

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Bot className="w-4 h-4 text-primary" />
        <h2 className="text-sm font-semibold text-text-primary">Trading Agent</h2>
        <span className="text-[10px] text-text-muted px-2 py-0.5 rounded-full border border-border">Paper Mode</span>
      </div>

      {isLoading ? (
        <div className="card p-4 space-y-3">
          {[1,2,3,4].map(i => <div key={i} className="h-8 bg-bg-elevated rounded animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Position sizing */}
          <div className="card p-4 space-y-4">
            <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">Position Sizing</p>
            {field("min_confidence", "Min Confidence", 70, 100, 1, "%")}
            {field("trade_amount", "Trade Amount (₹)", 5000, 100000, 5000, "")}
            {field("max_open_trades", "Max Open Trades", 5, 50, 1, "")}
            {field("risk_pct_per_trade", "Risk % Per Trade", 0.5, 5, 0.5, "%")}
            {field("kill_drawdown", "Kill Switch Drawdown", 5, 30, 1, "%")}
          </div>

          {/* Strategy toggles */}
          <div className="card p-4 space-y-3">
            <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">Active Strategies</p>
            <div className="grid grid-cols-2 gap-2">
              {allStrategies.map(s => {
                const active = (current?.strategies ?? allStrategies).includes(s);
                const params = stratParams[s];
                return (
                  <button
                    key={s}
                    onClick={() => toggleStrategy(s)}
                    style={{
                      textAlign: "left", padding: 10, borderRadius: 8, fontSize: 12, transition: "all 150ms",
                      border: `1px solid ${active ? "var(--accent-border)" : "var(--border)"}`,
                      background: active ? "var(--accent-dim)" : "var(--surface-2)",
                      color: active ? "var(--text-1)" : "var(--text-3)",
                      opacity: active ? 1 : 0.7, cursor: "pointer",
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: 4, fontFamily: "var(--font-body)" }}>{strategyLabels[s]}</div>
                    {params && (
                      <div style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
                        TP +{params.target_pct}% · SL -{params.sl_pct}% · {params.hold_days}d
                      </div>
                    )}
                  </button>
                );
              })}
            </div>

            {draft && (
              <button
                onClick={handleSave}
                disabled={update.isPending}
                className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-all"
                style={{ background: "var(--accent)", color: "#fff" }}
              >
                {update.isPending ? <RefreshIcon className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                {update.isPending ? "Saving…" : "Save Configuration"}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

// ── Risk Monitor section (merged from Risk page) ──────────────────────────────
function LimitBar({ label, value, limit, unit = "%" }: { label: string; value: number; limit: number; unit?: string }) {
  const pct = Math.min((value / limit) * 100, 100);
  const isDanger = value >= limit;
  const isWarn   = value >= limit * 0.75;
  const valColor = isDanger ? "var(--red)" : isWarn ? "var(--amber)" : "var(--text-1)";
  const barColor = isDanger ? "var(--red)" : isWarn ? "var(--amber)" : "var(--accent)";
  return (
    <div style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: "var(--text-2)", fontFamily: "var(--font-body)" }}>{label}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", fontWeight: 600, color: valColor }}>
            {value.toFixed(2)}{unit}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-3)" }}>/ {limit}{unit}</span>
          {isDanger ? <XCircle style={{ width: 13, height: 13, color: "var(--red)" }} /> :
           isWarn   ? <AlertTriangle style={{ width: 13, height: 13, color: "var(--amber)" }} /> :
                      <CheckCircle style={{ width: 13, height: 13, color: "var(--green)" }} />}
        </div>
      </div>
      <div style={{ height: 5, borderRadius: 9999, background: "var(--surface-3)", overflow: "hidden" }}>
        <motion.div
          style={{ height: "100%", borderRadius: 9999, background: barColor }}
          initial={{ width: 0 }} animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

function RiskSection() {
  const { data: risk, isLoading: riskLoading } = useRiskMetrics();
  const { data: limits } = useRiskLimits();
  const { data: dd } = useDrawdownHistory(90);
  const { data: ks } = useKillSwitchStatus();
  const ksActive = ks?.active;

  return (
    <section className="space-y-4">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Shield style={{ width: 15, height: 15, color: "var(--accent)" }} />
        <h2 style={{ fontSize: 13, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-body)" }}>
          Risk Monitor
        </h2>
      </div>

      {/* Kill switch */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderRadius: 10,
        border: `1px solid ${ksActive ? "rgba(248,113,113,0.3)" : "rgba(34,197,94,0.3)"}`,
        background: ksActive ? "rgba(248,113,113,0.07)" : "rgba(34,197,94,0.06)",
      }}>
        {ksActive
          ? <XCircle style={{ width: 22, height: 22, color: "var(--red)", flexShrink: 0 }} />
          : <CheckCircle style={{ width: 22, height: 22, color: "var(--green)", flexShrink: 0 }} />}
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: ksActive ? "var(--red)" : "var(--green)", fontFamily: "var(--font-body)" }}>
            Kill Switch: {ksActive ? "ACTIVE — Trading Halted" : "Inactive — Normal Operation"}
          </p>
          {ks?.reason && <p style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>{ks.reason}</p>}
        </div>
        <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.1em", padding: "3px 10px", borderRadius: 9999, background: ksActive ? "var(--red)" : "var(--green)", color: "#fff" }}>
          {ksActive ? "HALTED" : "LIVE"}
        </span>
      </div>

      {/* KPI grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {riskLoading ? Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 80, borderRadius: 10 }} />
        )) : (
          <>
            <StatCard label="Current Drawdown" value={<span style={{ color: "var(--red)" }}>{formatPct(-(risk?.drawdown_pct ?? 0))}</span>} subValue={`Alert: ${risk?.drawdown_alert}% | Limit: ${risk?.drawdown_limit}%`} variant={(risk?.drawdown_pct ?? 0) >= (risk?.drawdown_limit ?? 12) ? "danger" : "default"} delay={0} />
            <StatCard label="Daily P&L" value={<span style={{ color: (risk?.daily_loss_pct ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>{formatPct(risk?.daily_loss_pct ?? 0)}</span>} subValue={`Limit: -${risk?.daily_loss_limit}%`} delay={0.05} />
            <StatCard label="Sharpe (63d)" value={<span style={{ color: (risk?.rolling_sharpe_63d ?? 0) >= 1 ? "var(--green)" : "var(--amber)" }}>{(risk?.rolling_sharpe_63d ?? 0).toFixed(2)}</span>} subValue="Annualised, RFR 6.5%" delay={0.1} />
            <StatCard label="Max Position" value={`${risk?.max_position_pct ?? 0}%`} subValue={`Sector cap: ${risk?.max_sector_pct ?? 0}%`} delay={0.15} />
          </>
        )}
      </div>

      {/* Drawdown chart + limit bars */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card" style={{ padding: 16 }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: "var(--text-2)", marginBottom: 12 }}>Drawdown (90d)</p>
          <DrawdownChart data={dd ?? []} alertLevel={risk?.drawdown_alert} limitLevel={risk?.drawdown_limit} height={140} />
        </div>
        <div className="card" style={{ padding: 16 }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: "var(--text-2)", marginBottom: 8 }}>Limit Utilisation</p>
          {risk ? (
            <>
              <LimitBar label="Portfolio Drawdown" value={Math.abs(risk.drawdown_pct)} limit={risk.drawdown_limit} />
              <LimitBar label="Daily Loss" value={Math.abs(Math.min(0, risk.daily_loss_pct))} limit={risk.daily_loss_limit} />
              <LimitBar label="Max Position" value={risk.position_utilization_pct ?? 0} limit={risk.max_position_pct} />
              <LimitBar label="Sector Exposure" value={risk.sector_utilization_pct ?? 0} limit={risk.max_sector_pct} />
            </>
          ) : Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 40, borderRadius: 6, marginBottom: 10 }} />
          ))}
        </div>
      </div>

      {/* Risk config limits */}
      {limits && (
        <div className="card" style={{ padding: 16 }}>
          <p style={{ fontSize: 10, fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 12 }}>
            Risk Configuration (risk_limits.yaml)
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
            {Object.entries(limits).map(([section, vals]) => (
              <div key={section} style={{ background: "var(--surface-2)", borderRadius: 8, padding: 12 }}>
                <p style={{ fontSize: 9, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 700, marginBottom: 8 }}>{section}</p>
                {Object.entries(vals as Record<string, number>).map(([k, v]) => (
                  <div key={k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "3px 0" }}>
                    <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>{k.replace(/_/g, " ")}</span>
                    <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-1)" }}>{v}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
type SettingsTab = "agent" | "connections" | "risk";

export function SettingsPage() {
  const [tab, setTab] = useState<SettingsTab>("agent");

  const tabs: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
    { id: "agent",       label: "Trading Agent Config", icon: <Bot style={{ width: 13, height: 13 }} /> },
    { id: "connections", label: "Connections & Alerts",  icon: <Wifi style={{ width: 13, height: 13 }} /> },
    { id: "risk",        label: "Risk Monitor",          icon: <Shield style={{ width: 13, height: 13 }} /> },
  ];

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Settings & Configuration" subtitle="Trading agent · providers · risk limits" />
      <div className="flex-1 p-6 overflow-y-auto">
        <div className="max-w-3xl mx-auto">
          {/* Tab bar */}
          <div style={{ display: "flex", gap: 4, marginBottom: 24, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 4 }}>
            {tabs.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                  padding: "8px 14px", borderRadius: 7, cursor: "pointer",
                  fontSize: 12, fontWeight: 600, fontFamily: "var(--font-body)",
                  border: "none", transition: "all 150ms",
                  background: tab === t.id ? "var(--accent)" : "transparent",
                  color: tab === t.id ? "#fff" : "var(--text-3)",
                }}
              >
                {t.icon} {t.label}
              </button>
            ))}
          </div>

          {tab === "agent" && (
            <div className="space-y-8">
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <TradingAgentSection />
              </motion.div>
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 }}>
                <LLMSection />
              </motion.div>
            </div>
          )}

          {tab === "connections" && (
            <div className="space-y-8">
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <BrokersSection />
              </motion.div>
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 }}>
                <AlertsSection />
              </motion.div>
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}>
                <EnvSection />
              </motion.div>
            </div>
          )}

          {tab === "risk" && (
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <RiskSection />
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
