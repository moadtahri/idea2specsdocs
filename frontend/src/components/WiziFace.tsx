/**
 * wizi's face, and its only mark: the wobbly glowing ball (ThinkingOrb). It drifts slowly while it is on standby
 * and moves fast while it thinks (D48, the user's choice; it replaced the fennec fox and the separate thinking orb).
 * `state="still"` draws it without motion, for older messages, so a long chat does not fill with moving balls. Under
 * reduced motion it is always still.
 */
import { ThinkingOrb } from "./ThinkingOrb";

export type FaceState = "thinking" | "standby" | "still";
const PACE: Record<Exclude<FaceState, "still">, number> = { thinking: 2, standby: 9 };

interface Props {
  size?: number;
  state?: FaceState;
  /** Say "wizi" to screen readers (off when its name is written beside it). */
  label?: string;
  className?: string;
}

export function WiziFace({ size = 36, state = "standby", label, className = "" }: Props) {
  return (
    <span
      className={`wizi-face wizi-face-${state} ${className}`.trim()}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      title={label}
      style={{ width: size, height: size }}
    >
      <ThinkingOrb size={size} animated={state !== "still"} pace={state === "still" ? 4.5 : PACE[state]} />
    </span>
  );
}
