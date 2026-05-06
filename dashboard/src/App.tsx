import React, { useState } from "react";
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
import { LoginPage, AUTH_KEY } from "@/pages/Login";

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
          height: "100vh", background: "#000", color: "#00ff41", gap: 16,
          fontFamily: '"JetBrains Mono", monospace', padding: 32, textAlign: "center",
        }}>
          <pre style={{ color: "#ff2244", fontSize: 32, margin: 0 }}>// ERROR</pre>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#00ff41" }}>SYSTEM EXCEPTION</div>
          <div style={{ fontSize: 11, color: "#00aa28", maxWidth: 480, lineHeight: 1.6 }}>
            {this.state.error.message}
          </div>
          <button
            onClick={() => { this.setState({ error: null }); window.location.href = "/"; }}
            style={{
              marginTop: 8, padding: "10px 24px",
              background: "transparent", color: "#00ff41",
              border: "1px solid #00ff41", borderRadius: 2,
              cursor: "pointer", fontSize: 11, fontWeight: 700,
              fontFamily: '"JetBrains Mono", monospace',
              letterSpacing: "0.15em",
            }}
          >
            [ RESTART ]
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem(AUTH_KEY));

  if (!authed) {
    return <LoginPage onAuth={() => setAuthed(true)} />;
  }

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
