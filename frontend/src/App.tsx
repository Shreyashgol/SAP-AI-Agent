import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuth } from "@/stores/auth";
import SignInPage from "@/pages/SignInPage";
import SignUpPage from "@/pages/SignUpPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
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

/** Gate the protected app behind authentication. Public routes (/signin, /signup)
 * render outside this. While the session is being validated we show a spinner. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const status = useAuth((s) => s.status);
  if (status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-gray-500 dark:text-gray-400 dark:bg-gray-900">
        Connecting…
      </div>
    );
  }
  if (status === "anon") {
    return <Navigate to="/signin" replace />;
  }
  return <>{children}</>;
}

/** Redirect already-authenticated users away from the auth pages. */
function PublicOnly({ children }: { children: React.ReactNode }) {
  const status = useAuth((s) => s.status);
  if (status === "authed") return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  const init = useAuth((s) => s.init);
  useEffect(() => {
    init();
  }, [init]);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/signin" element={<PublicOnly><SignInPage /></PublicOnly>} />
          <Route path="/signup" element={<PublicOnly><SignUpPage /></PublicOnly>} />
          <Route path="/forgot-password" element={<PublicOnly><ForgotPasswordPage /></PublicOnly>} />
          <Route path="/reset-password" element={<PublicOnly><ResetPasswordPage /></PublicOnly>} />

          <Route
            element={
              <RequireAuth>
                <AppWithOnboarding>
                  <AppShell />
                </AppWithOnboarding>
              </RequireAuth>
            }
          >
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
