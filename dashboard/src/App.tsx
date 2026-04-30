import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { Layout } from "@/components/layout/Layout";
import { PortfolioPage } from "@/pages/Portfolio";
import { LivePnLPage } from "@/pages/LivePnL";
import { TradesPage } from "@/pages/Trades";
import { RiskPage } from "@/pages/Risk";
import { StrategiesPage } from "@/pages/Strategies";
import { SettingsPage } from "@/pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <AnimatePresence mode="wait">
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<PortfolioPage />} />
            <Route path="/live" element={<LivePnLPage />} />
            <Route path="/trades" element={<TradesPage />} />
            <Route path="/risk" element={<RiskPage />} />
            <Route path="/strategies" element={<StrategiesPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </AnimatePresence>
    </BrowserRouter>
  );
}
