export type AssetTab = "dashboard" | "costs" | "checkin";
export type CostsTab = "time" | "usage" | "maint";

export type Route =
  | { kind: "home" }
  | { kind: "new" }
  | { kind: "asset"; assetId: string; tab: AssetTab; costsSubTab?: CostsTab };
