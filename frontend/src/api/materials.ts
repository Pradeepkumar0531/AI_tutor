import { apiClient } from "./client";
import type {
  DocumentChunk,
  DocumentImage,
  KnowledgeStatus,
  Material,
  MaterialDetail,
  MaterialDocument,
  MaterialStatus,
  Page,
} from "@/types";

interface BackendMaterial {
  id: string;
  project_id: string;
  name: string;
  type: string;
  status: MaterialStatus;
  storage_provider: string;
  original_filename: string | null;
  mime_type: string | null;
  file_size: number | null;
  processing_error: string | null;
  retry_count: number;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  page_count?: number | null;
  chunk_count?: number | null;
  created_at: string;
  updated_at: string;
}

interface BackendDocument {
  id: string;
  material_id: string;
  project_id: string;
  page_count: number | null;
  extraction_method: string | null;
  language: string | null;
  doc_metadata?: Record<string, unknown> | null;
  chunk_count: number;
  image_count: number;
  created_at: string;
  updated_at: string;
}

interface BackendImage {
  id: string;
  document_id: string;
  page_number: number;
  image_index: number;
  width: number;
  height: number;
  mime_type: string;
  file_size: number;
}

interface BackendChunk {
  id: string;
  document_id: string;
  project_id: string;
  chunk_index: number;
  content: string;
  page_start: number | null;
  page_end: number | null;
  section_title: string | null;
  chunk_metadata?: Record<string, unknown> | null;
}

function toMaterial(m: BackendMaterial): Material {
  return {
    id: m.id,
    projectId: m.project_id,
    name: m.name,
    type: m.type,
    status: m.status,
    originalFilename: m.original_filename,
    mimeType: m.mime_type,
    fileSize: m.file_size,
    processingError: m.processing_error,
    retryCount: m.retry_count,
    pageCount: m.page_count ?? null,
    chunkCount: m.chunk_count ?? null,
    createdAt: m.created_at,
    updatedAt: m.updated_at,
  };
}

function toDocument(d: BackendDocument): MaterialDocument {
  return {
    id: d.id,
    materialId: d.material_id,
    projectId: d.project_id,
    pageCount: d.page_count,
    extractionMethod: d.extraction_method,
    language: d.language,
    chunkCount: d.chunk_count,
    imageCount: d.image_count ?? 0,
  };
}

function toImage(i: BackendImage): DocumentImage {
  return {
    id: i.id,
    documentId: i.document_id,
    pageNumber: i.page_number,
    imageIndex: i.image_index,
    width: i.width,
    height: i.height,
    mimeType: i.mime_type,
    fileSize: i.file_size,
  };
}

function toChunk(c: BackendChunk): DocumentChunk {
  return {
    id: c.id,
    documentId: c.document_id,
    projectId: c.project_id,
    chunkIndex: c.chunk_index,
    content: c.content,
    pageStart: c.page_start,
    pageEnd: c.page_end,
  };
}

interface BackendMaterialDetail extends BackendMaterial {
  document: BackendDocument | null;
  image_count: number;
  knowledge?: {
    status: string;
    embedded: number;
    total: number;
    image_count: number;
    images_by_page: Record<string, number>;
  } | null;
}

export const materialsApi = {
  async list(projectId: string, params: { page?: number; pageSize?: number } = {}) {
    const res = await apiClient.get<Page<BackendMaterial>>(
      `/api/v1/projects/${projectId}/materials`,
      { params: { page: params.page ?? 1, page_size: params.pageSize ?? 20 } },
    );
    return { ...res.data, items: res.data.items.map(toMaterial) };
  },

  async upload(
    projectId: string,
    file: File,
    title: string,
    onProgress?: (percent: number) => void,
  ): Promise<Material> {
    const form = new FormData();
    form.append("file", file, file.name);
    if (title.trim()) form.append("title", title.trim());
    const res = await apiClient.post<BackendMaterial>(
      `/api/v1/projects/${projectId}/materials`,
      form,
      {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total) onProgress?.(Math.round((e.loaded / e.total) * 100));
        },
      },
    );
    return toMaterial(res.data);
  },

  async get(projectId: string, materialId: string): Promise<MaterialDetail> {
    const res = await apiClient.get<BackendMaterialDetail>(
      `/api/v1/projects/${projectId}/materials/${materialId}`,
    );
    return {
      ...toMaterial(res.data),
      imageCount: res.data.image_count ?? 0,
      document: res.data.document ? toDocument(res.data.document) : null,
      knowledge: res.data.knowledge
        ? {
            status: res.data.knowledge.status as KnowledgeStatus,
            embedded: res.data.knowledge.embedded,
            total: res.data.knowledge.total,
            imageCount: res.data.knowledge.image_count ?? 0,
            imagesByPage: res.data.knowledge.images_by_page ?? {},
          }
        : null,
    };
  },

  async images(projectId: string, materialId: string): Promise<DocumentImage[]> {
    const res = await apiClient.get<Page<BackendImage>>(
      `/api/v1/projects/${projectId}/materials/${materialId}/images`,
      { params: { page_size: 100 } },
    );
    return res.data.items.map(toImage);
  },

  async imageBlob(projectId: string, materialId: string, imageId: string): Promise<Blob> {
    const res = await apiClient.get(
      `/api/v1/projects/${projectId}/materials/${materialId}/images/${imageId}/content`,
      { responseType: "blob" },
    );
    return res.data as Blob;
  },

  async pdfBlob(projectId: string, materialId: string): Promise<Blob> {
    const res = await apiClient.get(
      `/api/v1/projects/${projectId}/materials/${materialId}/content`,
      { responseType: "blob" },
    );
    return res.data as Blob;
  },

  async chunks(
    projectId: string,
    materialId: string,
    params: { page?: number; pageSize?: number } = {},
  ) {
    const res = await apiClient.get<Page<BackendChunk>>(
      `/api/v1/projects/${projectId}/materials/${materialId}/document/chunks`,
      { params: { page: params.page ?? 1, page_size: params.pageSize ?? 10 } },
    );
    return { ...res.data, items: res.data.items.map(toChunk) };
  },

  async reprocess(projectId: string, materialId: string): Promise<Material> {
    const res = await apiClient.post<BackendMaterial>(
      `/api/v1/projects/${projectId}/materials/${materialId}/reprocess`,
    );
    return toMaterial(res.data);
  },

  async archive(projectId: string, materialId: string): Promise<Material> {
    const res = await apiClient.delete<BackendMaterial>(
      `/api/v1/projects/${projectId}/materials/${materialId}`,
    );
    return toMaterial(res.data);
  },
};
