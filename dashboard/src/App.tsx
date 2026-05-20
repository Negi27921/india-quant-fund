import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { api } from "@/api/client";
import { Layout } from "@/components/layout/Layout";
import { MarketPage }         from "@/pages/Market";
import { ScreenerPage }       from "@/pages/Screener";
import { PortfolioPage }      from "@/pages/Portfolio";
import { RiskPage }           from "@/pages/Risk";
import { StrategiesPage }     from "@/pages/Strategies";
import { SettingsPage }       from "@/pages/Settings";
import { TradingJournalPage } from "@/pages/TradingJournal";
import { ResultsPage }        from "@/pages/Results";
import { LoginPage, hasValidSession } from "@/pages/Login";

/* ── Global error boundary ────────────────────────────────────────────────── */
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    const { error } = this.state;
    if (error) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", height: "100vh",
          background: "var(--bg)", gap: 16,
          fontFamily: "var(--font-body)", padding: 32, textAlign: "center",
        }}>
          <div style={{
            width: 56, height: 56, borderRadius: "50%",
            background: "rgba(231,76,60,0.08)",
            border: "1px solid rgba(231,76,60,0.22)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 28,
          }}>⚠</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-1)", letterSpacing: "-0.01em" }}>
            Something went wrong
          </div>
          <div style={{ fontSize: 12, color: "var(--text-3)", maxWidth: 480, lineHeight: 1.7 }}>
            {error.message}
          </div>
          <button
            onClick={() => { this.setState({ error: null }); window.location.href = "/"; }}
            style={{
              marginTop: 8, padding: "10px 28px",
              background: "var(--accent)", color: "#fff",
              border: "none", borderRadius: 9999,
              cursor: "pointer", fontSize: 13, fontWeight: 600,
              fontFamily: "var(--font-body)",
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

/* ── Application root ─────────────────────────────────────────────────────── */
export default function App() {
  const [authed, setAuthed] = useState(() => hasValidSession());

  useEffect(() => {
    if (!authed) return;
    // Pre-warm the screener scan cache so first search is fast
    api.post("/screener/prewarm?universe=nifty500").catch(() => {});
  }, [authed]);

  if (!authed) return <LoginPage onAuth={() => setAuthed(true)} />;

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AnimatePresence mode="wait">
          <Routes>
            <Route element={<Layout />}>
              <Route index              element={<MarketPage />} />
              <Route path="screener"   element={<ScreenerPage />} />
              <Route path="portfolio"  element={<PortfolioPage />} />
              <Route path="risk"       element={<RiskPage />} />
              <Route path="strategies" element={<StrategiesPage />} />
              <Route path="settings"   element={<SettingsPage />} />
              <Route path="journal"    element={<TradingJournalPage />} />
              <Route path="results"    element={<ResultsPage />} />
            </Route>
          </Routes>
        </AnimatePresence>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
