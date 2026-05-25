import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useBootstrapAuth } from "@/hooks/useAuth";
import { useAuth } from "@/store/auth";
import { CenterLoader, PageError } from "@/components/ui";
import { Layout } from "@/components/Layout";
import { OnboardingPage } from "@/pages/Onboarding";
import { FeedPage } from "@/pages/Feed";
import { VacancyDetailPage } from "@/pages/VacancyDetail";
import { LetterPage } from "@/pages/Letter";
import { TrackerPage } from "@/pages/Tracker";
import { ProfilePage } from "@/pages/Profile";

function ProtectedRoutes() {
  const profileId = useAuth((s) => s.user?.active_profile_id);
  // Без активного профиля — Onboarding
  if (profileId === null || profileId === undefined) {
    return (
      <Routes>
        <Route path="*" element={<OnboardingPage />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/feed" replace />} />
        <Route path="/feed" element={<FeedPage />} />
        <Route path="/tracker" element={<TrackerPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
      {/* full-screen pages (без bottom-nav) */}
      <Route path="/vacancies/:id" element={<VacancyDetailPage />} />
      <Route path="/vacancies/:id/letter" element={<LetterPage />} />
      <Route path="*" element={<Navigate to="/feed" replace />} />
    </Routes>
  );
}

export function App() {
  const { status, error } = useBootstrapAuth();
  if (status === "loading" || status === "idle") return <CenterLoader />;
  if (status === "error") return <PageError message={error ?? "Auth failed"} />;
  return (
    <BrowserRouter>
      <ProtectedRoutes />
    </BrowserRouter>
  );
}
