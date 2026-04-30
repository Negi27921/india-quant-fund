import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";
import { useKillSwitchStatus, useResetKillSwitch } from "@/api/queries";

export function KillSwitchBanner() {
  const { data: ks } = useKillSwitchStatus();
  const reset = useResetKillSwitch();
  const [hidden, setHidden] = useState(false);

  const active = ks?.active && !hidden;

  return (
    <AnimatePresence>
      {active && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="bg-danger/10 border-b border-danger/30 overflow-hidden"
        >
          <div className="flex items-center gap-3 px-6 py-2.5">
            <AlertTriangle className="w-4 h-4 text-danger shrink-0 animate-pulse" />
            <p className="flex-1 text-sm text-danger font-medium">
              KILL SWITCH ACTIVE — All trading halted.{" "}
              {ks?.reason && (
                <span className="font-normal text-danger/80">{ks.reason}</span>
              )}
            </p>
            <button
              onClick={() =>
                reset.mutate("Manual reset via dashboard", {
                  onSuccess: () => setHidden(true),
                })
              }
              disabled={reset.isPending}
              className="text-xs bg-danger hover:bg-danger-hover text-white px-3 py-1 rounded-md transition-colors disabled:opacity-50"
            >
              {reset.isPending ? "Resetting…" : "Reset"}
            </button>
            <button
              onClick={() => setHidden(true)}
              className="p-1 text-danger/60 hover:text-danger transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
