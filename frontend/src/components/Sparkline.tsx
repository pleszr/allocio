import { useRef, useState, type MouseEvent } from "react";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  padding?: number;
  // When provided (one label per point, parallel to `data`), the chart becomes hoverable: a small
  // tooltip shows the point's label, its formatted value, and the change from the prior point.
  months?: string[];
  fmtValue?: (v: number) => string;
}

// Area + line sparkline. Purely presentational; expects at least one point. Renders identically to
// before when `months` is omitted — the hover behavior only activates when a caller opts in.
export function Sparkline({ data, width = 900, height = 130, padding = 12, months, fmtValue }: SparklineProps) {
  const points = data.length >= 2 ? data : [data[0] ?? 0, data[0] ?? 0];
  // `points` may be padded to length 2 above (a single real point needs two to draw a line); pad
  // `months` the same way so hover indices always line up between the two arrays.
  const monthLabels = months && (months.length >= 2 ? months : [months[0] ?? "", months[0] ?? ""]);
  const ink = "var(--ink)";
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const w = width - padding * 2;
  const h = height - padding * 2;
  const pts = points.map((v, i) => {
    const x = padding + (i / (points.length - 1)) * w;
    const y = padding + h - ((v - min) / range) * h;
    return [x, y] as const;
  });
  const path = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(" ");
  const last = pts[pts.length - 1];
  const area = `${path} L${last[0]},${padding + h} L${pts[0][0]},${padding + h} Z`;
  const fmt = fmtValue ?? ((v: number) => v.toFixed(0));

  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const hoverable = !!months;

  const onMove = (evt: MouseEvent<HTMLDivElement>) => {
    if (!hoverable || !wrapRef.current) return;
    const rect = wrapRef.current.getBoundingClientRect();
    const frac = (evt.clientX - rect.left) / rect.width;
    const idx = Math.round(frac * (points.length - 1));
    setHoverIdx(Math.max(0, Math.min(points.length - 1, idx)));
  };

  const hp = hoverIdx != null ? pts[hoverIdx] : null;
  const hoverPct = hoverIdx != null ? hoverIdx / (points.length - 1) : 0;

  return (
    <div
      ref={wrapRef}
      style={{ position: "relative", width: "100%" }}
      onMouseMove={hoverable ? onMove : undefined}
      onMouseLeave={hoverable ? () => setHoverIdx(null) : undefined}
    >
      <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="sparkfill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={ink} stopOpacity="0.10" />
            <stop offset="100%" stopColor={ink} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#sparkfill)" />
        <path
          d={path}
          fill="none"
          stroke={ink}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        {hp ? (
          <>
            <line
              x1={hp[0]}
              y1={padding}
              x2={hp[0]}
              y2={padding + h}
              stroke={ink}
              strokeOpacity="0.15"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
            <circle cx={hp[0]} cy={hp[1]} r="3.5" fill={ink} />
          </>
        ) : (
          <>
            <circle cx={last[0]} cy={last[1]} r="3" fill={ink} />
            <circle cx={last[0]} cy={last[1]} r="6" fill={ink} fillOpacity="0.12" />
          </>
        )}
      </svg>
      {hoverIdx != null && monthLabels && (
        <div
          style={{
            position: "absolute",
            top: 0,
            pointerEvents: "none",
            left: `${Math.min(78, Math.max(0, hoverPct * 100))}%`,
            transform: `translateX(${hoverPct > 0.75 ? "-100%" : "0"})`,
            background: "var(--ink)",
            color: "var(--paper)",
            borderRadius: 8,
            padding: "6px 10px",
            fontSize: 11.5,
            lineHeight: 1.4,
            whiteSpace: "nowrap",
            boxShadow: "0 4px 14px rgba(0,0,0,.18)",
            zIndex: 5,
          }}
        >
          <div style={{ fontWeight: 600 }}>{monthLabels[hoverIdx]}</div>
          <div>
            {fmt(points[hoverIdx])}
            {hoverIdx > 0 && (
              <span style={{ opacity: 0.75 }}>
                {" "}
                · {points[hoverIdx] - points[hoverIdx - 1] >= 0 ? "+" : "−"}
                {fmt(Math.abs(points[hoverIdx] - points[hoverIdx - 1]))}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
