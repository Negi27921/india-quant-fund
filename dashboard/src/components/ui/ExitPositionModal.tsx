import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, TrendingDown, TrendingUp, LogOut } from "lucide-react";
import { useExitPosition } from "@/api/pnl-queries";
import type { PaperPosition } from "@/api/pnl-queries";

interface Props {
  open: boolean;
  position: PaperPosition | null;
  mode: "paper" | "live";
  onClose: () => void;
}

const fmt = (n: number, decimals = 2) =>
  n.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const fmtCurrency = (n: number) =>
  "₹" + fmt(n);

export function ExitPositionModal({ open, position, mode, onClose }: Props) {
  const [quantity, setQuantity] = useState<number>(0);
  const [exitPrice, setExitPrice] = useState<string>("");
  const exitMutation = useExitPosition(mode);

  useEffect(() => {
    if (position) {
      setQuantity(position.quantity);
      setExitPrice(String(position.current_price));
    }
  }, [position]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setQuantity(0);
      setExitPrice("");
      exitMutation.reset();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!position) return null;

  const pnlPositive = position.unrealized_pnl >= 0;

  const handleExit = (fullExit: boolean) => {
    const qty = fullExit ? position.quantity : quantity;
    exitMutation.mutate(
      { ticker: position.ticker, quantity: qty },
      {
        onSuccess: () => {
          onClose();
        },
      }
    );
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            style={{
              position: "fixed",
              inset: 0,
              backgroundColor: "rgba(8, 14, 24, 0.78)",
              backdropFilter: "blur(4px)",
              zIndex: 999,
            }}
          />

          {/* Modal */}
          <motion.div
            key="modal"
            initial={{ opacity: 0, scale: 0.94, y: 24 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: 24 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            style={{
              position: "fixed",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              zIndex: 1000,
              width: "min(480px, 94vw)",
              backgroundColor: "#0B1221",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 14,
              padding: "28px 28px 24px",
              color: "#FFFFFF",
              boxShadow: "0 24px 60px rgba(0,0,0,0.55)",
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <LogOut size={18} color="#5B7FFF" />
                <span style={{ fontSize: 16, fontWeight: 600, color: "#FFFFFF" }}>
                  Exit Position
                </span>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "2px 8px",
                    borderRadius: 20,
                    backgroundColor: mode === "paper" ? "rgba(91,127,255,0.12)" : "rgba(6,214,160,0.12)",
                    color: mode === "paper" ? "#5B7FFF" : "#06D6A0",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
                >
                  {mode}
                </span>
              </div>
              <button
                onClick={onClose}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#7C8DA6",
                  padding: 4,
                  display: "flex",
                  alignItems: "center",
                  borderRadius: 6,
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Position Summary */}
            <div
              style={{
                backgroundColor: "#0D1929",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 10,
                padding: "16px 18px",
                marginBottom: 20,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#FFFFFF", letterSpacing: "0.02em" }}>
                    {position.ticker}
                  </div>
                  <div style={{ fontSize: 12, color: "#7C8DA6", marginTop: 2 }}>
                    {position.name || position.ticker}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 5,
                      justifyContent: "flex-end",
                      color: pnlPositive ? "#06D6A0" : "#FF4757",
                      fontWeight: 700,
                      fontSize: 15,
                    }}
                  >
                    {pnlPositive ? <TrendingUp size={15} /> : <TrendingDown size={15} />}
                    {pnlPositive ? "+" : ""}
                    {fmtCurrency(position.unrealized_pnl)}
                  </div>
                  <div style={{ fontSize: 12, color: pnlPositive ? "#06D6A0" : "#FF4757", marginTop: 2 }}>
                    ({pnlPositive ? "+" : ""}{fmt(position.pnl_pct)}%)
                  </div>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                {[
                  { label: "Quantity", value: String(position.quantity) },
                  { label: "Avg Buy", value: fmtCurrency(position.avg_buy_price) },
                  { label: "Current", value: fmtCurrency(position.current_price) },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <div style={{ fontSize: 11, color: "#7C8DA6", marginBottom: 3, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      {label}
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#D1E4F5" }}>{value}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Inputs */}
            <div style={{ display: "flex", gap: 14, marginBottom: 22 }}>
              <label style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: "#7C8DA6", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Exit Quantity
                </div>
                <input
                  type="number"
                  min={1}
                  max={position.quantity}
                  value={quantity}
                  onChange={(e) => setQuantity(Math.min(position.quantity, Math.max(1, Number(e.target.value))))}
                  style={{
                    width: "100%",
                    backgroundColor: "#0D1929",
                    border: "1px solid rgba(255,255,255,0.06)",
                    borderRadius: 8,
                    padding: "9px 12px",
                    color: "#FFFFFF",
                    fontSize: 14,
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </label>
              <label style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: "#7C8DA6", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Exit Price (info)
                </div>
                <input
                  type="number"
                  min={0}
                  step="0.05"
                  value={exitPrice}
                  onChange={(e) => setExitPrice(e.target.value)}
                  placeholder={String(position.current_price)}
                  style={{
                    width: "100%",
                    backgroundColor: "#0D1929",
                    border: "1px solid rgba(255,255,255,0.06)",
                    borderRadius: 8,
                    padding: "9px 12px",
                    color: "#FFFFFF",
                    fontSize: 14,
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </label>
            </div>

            {/* Error */}
            {exitMutation.isError && (
              <div
                style={{
                  backgroundColor: "rgba(255,71,87,0.1)",
                  border: "1px solid rgba(255,71,87,0.25)",
                  borderRadius: 8,
                  padding: "10px 14px",
                  fontSize: 13,
                  color: "#FF4757",
                  marginBottom: 16,
                }}
              >
                {exitMutation.error instanceof Error
                  ? exitMutation.error.message
                  : "Exit failed. Please try again."}
              </div>
            )}

            {/* Buttons */}
            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={() => handleExit(true)}
                disabled={exitMutation.isPending}
                style={{
                  flex: 1,
                  padding: "11px 0",
                  borderRadius: 8,
                  border: "none",
                  cursor: exitMutation.isPending ? "not-allowed" : "pointer",
                  backgroundColor: "#EF4444",
                  color: "#fff",
                  fontWeight: 600,
                  fontSize: 14,
                  opacity: exitMutation.isPending ? 0.6 : 1,
                  transition: "opacity 0.15s",
                }}
              >
                {exitMutation.isPending ? "Exiting..." : `Full Exit (${position.quantity})`}
              </button>
              <button
                onClick={() => handleExit(false)}
                disabled={exitMutation.isPending || quantity <= 0 || quantity >= position.quantity}
                style={{
                  flex: 1,
                  padding: "11px 0",
                  borderRadius: 8,
                  border: "1px solid #5B7FFF",
                  cursor:
                    exitMutation.isPending || quantity <= 0 || quantity >= position.quantity
                      ? "not-allowed"
                      : "pointer",
                  backgroundColor: "transparent",
                  color: "#5B7FFF",
                  fontWeight: 600,
                  fontSize: 14,
                  opacity:
                    exitMutation.isPending || quantity <= 0 || quantity >= position.quantity ? 0.45 : 1,
                  transition: "opacity 0.15s",
                }}
              >
                Partial Exit ({quantity})
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
