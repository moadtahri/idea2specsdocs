import type { CSSProperties, KeyboardEvent } from 'react';
import type { WorkItem } from '../api';

// The decision register drawn as a map (after mattpocock/skills' wayfinder): each decision one row below the
// deepest decision blocking it, arrows from blocker to dependent. The frontier (open, every blocker resolved) glows.
// Motion (styles.css, off under prefers-reduced-motion): the map draws in row by row, frontier nodes breathe and
// ripple, light flows along each arrow from a settled decision into one it unlocked, and the stars twinkle.

const WIDTH = 640;
const ROW = 96;
const TOP = 34;
const LABEL = 30;

type NodeState = 'frontier' | 'waiting' | 'resolved' | 'deferred';

export const ownerLabels: Record<string, string> = {
  stakeholder: 'Yours to decide', default: 'Recommended default to confirm', repo: 'A fact from the code',
};

/** Depth of each decision: 0 without blockers, else one below its deepest blocker. */
export function depths(items: WorkItem[]): Map<string, number> {
  const byId = new Map(items.map(item => [item.id, item]));
  const depth = new Map<string, number>();
  const visit = (id: string, trail: Set<string>): number => {
    const known = depth.get(id);
    if (known !== undefined) return known;
    const item = byId.get(id);
    if (!item || trail.has(id)) return 0; // the backend forbids cycles; never loop on bad data
    trail.add(id);
    const blockers = (item.blocked_by ?? []).filter(blocker => byId.has(blocker));
    const value = blockers.length ? 1 + Math.max(...blockers.map(blocker => visit(blocker, trail))) : 0;
    trail.delete(id);
    depth.set(id, value);
    return value;
  };
  items.forEach(item => visit(item.id, new Set()));
  return depth;
}

function nodeState(item: WorkItem, frontier: Set<string>): NodeState {
  if (frontier.has(item.id)) return 'frontier';
  if (item.status === 'resolved') return 'resolved';
  if (item.status === 'deferred') return 'deferred';
  return 'waiting';
}

const stateLabels: Record<NodeState, string> = {
  frontier: 'can be decided now', waiting: 'waiting on another decision', resolved: 'decided', deferred: 'deferred',
};

function short(title: string) {
  return title.length > 30 ? `${title.slice(0, 29)}…` : title;
}

export default function DecisionMap({ items, frontier, selected, onSelect }: {
  items: WorkItem[]; frontier: string[]; selected: string; onSelect: (id: string) => void;
}) {
  const depth = depths(items);
  const rows = new Map<number, WorkItem[]>();
  items.forEach(item => rows.set(depth.get(item.id) ?? 0, [...(rows.get(depth.get(item.id) ?? 0) ?? []), item]));
  const position = new Map<string, {x: number; y: number}>();
  rows.forEach((row, level) => row.forEach((item, index) => position.set(item.id, {
    x: (WIDTH / (row.length + 1)) * (index + 1),
    y: TOP + level * ROW,
  })));
  const height = TOP * 2 + Math.max(0, ...depth.values()) * ROW + LABEL;
  const open = new Set(frontier);
  const byStatus = new Map(items.map(item => [item.id, item.status]));
  const stars = Array.from({length: 36}, (_, i) => ({x: (i * 137.5) % WIDTH, y: (i * 89.3 + 17) % height, r: 0.5 + (i % 3) * 0.35}));
  const keyed = (id: string) => (event: KeyboardEvent) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(id); }
  };

  return <figure className="decision-map" aria-label="Decision map">
    <svg viewBox={`0 0 ${WIDTH} ${height}`} role="group">
      <defs>
        <marker id="map-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" className="map-arrow" />
        </marker>
      </defs>
      {stars.map((star, i) => <circle key={i} className="map-star" cx={star.x} cy={star.y} r={star.r}
        style={{animationDelay: `${(i * 0.37) % 4}s`, animationDuration: `${3 + (i % 4)}s`}} />)}
      {items.flatMap(item => (item.blocked_by ?? []).filter(blocker => position.has(blocker)).map(blocker => {
        const from = position.get(blocker)!;
        const to = position.get(item.id)!;
        const end = to.y - 14;
        const d = `M ${from.x} ${from.y + 12} C ${from.x} ${from.y + ROW / 2}, ${to.x} ${end - ROW / 2}, ${to.x} ${end}`;
        // Unlocked: the blocker is settled and this decision can be made now; light flows along the arrow.
        const unlocked = byStatus.get(blocker) === 'resolved' && open.has(item.id);
        const delay = {animationDelay: `${(depth.get(blocker) ?? 0) * 0.18 + 0.15}s`};
        return <g key={`${blocker}-${item.id}`}>
          <path className={`map-edge${unlocked ? ' unlocked' : ''}`} markerEnd="url(#map-arrow)" d={d} pathLength={1} style={delay} />
          {unlocked && <path className="map-flow" d={d} pathLength={1} />}
        </g>;
      }))}
      {items.map((item, index) => {
        const {x, y} = position.get(item.id)!;
        const state = nodeState(item, open);
        const labelY = index % 2 && (rows.get(depth.get(item.id) ?? 0)?.length ?? 0) > 2 ? -20 : 26;
        return <g key={item.id} transform={`translate(${x} ${y})`} role="button" tabIndex={0}
          style={{'--row': depth.get(item.id) ?? 0} as CSSProperties}
          className={`map-node ${state} owner-${item.owner_type ?? 'stakeholder'}${selected === item.id ? ' selected' : ''}`}
          aria-label={`${item.title}: ${stateLabels[state]}, ${ownerLabels[item.owner_type ?? 'stakeholder']}`}
          aria-pressed={selected === item.id}
          onClick={() => onSelect(item.id)} onKeyDown={keyed(item.id)}>
          <title>{`${item.title} · ${stateLabels[state]}`}</title>
          <g className="node-body">
            {state === 'frontier' && <><circle className="ring" r={12} /><circle className="ring late" r={12} /></>}
            <circle className="halo" r={16} />
            <circle className="core" r={state === 'frontier' ? 10 : 7} />
            <text y={labelY} textAnchor="middle">{short(item.title)}</text>
          </g>
        </g>;
      })}
    </svg>
    <figcaption className="map-legend">
      <span><i className="swatch frontier" /> can be decided now</span>
      <span><i className="swatch waiting" /> waiting on another decision</span>
      <span><i className="swatch resolved" /> decided</span>
      <span><i className="swatch owner-stakeholder" /> yours</span>
      <span><i className="swatch owner-default" /> recommended default</span>
      <span><i className="swatch owner-repo" /> from the code</span>
    </figcaption>
  </figure>;
}
