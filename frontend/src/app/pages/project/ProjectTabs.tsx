import { useParams } from "react-router-dom";

import { DashboardSection } from "@/features/dashboard/components/DashboardSection";
import { GrowthSection } from "@/features/growth/components/GrowthSection";
import { KnowledgeSection } from "@/features/knowledge/components/KnowledgeSection";
import { MasterySection } from "@/features/mastery/components/MasterySection";
import { MaterialsSection } from "@/features/materials/components/MaterialsSection";
import { QuizSection } from "@/features/quizzes/components/QuizSection";
import { RecommendationsSection } from "@/features/recommendations/components/RecommendationsSection";
import { TutorSection } from "@/features/tutor/components/TutorSection";

/** Canonical project tabs. Paths are relative to /projects/:projectId. */
export const PROJECT_TABS = [
  { to: "overview", label: "Overview" },
  { to: "materials", label: "Materials" },
  { to: "tutor", label: "Tutor" },
  { to: "quiz", label: "Quiz" },
  { to: "growth", label: "Growth" },
  { to: "analytics", label: "Analytics" },
] as const;

function useTabProjectId(): string {
  const { projectId } = useParams<{ projectId: string }>();
  if (!projectId) throw new Error("Project tab rendered outside a project route.");
  return projectId;
}

export function ProjectOverviewTab() {
  const projectId = useTabProjectId();
  return (
    <div className="flex flex-col gap-6">
      <RecommendationsSection projectId={projectId} />
      <KnowledgeSection projectId={projectId} />
    </div>
  );
}

export function ProjectMaterialsTab() {
  const projectId = useTabProjectId();
  return (
    <div id="section-materials" aria-label="Materials">
      <MaterialsSection projectId={projectId} />
    </div>
  );
}

export function ProjectTutorTab() {
  const projectId = useTabProjectId();
  return (
    <div id="section-tutor" aria-label="Tutor">
      <TutorSection projectId={projectId} />
    </div>
  );
}

export function ProjectQuizTab() {
  const projectId = useTabProjectId();
  return (
    <div id="section-assessment" aria-label="Quiz">
      <QuizSection projectId={projectId} />
    </div>
  );
}

export function ProjectGrowthTab() {
  const projectId = useTabProjectId();
  return (
    <div id="section-growth" aria-label="Growth" className="flex flex-col gap-6">
      <MasterySection projectId={projectId} />
      <GrowthSection projectId={projectId} />
    </div>
  );
}

export function ProjectAnalyticsTab() {
  const projectId = useTabProjectId();
  return (
    <div id="section-analytics" aria-label="Analytics">
      <DashboardSection projectId={projectId} />
    </div>
  );
}
