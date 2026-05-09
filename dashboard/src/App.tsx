import React, { useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { Layout } from "@/components/layout/Layout";
import { MarketPage }     from "@/pages/Market";
import { ScreenerPage }   from "@/pages/Screener";
import { PortfolioPage }  from "@/pages/Portfolio";
import { RiskPage }       from "@/pages/Risk";
import { StrategiesPage } from "@/pages/Strategies";
import { SettingsPage }   from "@/pages/Settings";
import { LoginPage, AUTH_KEY } from "@/pages/Login";

/* ── Error boundary ───────────────────────────────────────────────────────── */
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) { return { error }; }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", height: "100vh", background: "#020407",
          color: "#00ff87", gap: 16, fontFamily: '"JetBrains Mono", monospace',
          padding: 32, textAlign: "center",
        }}>
          <pre style={{ color: "#f87171", fontSize: 32, margin: 0 }}>// SYSTEM FAULT</pre>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.15em" }}>EXCEPTION CAUGHT</div>
          <div style={{ fontSize: 11, color: "rgba(0,255,135,0.6)", maxWidth: 480, lineHeight: 1.8 }}>
            {this.state.error.message}
          </div>
          <button
            onClick={() => { this.setState({ error: null }); window.location.href = "/"; }}
            style={{
              marginTop: 8, padding: "10px 28px",
              background: "transparent", color: "#00ff87",
              border: "1px solid rgba(0,255,135,0.4)", borderRadius: 6,
              cursor: "pointer", fontSize: 10, fontWeight: 700,
              letterSpacing: "0.2em", fontFamily: '"JetBrains Mono", monospace',
              boxShadow: "0 0 20px rgba(0,255,135,0.1)",
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

/* ── App ──────────────────────────────────────────────────────────────────── */
export default function App() {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem(AUTH_KEY));

  if (!authed) return <LoginPage onAuth={() => setAuthed(true)} />;

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AnimatePresence mode="wait">
          <Routes>
            <Route element={<Layout />}>
              {/* 6 pages — P&L / Live / Trades merged into Portfolio */}
              <Route index          element={<MarketPage />} />
              <Route path="screener"   element={<ScreenerPage />} />
              <Route path="portfolio"  element={<PortfolioPage />} />
              <Route path="risk"       element={<RiskPage />} />
              <Route path="strategies" element={<StrategiesPage />} />
              <Route path="settings"   element={<SettingsPage />} />
            </Route>
          </Routes>
        </AnimatePresence>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
