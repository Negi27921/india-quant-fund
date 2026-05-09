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
          justifyContent: "center", height: "100vh", background: "#0E0C0A",
          color: "#E07B54", gap: 16, fontFamily: '"Inter", system-ui, sans-serif',
          padding: 32, textAlign: "center",
        }}>
          <div style={{ color: "#E0614A", fontSize: 28, fontWeight: 700, margin: 0 }}>Something went wrong</div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", color: "#7D6E65", textTransform: "uppercase" }}>Exception caught</div>
          <div style={{ fontSize: 12, color: "#7D6E65", maxWidth: 480, lineHeight: 1.8, fontFamily: '"JetBrains Mono", monospace' }}>
            {this.state.error.message}
          </div>
          <button
            onClick={() => { this.setState({ error: null }); window.location.href = "/"; }}
            style={{
              marginTop: 8, padding: "10px 28px",
              background: "rgba(224,123,84,0.12)", color: "#E07B54",
              border: "1px solid rgba(224,123,84,0.35)", borderRadius: 8,
              cursor: "pointer", fontSize: 12, fontWeight: 600,
              letterSpacing: "0.06em", fontFamily: '"Inter", system-ui, sans-serif',
            }}
          >
            Restart
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
