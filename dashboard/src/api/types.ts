export interface PortfolioSummary {
  portfolio_value: number;
  cash: number;
  invested: number;
  day_pnl: number;
  day_pnl_pct: number;
  drawdown_pct: number;
  n_positions: number;
  equity_curve: EquityPoint[];
}

export interface EquityPoint {
  date: string;
  portfolio_value: number;
  day_pnl_pct: number;
  drawdown_pct: number;
  benchmark_ret?: number;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_buy_price: number;
  current_price: number;
  unrealized_pnl: number;
  pnl_pct: number;
  weight: number;
  sector: string;
  strategy: string;
}

export interface SectorExposure {
  sector: string;
  weight: number;
}

export interface Order {
  id: string;
  ticker: string;
  side: "BUY" | "SELL";
  quantity: number;
  order_type: string;
  status: "PENDING" | "FILLED" | "REJECTED" | "CANCELLED";
  limit_price?: number;
  avg_fill_price?: number;
  strategy: string;
  created_at: string;
  filled_at?: string;
  rejection_reason?: string;
}

export interface TradeStats {
  total_orders: number;
  filled: number;
  rejected: number;
  buys: number;
  sells: number;
  avg_fill_price: number;
}

export interface RiskMetrics {
  drawdown_pct: number;
  drawdown_alert: number;
  drawdown_limit: number;
  daily_loss_pct: number;
  daily_loss_limit: number;
  rolling_sharpe_63d: number;
  max_position_pct: number;
  max_sector_pct: number;
  position_utilization_pct: number;
  sector_utilization_pct: number;
  kill_switch_active: boolean;
}

export interface RiskLimits {
  position: Record<string, number>;
  sector: Record<string, number>;
  drawdown: Record<string, number>;
  liquidity: Record<string, number>;
}

export interface DrawdownPoint {
  date: string;
  drawdown_pct: number;
  day_pnl_pct: number;
}

export interface StrategyPerformance {
  strategy: string;
  sharpe_ratio: number;
  total_return: number;
  max_drawdown: number;
  win_rate: number;
  num_trades: number;
  run_date: string;
}

export interface Signal {
  date: string;
  ticker: string;
  strategy: string;
  signal: number;
  approved: boolean;
  rejection_reason?: string;
}

export interface StrategyAllocation {
  strategy: string;
  weight: number;
}

export interface SystemHealth {
  database: "ok" | "down";
  api: "ok";
  timestamp: string;
  paper_trading: boolean;
}

export interface KillSwitchStatus {
  active: boolean;
  triggered_at?: string;
  reason?: string;
}

export interface AuditEntry {
  timestamp: string;
  event_type: string;
  source: string;
  action: string;
  payload?: Record<string, unknown>;
}

export interface LiveData {
  portfolio_value: number;
  day_pnl: number;
  day_pnl_pct: number;
  drawdown_pct: number;
  n_positions: number;
  kill_switch_active: boolean;
  timestamp: string;
}
