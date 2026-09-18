import { create } from "zustand";

import { toApiError } from "@/api/client";
import { materialsApi } from "@/api/materials";
import type {
  DocumentChunk,
  DocumentImage,
  Material,
  MaterialDetail,
  MaterialStatus,
} from "@/types";
import type { LoadStatus } from "./useSpacesStore";

export const TERMINAL_MATERIAL_STATUSES: MaterialStatus[] = ["READY", "FAILED"];

interface MaterialsState {
  items: Material[];
  total: number;
  projectId: string | null;
  status: LoadStatus;
  error: string | null;
  current: MaterialDetail | null;
  chunks: DocumentChunk[];
  chunksTotal: number;
  images: DocumentImage[];
  imagesState: LoadStatus;
  imagesError: string | null;
  chunksPage: number;
  uploadState: {
    pending: boolean;
    progress: number;
    error: string | null;
    fileName: string | null;
  };
  _fetchSeq: number;
  fetch: (projectId: string) => Promise<void>;
  refreshOne: (projectId: string, materialId: string) => Promise<MaterialDetail | null>;
  upload: (projectId: string, file: File, title: string) => Promise<Material>;
  fetchChunks: (projectId: string, materialId: string, page?: number) => Promise<void>;
  fetchImages: (projectId: string, materialId: string) => Promise<void>;
  reprocess: (projectId: string, materialId: string) => Promise<void>;
  archive: (projectId: string, materialId: string) => Promise<void>;
  resetUpload: () => void;
  reset: () => void;
}

const initial = {
  items: [] as Material[],
  total: 0,
  projectId: null as string | null,
  status: "idle" as LoadStatus,
  error: null as string | null,
  current: null as MaterialDetail | null,
  chunks: [] as DocumentChunk[],
  chunksTotal: 0,
  images: [] as DocumentImage[],
  imagesState: "idle" as LoadStatus,
  imagesError: null as string | null,
  chunksPage: 1,
  uploadState: {
    pending: false,
    progress: 0,
    error: null as string | null,
    fileName: null as string | null,
  },
  /** Internal list-generation counter: stale list responses (mount fetch
  racing an upload prepend or a navigation) are discarded, never applied. */
  _fetchSeq: 0,
};

export const useMaterialsStore = create<MaterialsState>((set, get) => ({
  ...initial,

  fetch: async (projectId) => {
    const seq = get()._fetchSeq + 1;
    set({ status: "loading", error: null, projectId, current: null, _fetchSeq: seq });
    try {
      const res = await materialsApi.list(projectId);
      // A newer generation (upload prepend, navigation, newer fetch) wins;
      // applying this stale snapshot would wipe just-uploaded rows.
      if (get()._fetchSeq !== seq) return;
      set({ items: res.items, total: res.total, status: "ready" });
    } catch (e) {
      if (get()._fetchSeq !== seq) return;
      set({ status: "error", error: toApiError(e).message });
    }
  },

  refreshOne: async (projectId, materialId) => {
    try {
      const detail = await materialsApi.get(projectId, materialId);
      set((s) => ({
        current: detail,
        items: s.items.some((i) => i.id === materialId)
          ? s.items.map((i) => (i.id === materialId ? { ...i, ...detail } : i))
          : [...s.items, detail],
        total: s.items.some((i) => i.id === materialId) ? s.total : s.total + 1,
      }));
      return detail;
    } catch (e) {
      set({ error: toApiError(e).message });
      return null;
    }
  },

  upload: async (projectId, file, title) => {
    set({ uploadState: { pending: true, progress: 0, error: null, fileName: file.name } });
    try {
      const material = await materialsApi.upload(projectId, file, title, (progress) =>
        set((s) => ({ uploadState: { ...s.uploadState, progress } })),
      );
      // Prepend locally; polling takes over status tracking from the server.
      // Bumping the generation retires any in-flight list fetch whose stale
      // snapshot would otherwise wipe this row on arrival.
      set((s) => ({
        items: [material, ...s.items],
        total: s.total + 1,
        uploadState: { pending: false, progress: 100, error: null, fileName: file.name },
        _fetchSeq: s._fetchSeq + 1,
      }));
      return material;
    } catch (e) {
      const message = toApiError(e).message;
      set((s) => ({ uploadState: { ...s.uploadState, pending: false, error: message } }));
      throw e;
    }
  },

  fetchChunks: async (projectId, materialId, page = 1) => {
    const res = await materialsApi.chunks(projectId, materialId, { page, pageSize: 10 });
    set({ chunks: res.items, chunksTotal: res.total, chunksPage: page });
  },

  fetchImages: async (projectId, materialId) => {
    set({ imagesState: "loading", imagesError: null });
    try {
      const images = await materialsApi.images(projectId, materialId);
      set({ images, imagesState: "ready" });
    } catch (e) {
      set({ images: [], imagesState: "error", imagesError: toApiError(e).message });
    }
  },

  reprocess: async (projectId, materialId) => {
    const material = await materialsApi.reprocess(projectId, materialId);
    set((s) => ({
      items: s.items.map((i) => (i.id === materialId ? { ...i, ...material } : i)),
      current:
        s.current?.id === materialId ? { ...s.current, ...material, document: null } : s.current,
    }));
  },

  archive: async (projectId, materialId) => {
    await materialsApi.archive(projectId, materialId);
    set((s) => ({
      items: s.items.filter((i) => i.id !== materialId),
      total: Math.max(0, s.total - 1),
      current: s.current?.id === materialId ? null : s.current,
    }));
  },

  resetUpload: () =>
    set({ uploadState: { pending: false, progress: 0, error: null, fileName: null } }),

  reset: () => set(initial),
}));
