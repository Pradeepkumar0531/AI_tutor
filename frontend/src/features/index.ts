/** Feature-module contracts (placeholders). Business logic lives in services/hooks, never in components. */

// Auth feature: sign-in/out flows land in Phase 2.
export interface AuthCredentials {
  email: string;
  password: string;
}

// Spaces → Projects → Materials → Tutor → Quiz → Assessment → Mastery → Growth → Recommendation
export interface FeatureStub {
  name: string;
  status: "planned";
}

export const PLANNED_FEATURES: FeatureStub[] = [
  { name: "auth", status: "planned" },
  { name: "spaces", status: "planned" },
  { name: "projects", status: "planned" },
  { name: "materials", status: "planned" },
  { name: "tutor", status: "planned" },
  { name: "quizzes", status: "planned" },
  { name: "mastery", status: "planned" },
  { name: "growth", status: "planned" },
  { name: "recommendations", status: "planned" },
];
