// Lucide-style single-path stroke icons, ported from the design.

const ICONS: Record<string, string> = {
  home: "M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z",
  car: "M5 16h14M5 16v3M19 16v3M5 16l1.5-5a2 2 0 0 1 1.9-1.4h7.2a2 2 0 0 1 1.9 1.4L19 16M5 16H3.5a.5.5 0 0 1-.5-.5V14a1 1 0 0 1 1-1h1M19 16h1.5a.5.5 0 0 0 .5-.5V14a1 1 0 0 0-1-1h-1M8 19h2M14 19h2",
  house: "M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z",
  pet: "M5 12c0-2.5 1.5-4 3-4s3 1.5 3 4-1.5 4-3 4-3-1.5-3-4zm8 0c0-2.5 1.5-4 3-4s3 1.5 3 4-1.5 4-3 4-3-1.5-3-4zM4 17a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v.5a2 2 0 0 1-2 2h-1.5a2.5 2.5 0 0 0-2.5 2.5v.5h-4v-.5a2.5 2.5 0 0 0-2.5-2.5H6a2 2 0 0 1-2-2z",
  check: "M4 12l5 5 11-11",
  edit: "M4 20h4l11-11-4-4-11 11v4zm10-15 4 4",
  bell: "M6 8a6 6 0 1 1 12 0c0 5 2 7 2 7H4s2-2 2-7zm4 11a2 2 0 0 0 4 0",
  arrowRight: "M5 12h14m-5-5 5 5-5 5",
  plus: "M12 5v14M5 12h14",
  chevronRight: "M9 6l6 6-6 6",
  alert: "M12 9v4m0 4h.01M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0z",
  calendar: "M8 2v4m8-4v4M3 9h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z",
};

export type IconName = keyof typeof ICONS;

interface IconProps {
  name: string;
  size?: number;
  className?: string;
  stroke?: number;
}

export function Icon({ name, size = 16, className, stroke = 1.6 }: IconProps) {
  const d = ICONS[name];
  if (!d) return null;
  return (
    <svg
      className={className ?? "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}
