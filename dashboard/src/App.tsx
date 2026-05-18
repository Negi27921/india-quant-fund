import React, { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { Layout } from "@/components/layout/Layout";
import { MarketPage }          from "@/pages/Market";
import { ScreenerPage }        from "@/pages/Screener";
import { PortfolioPage }       from "@/pages/Portfolio";
import { RiskPage }            from "@/pages/Risk";
import { StrategiesPage }      from "@/pages/Strategies";
import { SettingsPage }        from "@/pages/Settings";
import { TradingJournalPage }  from "@/pages/TradingJournal";
import { ResultsPage }         from "@/pages/Results";
import { LoginPage, hasValidSession } from "@/pages/Login";

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
          justifyContent: "center", height: "100vh",
          background: "#F8F9FC", gap: 16,
          fontFamily: 'var(--font-body)',
          padding: 32, textAlign: "center",
        }}>
          <div style={{
            width: 56, height: 56, borderRadius: "50%",
            background: "rgba(231,76,60,0.08)",
            border: "1px solid rgba(231,76,60,0.22)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 28,
          }}>⚠</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#121317", letterSpacing: "-0.01em" }}>
            Something went wrong
          </div>
          <div style={{ fontSize: 12, color: "var(--text-3)", maxWidth: 480, lineHeight: 1.7 }}>
            {this.state.error.message}
          </div>
          <button
            onClick={() => { this.setState({ error: null }); window.location.href = "/"; }}
            style={{
              marginTop: 8, padding: "10px 28px",
              background: "var(--accent)", color: "#fff",
              border: "none", borderRadius: 9999,
              cursor: "pointer", fontSize: 13, fontWeight: 600,
              fontFamily: "var(--font-body)",
              boxShadow: "0 4px 16px rgba(106,98,86,0.3)",
            }}
          >
            Reload Terminal
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

/* ── App ──────────────────────────────────────────────────────────────────── */
export default function App() {
  const [authed, setAuthed] = useState(() => hasValidSession());

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
              <Route path="journal"    element={<TradingJournalPage />} />
              <Route path="results"    element={<ResultsPage />} />
              <Route path="risk"       element={<Navigate to="/settings" replace />} />
            </Route>
          </Routes>
        </AnimatePresence>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
