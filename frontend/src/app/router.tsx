import * as React from "react";
import { Navigate, createBrowserRouter } from "react-router-dom";

import { RedirectIfAuthenticated, RequireAdmin, RequireAuth } from "@/components/auth/RequireAuth";
import { AppShell } from "@/components/layout/AppShell";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { AnalyticsPage } from "@/app/pages/AnalyticsPage";
import { HomePage } from "@/app/pages/HomePage";
import { PlaceholderPage } from "@/app/pages/PlaceholderPage";
import { MaterialDetailPage } from "@/app/pages/MaterialDetailPage";
import { ProjectDetailPage } from "@/app/pages/ProjectDetailPage";
import {
  ProjectAnalyticsTab,
  ProjectGrowthTab,
  ProjectMaterialsTab,
  ProjectOverviewTab,
  ProjectQuizTab,
  ProjectTutorTab,
} from "@/app/pages/project/ProjectTabs";
import { ProjectsPage } from "@/app/pages/ProjectsPage";
import { SpaceDetailPage } from "@/app/pages/SpaceDetailPage";
import { SpacesPage } from "@/app/pages/SpacesPage";
import { SystemPage } from "@/app/pages/SystemPage";
import { LoginPage } from "@/app/pages/auth/LoginPage";
import { RegisterPage } from "@/app/pages/auth/RegisterPage";
import { SectionLoading, SkeletonTable, SkeletonText } from "@/components/ui";

// Admin is rarely visited and table-heavy: split it out of the initial
// bundle. The fallback is a real skeleton, shown only while the chunk loads.
const AdminPage = React.lazy(() =>
  import("@/app/pages/AdminPage").then((m) => ({ default: m.AdminPage })),
);

function AdminFallback() {
  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
      <SectionLoading label="Loading administration">
        <SkeletonText lines={1} className="max-w-xs" />
        <SkeletonTable rows={4} cols={4} />
      </SectionLoading>
    </div>
  );
}

export const router = createBrowserRouter([
  {
    element: <RedirectIfAuthenticated />,
    children: [
      {
        element: <AuthLayout />,
        children: [
          { path: "/login", element: <LoginPage /> },
          { path: "/register", element: <RegisterPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/",
        element: <AppShell />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "spaces", element: <SpacesPage /> },
          { path: "spaces/:spaceId", element: <SpaceDetailPage /> },
          { path: "projects", element: <ProjectsPage /> },
          {
            path: "projects/:projectId",
            element: <ProjectDetailPage />,
            children: [
              { index: true, element: <Navigate to="overview" replace /> },
              { path: "overview", element: <ProjectOverviewTab /> },
              { path: "materials", element: <ProjectMaterialsTab /> },
              { path: "tutor", element: <ProjectTutorTab /> },
              { path: "quiz", element: <ProjectQuizTab /> },
              { path: "growth", element: <ProjectGrowthTab /> },
              { path: "analytics", element: <ProjectAnalyticsTab /> },
              { path: "*", element: <Navigate to="overview" replace /> },
            ],
          },
          {
            path: "projects/:projectId/materials/:materialId",
            element: <MaterialDetailPage />,
          },
          { path: "materials", element: <PlaceholderPage name="Materials" /> },
          { path: "tutor", element: <PlaceholderPage name="Tutor" /> },
          { path: "quizzes", element: <PlaceholderPage name="Quizzes" /> },
          { path: "mastery", element: <PlaceholderPage name="Mastery" /> },
          { path: "growth", element: <PlaceholderPage name="Growth" /> },
          { path: "recommendations", element: <PlaceholderPage name="Recommendations" /> },
          { path: "analytics", element: <AnalyticsPage /> },
          {
            element: <RequireAdmin />,
            children: [
              {
                path: "admin",
                element: (
                  <React.Suspense fallback={<AdminFallback />}>
                    <AdminPage />
                  </React.Suspense>
                ),
              },
            ],
          },
          { path: "system", element: <SystemPage /> },
        ],
      },
    ],
  },
]);
