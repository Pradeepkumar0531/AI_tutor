import {
  Bot,
  ClipboardList,
  FileText,
  FolderKanban,
  GraduationCap,
  Layers,
  Lightbulb,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import { PageContainer, PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui";

const TITLES: Record<string, { title: string; description: string; icon: LucideIcon }> = {
  Spaces: {
    title: "Spaces",
    description: "Group projects into spaces. Coming in the next phase.",
    icon: Layers,
  },
  Projects: {
    title: "Projects",
    description: "Projects live here. Coming in the next phase.",
    icon: FolderKanban,
  },
  Materials: {
    title: "Materials",
    description: "Uploaded learning materials. Coming in the next phase.",
    icon: FileText,
  },
  Tutor: {
    title: "Tutor",
    description: "AI tutor conversations. Coming in the next phase.",
    icon: Bot,
  },
  Quizzes: {
    title: "Quizzes",
    description: "Quizzes and assessments. Coming in the next phase.",
    icon: ClipboardList,
  },
  Mastery: {
    title: "Mastery",
    description: "Mastery tracking. Coming in the next phase.",
    icon: GraduationCap,
  },
  Growth: {
    title: "Growth",
    description: "Growth analytics. Coming in the next phase.",
    icon: TrendingUp,
  },
  Recommendations: {
    title: "Recommendations",
    description: "Recommendations. Coming in the next phase.",
    icon: Lightbulb,
  },
};

export function PlaceholderPage({ name }: { name: keyof typeof TITLES }) {
  const meta = TITLES[name] ?? {
    title: name,
    description: "Coming in the next phase.",
    icon: Layers,
  };
  return (
    <PageContainer>
      <PageHeader
        title={meta.title}
        description={meta.description}
        icon={meta.icon}
        crumbs={[{ label: "Home", to: "/" }, { label: meta.title }]}
      />
      <EmptyState
        title={`No ${meta.title.toLowerCase()} yet`}
        description={meta.description}
        icon={meta.icon}
      />
    </PageContainer>
  );
}
