interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  padding?: number;
}

// Area + line sparkline. Purely presentational; expects at least one point.
export function Sparkline({ data, width = 900, height = 130, padding = 12 }: SparklineProps) {
  const points = data.length >= 2 ? data : [data[0] ?? 0, data[0] ?? 0];
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
  return (
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
      <circle cx={last[0]} cy={last[1]} r="3" fill={ink} />
      <circle cx={last[0]} cy={last[1]} r="6" fill={ink} fillOpacity="0.12" />
    </svg>
  );
}
