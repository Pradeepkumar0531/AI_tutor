/** Shared frontend domain types (contracts for future feature modules). */

export interface User {
  id: string;
  email: string;
  displayName: string;
  role: string;
  createdAt?: string;
}

export interface Space {
  id: string;
  name: string;
  description: string | null;
  archivedAt: string | null;
  createdAt: string;
  updatedAt: string;
  projectCount?: number | null;
}

export interface Project {
  id: string;
  spaceId: string;
  name: string;
  description: string | null;
  learningGoal: string | null;
  targetOutcome?: string | null;
  difficulty?: string | null;
  archivedAt: string | null;
  createdAt: string;
  updatedAt: string;
  materialCount?: number | null;
}

export type MaterialStatus = "QUEUED" | "PROCESSING" | "READY" | "FAILED";

export interface Material {
  id: string;
  projectId: string;
  name: string;
  type: string;
  status: MaterialStatus;
  originalFilename: string | null;
  mimeType: string | null;
  fileSize: number | null;
  processingError: string | null;
  retryCount: number;
  pageCount: number | null;
  chunkCount: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface MaterialDocument {
  id: string;
  materialId: string;
  projectId: string;
  pageCount: number | null;
  extractionMethod: string | null;
  language: string | null;
  chunkCount: number;
  imageCount: number;
}

export interface MaterialKnowledge {
  status: KnowledgeStatus;
  embedded: number;
  total: number;
  imageCount: number;
  imagesByPage: Record<string, number>;
}

export interface MaterialDetail extends Material {
  document: MaterialDocument | null;
  imageCount: number;
  knowledge?: MaterialKnowledge | null;
}

export interface DocumentImage {
  id: string;
  documentId: string;
  pageNumber: number;
  imageIndex: number;
  width: number;
  height: number;
  mimeType: string;
  fileSize: number;
}

export interface DocumentChunk {
  id: string;
  documentId: string;
  projectId: string;
  chunkIndex: number;
  content: string;
  pageStart: number | null;
  pageEnd: number | null;
}

export type KnowledgeStatus = "PENDING" | "PROCESSING" | "READY" | "FAILED";

export interface KnowledgeTotals {
  chunks_total: number;
  chunks_embedded: number;
  concepts: number;
  materials_ready: number;
}

export interface Concept {
  id: string;
  projectId: string;
  name: string;
  description: string | null;
  createdAt: string;
  updatedAt: string;
  materials?: { id: string; name: string }[];
  chunkCount?: number;
  pages?: number[];
}

export interface SearchResultItem {
  chunk_id: string;
  document_id: string;
  material_id: string;
  material_name: string;
  text: string;
  page_start: number | null;
  page_end: number | null;
  similarity: number;
}

export interface SearchCitation {
  chunk_id: string;
  document_id: string;
  material_id: string;
  material_name: string;
  page_start: number | null;
  page_end: number | null;
  label: string;
}

export interface KnowledgeSearchResponse {
  query: string;
  results: SearchResultItem[];
  citations: SearchCitation[];
  context: string;
  insufficient_evidence: boolean;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: unknown;
    request_id: string;
  };
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface TutorConversation {
  id: string;
  projectId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export type TutorRole = "USER" | "ASSISTANT";

export interface TutorCitation {
  chunk_id: string;
  document_id: string;
  material_id: string;
  material_name: string;
  page_start: number | null;
  page_end: number | null;
  label: string;
}

export interface TutorMessage {
  id: string;
  conversationId: string;
  role: TutorRole;
  content: string;
  model: string | null;
  createdAt: string;
  citations: TutorCitation[];
  grounded: boolean;
  insufficientEvidence: boolean;
}

export interface TutorSendResponse {
  conversation_id: string;
  message: TutorMessage;
  citations: TutorCitation[];
  grounded: boolean;
  insufficient_evidence: boolean;
}

export type QuizStatus = "DRAFT" | "READY" | "ARCHIVED";
export type QuestionType = "MCQ" | "OPEN_ENDED";
export type AttemptStatus = "IN_PROGRESS" | "COMPLETED" | "ABANDONED";

export interface Quiz {
  id: string;
  projectId: string;
  title: string;
  status: QuizStatus;
  difficulty: string | null;
  questionCount: number;
  createdAt: string;
}

export interface QuizOption {
  id: string;
  text: string;
}

export interface QuizConceptLabel {
  id: string;
  name: string;
}

export interface QuizSource {
  material_name: string;
  page_start: number | null;
  page_end: number | null;
}

export interface QuizQuestion {
  questionId: string;
  type: QuestionType;
  prompt: string;
  options: QuizOption[];
  position: number;
  points: number;
  difficulty: string | null;
  concepts: QuizConceptLabel[];
  sources: QuizSource[];
}

export interface AnswerState {
  submitted: string | null;
  isCorrect: boolean | null;
  score: number | null;
  feedback: string | null;
  correctOptionId: string | null;
  evaluation: Record<string, unknown> | null;
}

export interface AttemptQuestion extends QuizQuestion {
  answer: AnswerState;
}

export interface Attempt {
  id: string;
  quizId: string;
  status: AttemptStatus;
  score: number | null;
  maxScore: number | null;
  startedAt: string;
  completedAt: string | null;
}

export interface ConceptPerformance {
  conceptId: string;
  conceptName: string;
  questionsSeen: number;
  correctCount: number;
  partialCount: number;
  incorrectCount: number;
  normalizedScore: number;
  recent: string[];
}

export interface AssessmentResult {
  assessmentId: string;
  quizAttemptId: string;
  quizId: string;
  totalQuestions: number;
  answeredCount: number;
  correctCount: number;
  partialCount: number;
  incorrectCount: number;
  score: number;
  conceptResults: ConceptPerformance[];
}

export interface AssessmentSummary {
  id: string;
  quizAttemptId: string | null;
  quizId: string | null;
  status: string;
  score: number | null;
  completedAt: string | null;
}
