import * as React from "react";

import { cn } from "@/lib/utils";

interface ToastItem {
  id: number;
  message: string;
}

const ToastContext = React.createContext<{ push: (message: string) => void }>({ push: () => {} });

let nextId = 1;

export function useToast(): { push: (message: string) => void } {
  return React.useContext(ToastContext);
}

export function ToastHost({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);
  const push = React.useCallback((message: string) => {
    const id = nextId++;
    setToasts((t) => [...t, { id, message }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <Toast key={t.id} message={t.message} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function Toast({ message, className }: { message: string; className?: string }) {
  return (
    <div className={cn("rounded-lg border bg-card px-4 py-2 text-sm shadow-md", className)}>
      {message}
    </div>
  );
}
