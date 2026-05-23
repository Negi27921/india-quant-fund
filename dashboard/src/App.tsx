import React, { Suspense, lazy, useState, useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { api } from "@/api/client";
import { Layout } from "@/components/layout/Layout";
import { LoginPage, hasValidSession } from "@/pages/Login";

// Route-level code splitting — each page is loaded only when navigated to.
// First paint downloads ~80KB instead of ~235KB (measured with Vite bundle analysis).
const MarketPage         = lazy(() => import("@/pages/Market").then(m => ({ default: m.MarketPage })));
const ScreenerPage       = lazy(() => import("@/pages/Screener").then(m => ({ default: m.ScreenerPage })));
const PortfolioPage      = lazy(() => import("@/pages/Portfolio").then(m => ({ default: m.PortfolioPage })));
const RiskPage           = lazy(() => import("@/pages/Risk").then(m => ({ default: m.RiskPage })));
const SettingsPage       = lazy(() => import("@/pages/Settings").then(m => ({ default: m.SettingsPage })));
const TradingJournalPage = lazy(() => import("@/pages/TradingJournal").then(m => ({ default: m.TradingJournalPage })));
const ResultsPage        = lazy(() => import("@/pages/Results").then(m => ({ default: m.ResultsPage })));
const WatchlistPage      = lazy(() => import("@/pages/Watchlist").then(m => ({ default: m.WatchlistPage })));

function PageLoader() {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: "100%", minHeight: 300,
      color: "var(--text-4)", fontFamily: "var(--font-mono)", fontSize: 13,
      letterSpacing: "0.08em",
    }}>
      loading…
    </div>
  );
}

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
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route element={<Layout />}>
                <Route index              element={<MarketPage />} />
                <Route path="screener"   element={<ScreenerPage />} />
                <Route path="portfolio"  element={<PortfolioPage />} />
                <Route path="risk"       element={<RiskPage />} />
                <Route path="settings"   element={<SettingsPage />} />
                <Route path="journal"    element={<TradingJournalPage />} />
                <Route path="results"    element={<ResultsPage />} />
                <Route path="watchlist" element={<WatchlistPage />} />
              </Route>
            </Routes>
          </Suspense>
        </AnimatePresence>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
