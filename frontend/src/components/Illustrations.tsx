// Friendly flat illustrations used at the top of bucket cards and the dashboard
// hero. Ported verbatim from the design.
import type { IlloKind } from "../utils/assetType";

export function CarIllo() {
  return (
    <svg viewBox="0 0 240 160" width="100%" height="100%" aria-hidden="true">
      <ellipse cx="60" cy="48" rx="34" ry="10" fill="#DCE6F5" />
      <ellipse cx="180" cy="36" rx="22" ry="7" fill="#DCE6F5" />
      <rect x="20" y="120" width="200" height="6" rx="3" fill="#E4E8EF" />
      <rect x="60" y="121" width="22" height="4" rx="2" fill="#CBD3E0" />
      <rect x="120" y="121" width="22" height="4" rx="2" fill="#CBD3E0" />
      <ellipse cx="120" cy="128" rx="74" ry="5" fill="rgba(27,35,51,.08)" />
      <path d="M 50 110 L 60 86 Q 64 78 74 78 L 166 78 Q 176 78 180 86 L 192 110 Z" fill="#5B8AD9" />
      <path d="M 80 80 Q 84 60 100 58 L 144 58 Q 160 60 164 80 Z" fill="#7CA3E1" />
      <path d="M 86 80 Q 90 64 104 62 L 140 62 Q 154 64 158 80 Z" fill="#D8E5F8" />
      <rect x="120" y="62" width="2" height="18" fill="#7CA3E1" />
      <rect x="50" y="108" width="142" height="6" fill="#3F6CC0" />
      <circle cx="58" cy="100" r="3" fill="#FFE9A8" />
      <circle cx="186" cy="100" r="3" fill="#FFE9A8" />
      <circle cx="78" cy="118" r="11" fill="#1B2333" />
      <circle cx="78" cy="118" r="5" fill="#5B6478" />
      <circle cx="166" cy="118" r="11" fill="#1B2333" />
      <circle cx="166" cy="118" r="5" fill="#5B6478" />
    </svg>
  );
}

export function HouseIllo() {
  return (
    <svg viewBox="0 0 240 160" width="100%" height="100%" aria-hidden="true">
      <rect x="20" y="124" width="200" height="6" rx="3" fill="#E4E8EF" />
      <ellipse cx="120" cy="132" rx="80" ry="5" fill="rgba(27,35,51,.06)" />
      <ellipse cx="46" cy="106" rx="18" ry="22" fill="#86C49A" />
      <rect x="44" y="118" width="4" height="10" fill="#7B5B3F" />
      <ellipse cx="200" cy="114" rx="14" ry="16" fill="#86C49A" />
      <rect x="198" y="124" width="4" height="6" fill="#7B5B3F" />
      <rect x="74" y="74" width="92" height="50" fill="#F2D9B0" />
      <path d="M 64 76 L 120 40 L 176 76 Z" fill="#C75D54" />
      <path d="M 120 40 L 176 76 L 168 76 L 120 44 Z" fill="#A84840" />
      <rect x="148" y="46" width="10" height="18" fill="#C75D54" />
      <rect x="148" y="46" width="10" height="3" fill="#A84840" />
      <rect x="110" y="96" width="20" height="28" rx="2" fill="#7B5B3F" />
      <circle cx="125" cy="110" r="1.5" fill="#F2D9B0" />
      <rect x="84" y="84" width="18" height="18" fill="#9CC6E8" stroke="#fff" strokeWidth="2" />
      <rect x="138" y="84" width="18" height="18" fill="#9CC6E8" stroke="#fff" strokeWidth="2" />
      <line x1="93" y1="84" x2="93" y2="102" stroke="#fff" strokeWidth="2" />
      <line x1="84" y1="93" x2="102" y2="93" stroke="#fff" strokeWidth="2" />
      <line x1="147" y1="84" x2="147" y2="102" stroke="#fff" strokeWidth="2" />
      <line x1="138" y1="93" x2="156" y2="93" stroke="#fff" strokeWidth="2" />
    </svg>
  );
}

export function DogIllo() {
  return (
    <svg viewBox="0 0 240 160" width="100%" height="100%" aria-hidden="true">
      <rect x="20" y="124" width="200" height="6" rx="3" fill="#E4E8EF" />
      <ellipse cx="120" cy="132" rx="60" ry="4" fill="rgba(27,35,51,.06)" />
      <ellipse cx="120" cy="100" rx="48" ry="22" fill="#E0A86C" />
      <rect x="86" y="108" width="10" height="18" rx="3" fill="#C28851" />
      <rect x="106" y="110" width="10" height="16" rx="3" fill="#C28851" />
      <rect x="124" y="110" width="10" height="16" rx="3" fill="#C28851" />
      <rect x="144" y="108" width="10" height="18" rx="3" fill="#C28851" />
      <path d="M 162 92 Q 184 76 178 60" stroke="#E0A86C" strokeWidth="9" fill="none" strokeLinecap="round" />
      <ellipse cx="80" cy="86" rx="26" ry="22" fill="#E0A86C" />
      <path d="M 64 70 Q 56 52 70 50 Q 76 60 76 76 Z" fill="#A86638" />
      <path d="M 92 64 Q 100 50 106 56 Q 102 68 96 76 Z" fill="#A86638" />
      <ellipse cx="68" cy="92" rx="12" ry="10" fill="#F5DAB2" />
      <circle cx="62" cy="86" r="2" fill="#1B2333" />
      <circle cx="78" cy="86" r="2" fill="#1B2333" />
      <ellipse cx="62" cy="94" rx="3" ry="2.2" fill="#1B2333" />
      <path d="M 60 98 Q 58 104 62 105 Q 66 104 64 98 Z" fill="#E68A8A" />
      <ellipse cx="138" cy="92" rx="10" ry="7" fill="#A86638" />
      <rect x="92" y="100" width="12" height="6" fill="#4F7DD9" />
      <circle cx="98" cy="106" r="2" fill="#FFD158" />
    </svg>
  );
}

export function Illo({ kind }: { kind: IlloKind }) {
  if (kind === "car") return <CarIllo />;
  if (kind === "pet") return <DogIllo />;
  return <HouseIllo />;
}
