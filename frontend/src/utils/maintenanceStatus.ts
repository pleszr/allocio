import type { MaintenanceStatus } from "../api/types";

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
