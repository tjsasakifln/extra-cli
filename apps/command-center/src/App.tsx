import { Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { AppShell } from "./layout/AppShell";
import { AreaPage } from "./pages/AreaPage";
import { ArtifactsPage } from "./pages/ArtifactsPage";
import { CapabilitiesPage } from "./pages/CapabilitiesPage";
import { CapabilityDetailPage } from "./pages/CapabilityDetailPage";
import { ComparePage } from "./pages/ComparePage";
import { HomePage } from "./pages/HomePage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { JobsPage } from "./pages/JobsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SearchPage } from "./pages/SearchPage";
import { VisualMatrixPage } from "./pages/VisualMatrixPage";
import { WorkStartPage } from "./pages/WorkStartPage";

/** Declared routes for route-census e2e (keep in sync with Routes below). */
export const APP_ROUTES: string[] = [
  "/",
  "/work/start",
  "/compare",
  "/extra",
  "/confenge/suppliers",
  "/confenge/agencies",
  "/documents",
  "/ops",
  "/dod",
  "/actions",
  "/capabilities",
  "/jobs",
  "/review",
  "/results",
  "/artifacts",
  "/search",
  "/onboarding",
  "/__visual_matrix",
];

export default function App() {
  return (
    <ErrorBoundary area="app">
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="work/start" element={<WorkStartPage />} />
          <Route path="work/start/:workflowId" element={<WorkStartPage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="__visual_matrix" element={<VisualMatrixPage />} />
          <Route path="extra" element={<AreaPage area="extra" />} />
          <Route path="confenge/suppliers" element={<AreaPage area="suppliers" />} />
          <Route path="confenge/agencies" element={<AreaPage area="agencies" />} />
          <Route path="documents" element={<AreaPage area="documents" />} />
          <Route path="ops" element={<AreaPage area="ops" />} />
          <Route path="dod" element={<AreaPage area="dod" />} />
          <Route path="actions" element={<CapabilitiesPage />} />
          <Route path="actions/:id" element={<CapabilityDetailPage />} />
          <Route path="capabilities" element={<CapabilitiesPage />} />
          <Route path="capabilities/:id" element={<CapabilityDetailPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="jobs/:id" element={<JobDetailPage />} />
          <Route path="review" element={<ReviewPage />} />
          <Route path="results" element={<ArtifactsPage />} />
          <Route path="artifacts" element={<ArtifactsPage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="onboarding" element={<OnboardingPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}
