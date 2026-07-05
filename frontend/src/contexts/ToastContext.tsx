import {
  createContext,
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ToastKind = "success" | "error" | "info" | "warning";
export interface Toast {
  id: number;
  message: string;
  kind: ToastKind;
}

export interface ToastContextValue {
  toasts: Toast[];
  notify: (message: string, kind?: ToastKind, durationMs?: number) => void;
  dismiss: (id: number) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

let seq = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const notify = useCallback(
    (message: string, kind: ToastKind = "info", durationMs = 3500) => {
      const id = ++seq;
      setToasts((t) => [...t, { id, message, kind }]);
      window.setTimeout(() => dismiss(id), durationMs);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ toasts, notify, dismiss }), [toasts, notify, dismiss]);
  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}
