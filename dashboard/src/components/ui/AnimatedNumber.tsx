import { useEffect, useRef, useState } from "react";
import { useMotionValue, animate } from "framer-motion";

interface AnimatedNumberProps {
  value: number;
  format?: (v: number) => string;
  className?: string;
  duration?: number;
}

export function AnimatedNumber({
  value,
  format = (v) => v.toFixed(2),
  className,
  duration = 0.6,
}: AnimatedNumberProps) {
  const motionVal = useMotionValue(value);
  const [display, setDisplay] = useState(format(value));
  const prevRef = useRef(value);

  useEffect(() => {
    const controls = animate(motionVal, value, {
      duration,
      ease: "easeOut",
      onUpdate: (v) => setDisplay(format(v)),
    });
    prevRef.current = value;
    return controls.stop;
  }, [value, duration, format, motionVal]);

  return <span className={className}>{display}</span>;
}
