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
  close: "M6 6l12 12M18 6 6 18",
  alert: "M12 9v4m0 4h.01M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0z",
  calendar: "M8 2v4m8-4v4M3 9h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z",
  odometer: "M4 18a8 8 0 1 1 16 0M12 14l4-4",
  clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  battery: "M2 9h16v6H2z M18 11h2v2h-2z M6 9v6M10 9v6",
  droplet: "M12 3c3.4 4.4 6 7.6 6 10.4a6 6 0 1 1-12 0C6 10.6 8.6 7.4 12 3z",
  gear: "M12 8.5a3.5 3.5 0 1 0 .01 0zM12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6",
  discBrake: "M12 3a9 9 0 1 0 .01 0zM12 8a4 4 0 1 0 .01 0z",
  padBrake: "M3 6h7v12H3z M14 6h7v12H14z",
  tire: "M12 4a8 8 0 1 0 .01 0zM12 10a2 2 0 1 0 .01 0zM12 4v2M12 18v2M5.5 6.5l1.4 1.4M17.1 16.1l1.4 1.4M4 12h2M18 12h2M5.5 17.5l1.4-1.4M17.1 7.9l1.4-1.4",
  wrench: "M14.7 6.3a4 4 0 0 1-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 1 5.4-5.4l-2.6 2.6-2-2 2.6-2.6z",
  shield: "M12 3l7 3.5v5c0 5-3.2 8.3-7 9.5-3.8-1.2-7-4.5-7-9.5v-5z",
  shieldCheck: "M12 3l7 3.5v5c0 5-3.2 8.3-7 9.5-3.8-1.2-7-4.5-7-9.5v-5z M9 12l2 2 4-4",
  receipt: "M6 3h12v18l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3z M8.5 8h7M8.5 12h7M8.5 16h4",
  ticket: "M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v1.2a1.3 1.3 0 0 0 0 2.6V13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-1.2a1.3 1.3 0 0 0 0-2.6z M9 6.5v9",
  clipboardCheck: "M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1z M6 6h12v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1z M9 13l2 2 4-4",
  flame: "M12 2c1 3-3 4.5-3 8a3 3 0 0 0 6 0c1 1 1.5 2.3 1.5 3.5A4.5 4.5 0 0 1 12 18a5 5 0 0 1-5-5c0-4 3-6 3-8a4 4 0 0 1 2-3z",
  wind: "M4 8h9a2.5 2.5 0 1 0-2.4-3.2 M4 12h13a2.5 2.5 0 1 1-2.4 3.2 M4 16h7a2 2 0 1 1-1.7 3",
  syringe: "M17 3l4 4-2 2-1-1-7 7 1 1-2 2-1-1-2 2-2-2 2-2-1-1 2-2 1 1 7-7-1-1z M9 13l2 2",
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
