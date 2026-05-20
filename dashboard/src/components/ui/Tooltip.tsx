import * as RadixTooltip from "@radix-ui/react-tooltip";

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
}

export function Tooltip({ content, children, side = "top" }: TooltipProps) {
  return (
    <RadixTooltip.Provider delayDuration={300}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            side={side}
            sideOffset={6}
            style={{
              background: "var(--surface-3, #1e2535)",
              color: "var(--text-1, #e2e8f0)",
              fontSize: "11px",
              lineHeight: 1.5,
              padding: "6px 10px",
              borderRadius: 6,
              maxWidth: 280,
              border: "1px solid var(--border, rgba(255,255,255,0.08))",
              boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
              zIndex: 9999,
            }}
          >
            {content}
            <RadixTooltip.Arrow style={{ fill: "var(--surface-3, #1e2535)" }} />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
