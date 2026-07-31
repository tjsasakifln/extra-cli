import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { AreaPage } from "./pages/AreaPage";
import { ArtifactsPage } from "./pages/ArtifactsPage";
import { CapabilitiesPage } from "./pages/CapabilitiesPage";
import { CapabilityDetailPage } from "./pages/CapabilityDetailPage";
import { HomePage } from "./pages/HomePage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { JobsPage } from "./pages/JobsPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SearchPage } from "./pages/SearchPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="extra" element={<AreaPage area="extra" />} />
        <Route path="confenge/suppliers" element={<AreaPage area="suppliers" />} />
        <Route path="confenge/agencies" element={<AreaPage area="agencies" />} />
        <Route path="documents" element={<AreaPage area="documents" />} />
        <Route path="ops" element={<AreaPage area="ops" />} />
        <Route path="dod" element={<AreaPage area="dod" />} />
        {/* Engineer-facing aliases */}
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
