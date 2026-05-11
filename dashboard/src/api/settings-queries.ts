import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface LLMProvider {
  id: string;
  label: string;
  tier: "free" | "paid" | "local";
  model: string;
  has_key: boolean;
  key_preview: string;
  url: string;
  models: string[];
}

export interface ProvidersResponse {
  active: string;
  providers: LLMProvider[];
}

export interface BrokerConfig {
  id: string;
  label: string;
  role: "primary" | "failover";
  has_key: boolean;
  client_id_preview: string;
  url: string;
}

export interface AlertConfig {
  telegram: { configured: boolean; chat_id_set: boolean; token_preview: string };
  email: { configured: boolean; smtp_host: string; user_preview: string };
}

export interface EnvSummary {
  env: string;
  paper_trading: boolean;
  initial_capital: number;
  llm_provider: string;
  log_level: string;
  redis_url: string;
  db_path: string;
}

export interface ProbeResult {
  [provider: string]: { status: string; model: string; error?: string };
}

export const useProviders = () =>
  useQuery({
    queryKey: ["settings", "providers"],
    queryFn: () => api.get<ProvidersResponse>("/settings/providers"),
    staleTime: 60_000,
  });

export const useBrokers = () =>
  useQuery({
    queryKey: ["settings", "brokers"],
    queryFn: () => api.get<BrokerConfig[]>("/settings/brokers"),
    staleTime: 60_000,
  });

export const useAlertConfig = () =>
  useQuery({
    queryKey: ["settings", "alerts"],
    queryFn: () => api.get<AlertConfig>("/settings/alerts"),
    staleTime: 60_000,
  });

export const useEnvSummary = () =>
  useQuery({
    queryKey: ["settings", "env"],
    queryFn: () => api.get<EnvSummary>("/settings/env"),
    staleTime: 60_000,
  });

export const useProbeProviders = () =>
  useMutation({
    mutationFn: () => api.post<ProbeResult>("/settings/providers/probe"),
  });

export const useTestTelegram = () =>
  useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; message_id?: number; error?: string }>(
        "/settings/alerts/test-telegram"
      ),
  });

export interface AgentConfig {
  min_confidence: number;
  trade_amount: number;
  max_open_trades: number;
  kill_drawdown: number;
  risk_pct_per_trade: number;
  strategies: string[];
  strategy_params: Record<string, { target_pct: number; sl_pct: number; hold_days: number }>;
}

export const useAgentConfig = () =>
  useQuery({
    queryKey: ["settings", "agent-config"],
    queryFn: () => api.get<AgentConfig>("/settings/agent-config"),
    staleTime: 30_000,
  });

export const useUpdateAgentConfig = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (config: Partial<AgentConfig>) =>
      api.put<{ ok: boolean }>("/settings/agent-config", config),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings", "agent-config"] }),
  });
};
