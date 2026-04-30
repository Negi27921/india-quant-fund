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
  type ProbeResult,
} from "@/api/settings-queries";
import { formatCurrency } from "@/lib/utils";
import { cn } from "@/lib/utils";

// ── Tier badges ───────────────────────────────────────────────────────────────
function TierBadge({ tier }: { tier: string }) {
  const map: Record<string, string> = {
    free:  "bg-success/10 text-success border border-success/20",
    paid:  "bg-warning/10 text-warning border border-warning/20",
    local: "bg-primary/10 text-primary border border-primary/20",
  };
  return (
    <span className={cn("text-[10px] font-medium px-2 py-0.5 rounded-full uppercase tracking-wider", map[tier] ?? map.paid)}>
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
                className={cn(
                  "card overflow-hidden transition-all",
                  isActive && "border-primary/30 bg-primary/5"
                )}
              >
                {/* Header row */}
                <button
                  className="w-full flex items-center gap-3 p-4 text-left"
                  onClick={() => setExpanded(expanded === p.id ? null : p.id)}
                >
                  {/* Active indicator */}
                  <div className={cn(
                    "w-2 h-2 rounded-full shrink-0",
                    isActive ? "bg-primary" : p.has_key ? "bg-success/50" : "bg-bg-overlay"
                  )} />

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
                        <span className={cn(
                          "text-xs",
                          probeResult.status === "ok" ? "text-success" : "text-danger"
                        )}>
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
                      className="border-t border-border bg-bg-elevated px-4 py-3 space-y-3"
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
                        <div className="text-xs text-danger bg-danger/10 rounded p-2 font-mono">
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
                              className={cn(
                                "text-[10px] font-mono px-2 py-0.5 rounded border",
                                m === p.model
                                  ? "border-primary/40 text-primary bg-primary/10"
                                  : "border-border text-text-muted bg-bg-overlay"
                              )}
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
                      <div className="bg-bg-overlay rounded p-2 text-[10px] font-mono text-text-muted space-y-0.5">
                        <p className="text-text-secondary font-semibold mb-1">.env</p>
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
            <div key={b.id} className={cn(
              "card p-4 flex items-center gap-4",
              b.has_key ? "border-success/20" : "border-border"
            )}>
              <div className={cn(
                "w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold",
                b.has_key ? "bg-success/10 text-success" : "bg-bg-overlay text-text-muted"
              )}>
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
          <div className={cn(
            "card p-4 space-y-3",
            data?.telegram.configured ? "border-success/20" : "border-border"
          )}>
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
                  className={cn(
                    "text-xs p-2 rounded flex items-center gap-2",
                    testResult.ok ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
                  )}
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
              <div className="text-xs text-text-muted space-y-1 bg-bg-elevated rounded p-3">
                <p className="font-medium text-text-secondary">Setup steps:</p>
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
          <div className={cn(
            "card p-4",
            data?.email.configured ? "border-success/20" : "border-border"
          )}>
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
                <tr key={i} className="border-b border-border last:border-0 hover:bg-bg-elevated transition-colors">
                  <td className="px-4 py-2.5 text-xs text-text-muted w-40">{row.label}</td>
                  <td className={cn(
                    "px-4 py-2.5 text-xs",
                    row.mono ? "font-mono text-text-primary" : "text-text-primary",
                    row.label === "Paper Trading" && !data?.paper_trading && "text-danger font-semibold"
                  )}>
                    {row.value}
                  </td>
                  <td className="px-4 py-2.5 w-8">
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

// ── Main page ─────────────────────────────────────────────────────────────────
export function SettingsPage() {
  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Settings" subtitle="Connections, providers, and environment" />
      <div className="flex-1 p-6">
        <div className="max-w-3xl mx-auto space-y-8">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <LLMSection />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.07 }}
          >
            <BrokersSection />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.14 }}
          >
            <AlertsSection />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.21 }}
          >
            <EnvSection />
          </motion.div>
        </div>
      </div>
    </div>
  );
}
