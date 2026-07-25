import { useEffect, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { api } from "./api/client";
import type { CurrentUser, UserSettings, WorkspaceOverview } from "./api/types";
import { Sidebar } from "./components/Sidebar";
import { ErrorState, LoadingState } from "./components/StateView";
import { Tabs } from "./components/Tabs";
import { TopBar } from "./components/TopBar";
import i18n, { resolveLanguage } from "./i18n";
import { CurrencyProvider } from "./utils/currency";
import { useAsync, type AsyncState } from "./utils/useAsync";
import type { AssetTab, CostsTab, Route } from "./routes";
import { CheckInScreen } from "./screens/CheckInScreen";
import { CostsScreen } from "./screens/CostsScreen";
import { DashboardScreen } from "./screens/DashboardScreen";
import { HomeScreen } from "./screens/HomeScreen";
import { NewBucketScreen } from "./screens/NewBucketScreen";
import { SignInScreen } from "./screens/SignInScreen";

// Auth gate: before the workspace can render, find out whether the user is signed in.
// Three outcomes — checking (spinner), not signed in (sign-in screen), signed in (the app).
export default function App() {
  useOsTheme();
  const { t } = useTranslation();
  const auth = useAsync(() => api.getMe(), []);

  if (auth.loading && !auth.data) return <LoadingState label={t("common.checking_sign_in")} />;
  // Any error here means "can't proceed authenticated": a 401 is the normal unauthenticated
  // case, and a network error still can't reach the workspace — both route to sign-in.
  if (auth.error || !auth.data) return <SignInScreen />;
  return <Workspace user={auth.data} />;
}

function Workspace({ user }: { user: CurrentUser }) {
  const { t } = useTranslation();
  const [route, setRoute] = useState<Route>({ kind: "home" });
  const workspace = useAsync(() => api.listAssets(), []);
  const assets = workspace.data?.assets ?? [];

  // Load the user's settings once and own them as local state, so the display formatter and the
  // popover share one source of truth. The popover updates `prefs` on save, which relabels all
  // money immediately (via CurrencyProvider) with no refetch flash.
  const settings = useAsync(() => api.getSettings(), []);
  const [prefs, setPrefs] = useState<UserSettings | null>(null);
  useEffect(() => {
    if (settings.data) setPrefs(settings.data);
  }, [settings.data]);

  // Apply the persisted language once settings resolve, and re-apply if it changes (e.g. after a
  // save). Before `prefs` resolves the app already renders English via the init `lng: 'en'`.
  useEffect(() => {
    if (prefs) void i18n.changeLanguage(resolveLanguage(prefs.language));
  }, [prefs?.language]);

  // Keep routing valid if the active asset disappears from the workspace. Only act on a
  // settled load: during a reload (e.g. right after creating a bucket and navigating to it)
  // `workspace.data` still holds the pre-refetch list, which would otherwise bounce a
  // just-created asset back to Home before its row arrives.
  useEffect(() => {
    if (route.kind === "asset" && workspace.data && !workspace.loading && !assets.some((a) => a.id === route.assetId)) {
      setRoute({ kind: "home" });
    }
  }, [route, workspace.data, workspace.loading, assets]);

  // Shared by the Tabs bar and the Dashboard's "Manage" button: landing on Costs through the tab
  // bar itself (no costsSubTab argument) always resets to "time"; only an explicit deep link (e.g.
  // Dashboard -> Manage) preserves a specific sub-tab.
  const onAssetTabChange = (tab: AssetTab, costsSubTab?: CostsTab) => {
    setRoute((r) => (r.kind === "asset" ? { ...r, tab, ...(tab === "costs" ? { costsSubTab: costsSubTab ?? "time" } : {}) } : r));
  };

  const crumbs = buildCrumbs(route, assets, t);

  // Gate the workspace on the initial settings load so money never flashes the wrong currency in
  // the sidebar/home before settings arrive.
  if (settings.error && !prefs) {
    return <ErrorState message={settings.error} onRetry={settings.reload} />;
  }
  if (!prefs) return <LoadingState label={t("common.loading_preferences")} />;

  return (
    <CurrencyProvider currency={prefs.default_currency}>
      <div className="app">
        <Sidebar
          assets={assets}
          route={route}
          onNavigate={setRoute}
          user={user}
          settings={prefs}
          onSettingsSaved={setPrefs}
        />
        <main className="main">
          <TopBar crumbs={crumbs} />
          {route.kind === "asset" && (
            <Tabs
              value={route.tab}
              onChange={onAssetTabChange}
              items={[
                { value: "dashboard", label: t("tabs.dashboard") },
                { value: "costs", label: t("tabs.costs") },
                { value: "checkin", label: t("tabs.checkin") },
              ]}
            />
          )}
          <Content route={route} setRoute={setRoute} workspace={workspace} onAssetTabChange={onAssetTabChange} />
        </main>
      </div>
    </CurrencyProvider>
  );
}

function Content({
  route,
  setRoute,
  workspace,
  onAssetTabChange,
}: {
  route: Route;
  setRoute: (r: Route) => void;
  workspace: AsyncState<WorkspaceOverview>;
  onAssetTabChange: (tab: AssetTab, costsSubTab?: CostsTab) => void;
}) {
  const { t } = useTranslation();
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
      return <DashboardScreen assetId={route.assetId} onTab={onAssetTabChange} />;
    }
    if (route.tab === "costs") {
      return (
        <CostsScreen
          key={route.costsSubTab ?? "time"}
          assetId={route.assetId}
          initialTab={route.costsSubTab ?? "time"}
          onChanged={() => workspace.reload()}
        />
      );
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
  if (workspace.loading) return <LoadingState label={t("common.loading_workspace")} />;
  if (workspace.error || !workspace.data) {
    return <ErrorState message={workspace.error ?? t("states.could_not_load_workspace")} onRetry={workspace.reload} />;
  }
  return (
    <HomeScreen
      overview={workspace.data}
      onOpenAsset={(id) => setRoute({ kind: "asset", assetId: id, tab: "dashboard" })}
      onNew={() => setRoute({ kind: "new" })}
    />
  );
}

function buildCrumbs(route: Route, assets: { id: string; name: string }[], t: TFunction): string[] {
  if (route.kind === "home") return [t("breadcrumbs.workspace"), t("breadcrumbs.overview")];
  if (route.kind === "new") return [t("breadcrumbs.workspace"), t("breadcrumbs.new_bucket")];
  const name = assets.find((a) => a.id === route.assetId)?.name ?? t("breadcrumbs.asset");
  return [t("breadcrumbs.workspace"), name, t(`tabs.${route.tab}`)];
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
