import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { Layout } from "@/components/layout/Layout";
import { MarketPage } from "@/pages/Market";
import { PortfolioPage } from "@/pages/Portfolio";
import { PnLPage } from "@/pages/PnL";
import { LivePnLPage } from "@/pages/LivePnL";
import { TradesPage } from "@/pages/Trades";
import { RiskPage } from "@/pages/Risk";
import { StrategiesPage } from "@/pages/Strategies";
import { SettingsPage } from "@/pages/Settings";
import { ScreenerPage } from "@/pages/Screener";

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          height: "100vh", background: "#000", color: "#fff", gap: 16,
          fontFamily: "Inter, sans-serif", padding: 32, textAlign: "center",
        }}>
          <div style={{ fontSize: 48, marginBottom: 8 }}>⚠️</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>Something went wrong</div>
          <div style={{ fontSize: 13, color: "#888", maxWidth: 480, lineHeight: 1.6 }}>
            {this.state.error.message}
          </div>
          <button
            onClick={() => { this.setState({ error: null }); window.location.href = "/"; }}
            style={{
              marginTop: 8, padding: "10px 24px", background: "#5B7FFF", color: "#fff",
              border: "none", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600,
            }}
          >
            Reload Dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AnimatePresence mode="wait">
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<MarketPage />} />
              <Route path="/screener" element={<ScreenerPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/pnl" element={<PnLPage />} />
              <Route path="/live" element={<LivePnLPage />} />
              <Route path="/trades" element={<TradesPage />} />
              <Route path="/risk" element={<RiskPage />} />
              <Route path="/strategies" element={<StrategiesPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </AnimatePresence>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
