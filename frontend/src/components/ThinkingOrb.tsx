/**
 * Kanya's thinking mark: a glowing orb drawn as one inline SVG (noise filters and SMIL, no script, no image file).
 *
 * Ported from the old app's `ui_pages/explainer/thinking_orb.py` (redrawn there on 30 Oct 2026 from a reference the
 * user chose, in Canyas teal #00ffff and dark blue #00649a): a deep sphere whose rim is a band of wavy light
 * filaments, brightest top left, with faint cracks inside that drift, fine specks low down and a soft halo, on a
 * 4.5 s loop.
 *
 * Every instance gets its own ids (useId), so several orbs on a page never share a filter. SMIL ignores
 * prefers-reduced-motion, so when that setting is on (or `animated` is false) the still copy is drawn: the same orb
 * without its <animate> elements.
 */
import { useId } from "react";

import { usePrefersReducedMotion } from "../lib/usePrefersReducedMotion";

/** Rim filaments: radius, stroke width, opacity, wobble (noise seed, frequency, displacement). */
const STRANDS: ReadonlyArray<readonly [number, number, number, readonly [number, number, number]]> = [
  [40.0, 1.8, 1.0, [2, 0.022, 4]],
  [39.2, 1.1, 0.9, [7, 0.03, 5]],
  [38.4, 0.9, 0.8, [11, 0.026, 5.5]],
  [37.6, 0.7, 0.65, [17, 0.034, 6]],
  [40.8, 0.8, 0.7, [23, 0.02, 4.5]],
  [36.8, 0.5, 0.5, [29, 0.03, 6.5]],
  [39.6, 0.6, 0.75, [31, 0.038, 5]],
];

/** Glints: x, y, radius, begin (s); more of them low down. */
const DOTS: ReadonlyArray<readonly [number, number, number, number]> = [
  [34, 72, 0.7, 0],
  [44, 80, 0.55, 0.6],
  [58, 78, 0.7, 1.2],
  [66, 70, 0.5, 1.9],
  [28, 60, 0.5, 2.4],
  [52, 86, 0.5, 3.1],
  [72, 58, 0.45, 3.6],
  [39, 30, 0.45, 1.5],
  [62, 26, 0.4, 2.8],
  [24, 44, 0.4, 0.9],
  [76, 40, 0.4, 3.9],
  [47, 66, 0.4, 2.1],
];

/** The noise's midpoint contour: a network of thin cracks. */
const VEIN_BAND = [...Array<string>(15).fill("0"), "1", ...Array<string>(15).fill("0")].join(" ");

/** Python's round(x, 4) / f"{x:.1f}" for the attribute values, so the port draws exactly what the old app drew. */
const r4 = (value: number) => String(Math.round(value * 10000) / 10000);
const f1 = (value: number) => value.toFixed(1);

function Strand({
  id,
  n,
  seed,
  freq,
  scale,
  animated,
  dur,
}: {
  id: string;
  n: number;
  seed: number;
  freq: number;
  scale: number;
  animated: boolean;
  dur: string;
}) {
  // One filament's wobble: fractal noise displacing the stroke; its frequency and depth drift over the loop.
  const wide = r4(freq * 1.5);
  return (
    <filter id={id} x="-20%" y="-20%" width="140%" height="140%">
      <feTurbulence type="fractalNoise" baseFrequency={freq} numOctaves={2} seed={seed}>
        {animated && (
          <animate
            attributeName="baseFrequency"
            values={`${freq};${wide};${freq}`}
            dur={dur}
            repeatCount="indefinite"
          />
        )}
      </feTurbulence>
      <feDisplacementMap in="SourceGraphic" scale={scale} xChannelSelector="R" yChannelSelector="G">
        {animated && (
          <animate
            attributeName="scale"
            values={`${scale};${f1(scale * 1.6)};${scale}`}
            dur={dur}
            begin={`-${f1(n * 0.7)}s`}
            repeatCount="indefinite"
          />
        )}
      </feDisplacementMap>
    </filter>
  );
}

/** The orb's colours: Kanya's Canyas teal and dark blue, or maroon for what waits on the user (D50). */
const TONES = {
  canyas: {
    body: ["#03111c", "#062a42", "#00527f", "#00649a", "#00a9cf"],
    haze: "#00b2cd",
    rim: ["#e6ffff", "#00ffff", "#00c4e0", "#0092c4"],
    veins: "0 0 0 0 0 0 0 0 0 .78 0 0 0 0 .86 1 0 0 0 0",
    speck: "0 0 0 0 .6 0 0 0 0 1 0 0 0 0 1 12 0 0 0 -7.9",
    halo: "#00c8e6",
    glint: "#a6ffff",
  },
  maroon: {
    body: ["#160307", "#3a0714", "#6b0d24", "#800020", "#c23a55"],
    haze: "#c4314d",
    rim: ["#ffe8ec", "#ff6f8a", "#d93a5a", "#9e1838"],
    veins: "0 0 0 0 .9 0 0 0 0 .3 0 0 0 0 .4 1 0 0 0 0",
    speck: "0 0 0 0 1 0 0 0 0 .62 0 0 0 0 .72 12 0 0 0 -7.9",
    halo: "#d0405c",
    glint: "#ffc2cd",
  },
} as const;

export type OrbTone = keyof typeof TONES;

export interface ThinkingOrbProps {
  /** Width and height (any CSS length). */
  size?: string | number;
  /** False draws the still copy; it is also drawn whenever the user asks for reduced motion. */
  animated?: boolean;
  /** Seconds per loop: about 9 drifts calmly (standby), about 2 moves fast (thinking); 4.5 by default. */
  pace?: number;
  /** Its colours; Kanya's own by default. */
  tone?: OrbTone;
  className?: string;
}

export function ThinkingOrb({ size = 28, animated = true, pace = 4.5, tone = "canyas", className }: ThinkingOrbProps) {
  const c = TONES[tone];
  const reduced = usePrefersReducedMotion();
  const live = animated && !reduced;
  const dur = `${pace}s`;
  const glint = `${Math.round(1.8 * (pace / 4.5) * 100) / 100}s`;
  const p = `ko${useId().replace(/[^a-zA-Z0-9_-]/g, "")}-`; // unique per instance, safe inside url(#…)
  const url = (name: string) => `url(#${p}${name})`;

  return (
    <svg
      className={["kanya-orb", className].filter(Boolean).join(" ")}
      viewBox="0 0 100 100"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <radialGradient id={`${p}body`} cx="50%" cy="46%" r="52%">
          <stop offset="0" stopColor={c.body[0]} />
          <stop offset=".48" stopColor={c.body[1]} />
          <stop offset=".74" stopColor={c.body[2]} />
          <stop offset=".9" stopColor={c.body[3]} />
          <stop offset="1" stopColor={c.body[4]} />
        </radialGradient>
        <radialGradient id={`${p}haze`} cx="50%" cy="92%" r="62%">
          <stop offset="0" stopColor={c.haze} stopOpacity=".5" />
          <stop offset="1" stopColor={c.haze} stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${p}rim`} x1="12%" y1="8%" x2="88%" y2="92%">
          <stop offset="0" stopColor={c.rim[0]} />
          <stop offset=".25" stopColor={c.rim[1]} />
          <stop offset=".6" stopColor={c.rim[2]} />
          <stop offset="1" stopColor={c.rim[3]} />
        </linearGradient>
        <linearGradient id={`${p}low`} x1="0" y1="0" x2="0" y2="1">
          <stop offset=".62" stopColor="#fff" stopOpacity="0" />
          <stop offset=".95" stopColor="#fff" />
        </linearGradient>
        <mask id={`${p}lowmask`}>
          <rect width="100" height="100" fill={url("low")} />
        </mask>
        <filter id={`${p}glow`} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation=".8" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id={`${p}halo`} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="5" />
        </filter>
        <filter id={`${p}veins`} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency=".085" numOctaves={4} seed={5} />
          <feComponentTransfer>
            <feFuncR type="table" tableValues={VEIN_BAND} />
          </feComponentTransfer>
          <feColorMatrix type="matrix" values={c.veins} />
        </filter>
        {/* fine specks: high-frequency noise kept only at its peaks, reseeded through the loop */}
        <filter id={`${p}speck`} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves={1} seed={9}>
            {live && (
              <animate attributeName="seed" values="9;10;11;12;13;14;15;16;17" dur={dur} repeatCount="indefinite" />
            )}
          </feTurbulence>
          <feColorMatrix type="matrix" values={c.speck} />
        </filter>
        <clipPath id={`${p}in`}>
          <circle cx="50" cy="50" r="37.5" />
        </clipPath>
        {STRANDS.map(([, , , [seed, freq, scale]], n) => (
          <Strand key={n} id={`${p}w${n}`} n={n} seed={seed} freq={freq} scale={scale} animated={live} dur={dur} />
        ))}
      </defs>

      <circle cx="50" cy="50" r="41" fill={c.halo} opacity=".55" filter={url("halo")}>
        {live && <animate attributeName="opacity" values=".45;.7;.45" dur={dur} repeatCount="indefinite" />}
      </circle>
      <circle cx="50" cy="50" r="39.5" fill={url("body")} />
      <circle cx="50" cy="50" r="39" fill={url("haze")} />
      {/* the cracks drift: the noise moves with its rect, inside the clip */}
      <g clipPath={url("in")}>
        <rect width="100" height="100" filter={url("veins")} opacity=".5">
          {live && (
            <animateTransform
              attributeName="transform"
              type="translate"
              values="0 0;-6 3;-2 -4;0 0"
              dur={dur}
              repeatCount="indefinite"
            />
          )}
        </rect>
        <rect x="10" y="10" width="80" height="80" filter={url("speck")} mask={url("lowmask")} opacity=".85" />
      </g>
      <g opacity=".9">
        {DOTS.map(([x, y, radius, begin], index) => (
          <circle key={index} cx={x} cy={y} r={radius} fill={c.glint}>
            {live && (
              <animate
                attributeName="opacity"
                values=".15;1;.15"
                dur={glint}
                begin={`${begin}s`}
                repeatCount="indefinite"
              />
            )}
          </circle>
        ))}
      </g>
      {/* a soft band under the filaments, brightest top left */}
      <circle
        cx="50"
        cy="50"
        r="38.6"
        fill="none"
        stroke={url("rim")}
        strokeWidth="3.2"
        opacity=".3"
        filter={url("glow")}
      />
      <g filter={url("glow")}>
        {STRANDS.map(([radius, width, opacity], n) => (
          <circle
            key={n}
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={url("rim")}
            strokeWidth={width}
            opacity={opacity}
            filter={url(`w${n}`)}
          />
        ))}
      </g>
    </svg>
  );
}
