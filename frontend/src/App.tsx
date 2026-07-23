import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { CurrentUser, WorkspaceOverview } from "./api/types";
import { Sidebar } from "./components/Sidebar";
import { ErrorState, LoadingState } from "./components/StateView";
import { Tabs } from "./components/Tabs";
import { TopBar } from "./components/TopBar";
import { useAsync, type AsyncState } from "./utils/useAsync";
import type { AssetTab, Route } from "./routes";
import { CheckInScreen } from "./screens/CheckInScreen";
import { CostsScreen } from "./screens/CostsScreen";
import { DashboardScreen } from "./screens/DashboardScreen";
import { HomeScreen } from "./screens/HomeScreen";
import { NewBucketScreen } from "./screens/NewBucketScreen";
import { SignInScreen } from "./screens/SignInScreen";

const TAB_LABEL: Record<AssetTab, string> = { dashboard: "Dashboard", costs: "Costs", checkin: "Check-in" };

// Auth gate: before the workspace can render, find out whether the user is signed in.
// Three outcomes — checking (spinner), not signed in (sign-in screen), signed in (the app).
export default function App() {
  useOsTheme();
  const auth = useAsync(() => api.getMe(), []);

  if (auth.loading && !auth.data) return <LoadingState label="Checking sign-in…" />;
  // Any error here means "can't proceed authenticated": a 401 is the normal unauthenticated
  // case, and a network error still can't reach the workspace — both route to sign-in.
  if (auth.error || !auth.data) return <SignInScreen />;
  return <Workspace user={auth.data} />;
}

function Workspace({ user }: { user: CurrentUser }) {
  const [route, setRoute] = useState<Route>({ kind: "home" });
  const workspace = useAsync(() => api.listAssets(), []);
  const assets = workspace.data?.assets ?? [];

  // Keep routing valid if the active asset disappears from the workspace. Only act on a
  // settled load: during a reload (e.g. right after creating a bucket and navigating to it)
  // `workspace.data` still holds the pre-refetch list, which would otherwise bounce a
  // just-created asset back to Home before its row arrives.
  useEffect(() => {
    if (route.kind === "asset" && workspace.data && !workspace.loading && !assets.some((a) => a.id === route.assetId)) {
      setRoute({ kind: "home" });
    }
  }, [route, workspace.data, workspace.loading, assets]);

  const crumbs = buildCrumbs(route, assets);

  return (
    <div className="app">
      <Sidebar assets={assets} route={route} onNavigate={setRoute} user={user} />
      <main className="main">
        <TopBar crumbs={crumbs} />
        {route.kind === "asset" && (
          <Tabs
            value={route.tab}
            onChange={(tab) => setRoute({ ...route, tab })}
            items={[
              { value: "dashboard", label: "Dashboard" },
              { value: "costs", label: "Costs" },
              { value: "checkin", label: "Check-in" },
            ]}
          />
        )}
        <Content route={route} setRoute={setRoute} workspace={workspace} />
      </main>
    </div>
  );
}

function Content({
  route,
  setRoute,
  workspace,
}: {
  route: Route;
  setRoute: (r: Route) => void;
  workspace: AsyncState<WorkspaceOverview>;
}) {
  if (route.kind === "new") {
    return (
      <NewBucketScreen
        onCancel={() => setRoute({ kind: "home" })}
        onCreated={(id) => {
          workspace.reload();
          setRoute({ kind: "asset", assetId: id, tab: "dashboard" });
        }}
      />
    );
  }

  if (route.kind === "asset") {
    if (route.tab === "dashboard") {
      return <DashboardScreen assetId={route.assetId} onTab={(tab) => setRoute({ ...route, tab })} />;
    }
    if (route.tab === "costs") {
      return <CostsScreen assetId={route.assetId} onChanged={() => workspace.reload()} />;
    }
    return (
      <CheckInScreen
        assetId={route.assetId}
        onPosted={() => {
          workspace.reload();
        }}
      />
    );
  }

  // Home
  if (workspace.loading) return <LoadingState label="Loading your workspace…" />;
  if (workspace.error || !workspace.data) {
    return <ErrorState message={workspace.error ?? "Could not load workspace."} onRetry={workspace.reload} />;
  }
  return (
    <HomeScreen
      overview={workspace.data}
      onOpenAsset={(id) => setRoute({ kind: "asset", assetId: id, tab: "dashboard" })}
      onNew={() => setRoute({ kind: "new" })}
    />
  );
}

function buildCrumbs(route: Route, assets: { id: string; name: string }[]): string[] {
  if (route.kind === "home") return ["Workspace", "Overview"];
  if (route.kind === "new") return ["Workspace", "New bucket"];
  const name = assets.find((a) => a.id === route.assetId)?.name ?? "Asset";
  return ["Workspace", name, TAB_LABEL[route.tab]];
}

// Mirrors the OS light/dark preference onto <html data-theme>, which the
// stylesheet keys off. Replaces the design's in-app theme switcher.
function useOsTheme() {
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme = mq.matches ? "dark" : "light";
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
}
