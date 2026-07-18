export type AssetTab = "dashboard" | "costs" | "checkin";

export type Route =
  | { kind: "home" }
  | { kind: "new" }
  | { kind: "asset"; assetId: string; tab: AssetTab };
