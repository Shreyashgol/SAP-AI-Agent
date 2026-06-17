import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ensureAuth } from "@/lib/api";
import ChatPage from "@/pages/ChatPage";
import ConnectionsPage from "@/pages/ConnectionsPage";
import DocumentsPage from "@/pages/DocumentsPage";
import DashboardsPage from "@/pages/DashboardsPage";
import AlertsPage from "@/pages/AlertsPage";
import AdminPage from "@/pages/AdminPage";
import DiscoveryPage from "@/pages/DiscoveryPage";
import OnboardingWizard, { useShowOnboarding } from "@/components/onboarding/OnboardingWizard";
import SemanticLayerPage from "@/pages/SemanticLayerPage";
import KnowledgeGraphPage from "@/pages/KnowledgeGraphPage";
import ToolCataloguePage from "@/pages/ToolCataloguePage";
import CustomToolBuilderPage from "@/pages/CustomToolBuilderPage";
import AppShell from "@/components/layout/AppShell";


const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 1000 * 60 * 5, // 5 minutes
      refetchOnWindowFocus: false,
    },
  },
});

function AppWithOnboarding({ children }: { children: React.ReactNode }) {
  const showOnboarding = useShowOnboarding();
  return (
    <>
      {showOnboarding && <OnboardingWizard />}
      {children}
    </>
  );
}

/** Block initial render until a token exists, so the first data queries are authenticated. */
function AuthGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ensureAuth()
      .then(() => setReady(true))
      .catch((e) => setError(e?.message ?? "Authentication failed"));
  }, []);

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-red-600">
        Could not sign in to the backend: {error}
      </div>
    );
  }
  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-gray-500">
        Connecting…
      </div>
    );
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate>
      <BrowserRouter>
        <Routes>
          <Route element={<AppWithOnboarding><AppShell /></AppWithOnboarding>}>
            <Route index element={<ChatPage />} />
            <Route path="dashboards" element={<DashboardsPage />} />
            <Route path="connections" element={<ConnectionsPage />} />
            <Route path="discovery" element={<DiscoveryPage />} />
            <Route path="semantic" element={<SemanticLayerPage />} />
            <Route path="knowledge-graph" element={<KnowledgeGraphPage />} />
            <Route path="tools" element={<ToolCataloguePage />} />
            <Route path="tools/builder" element={<CustomToolBuilderPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="admin" element={<AdminPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      </AuthGate>
    </QueryClientProvider>
  );
}
