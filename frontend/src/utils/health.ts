import type { Health, MaintenanceStatus } from "../api/types";

// Health → pill styling + label (dashboard hero, bucket cards).
export function healthPill(health: Health): { cls: string; label: string } {
  if (health === "underfunded") return { cls: "pill-bad", label: "Underfunded" };
  if (health === "overflowing") return { cls: "pill-good", label: "Surplus" };
  return { cls: "pill-good", label: "On track" };
}

// Health → bucket-card bottom band (icon + colored strip).
export function healthBand(health: Health): { cls: string; icon: string; label: string } {
  if (health === "underfunded") return { cls: "band-bad", icon: "alert", label: "Needs attention" };
  if (health === "overflowing") return { cls: "band-good", icon: "check", label: "Building surplus" };
  return { cls: "band-good", icon: "check", label: "All on track" };
}

// Maintenance status → pill styling + label. The backend's "due" renders as a
// "Due soon"-style pill (per the response schema note).
export function maintenancePill(status: MaintenanceStatus | null): { cls: string; label: string; fill: string } {
  switch (status) {
    case "overdue":
      return { cls: "pill-bad", label: "Overdue", fill: "bad" };
    case "due":
      return { cls: "pill-warn", label: "Due", fill: "warn" };
    case "soon":
      return { cls: "pill-warn", label: "Due soon", fill: "warn" };
    default:
      return { cls: "pill-good", label: "OK", fill: "" };
  }
}
