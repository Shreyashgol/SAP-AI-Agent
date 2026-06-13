import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
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
    </QueryClientProvider>
  );
}
