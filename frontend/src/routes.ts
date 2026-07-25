export type AssetTab = "dashboard" | "costs" | "checkin" | "history";

export type Route =
  | { kind: "home" }
  | { kind: "new" }
  | { kind: "asset"; assetId: string; tab: AssetTab };
