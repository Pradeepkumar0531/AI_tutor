import { create } from "zustand";

interface AppState {
  notifications: string[];
  notify: (message: string) => void;
  clearNotifications: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  notifications: [],
  notify: (message) => set((s) => ({ notifications: [...s.notifications, message] })),
  clearNotifications: () => set({ notifications: [] }),
}));
