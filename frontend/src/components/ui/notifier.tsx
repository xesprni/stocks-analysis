import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { CheckCircle2, CircleAlert, Info, X, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

type NoticeVariant = "info" | "success" | "warning" | "error";

type NoticeInput = {
  title: string;
  description?: string;
  variant?: NoticeVariant;
  durationMs?: number;
  dedupeKey?: string;
};

type NoticeItem = Required<Pick<NoticeInput, "title" | "variant" | "durationMs">> &
  Omit<NoticeInput, "title" | "variant" | "durationMs"> & {
    id: number;
  };

type NotifierValue = {
  notify: (input: NoticeInput) => void;
  info: (title: string, description?: string, options?: Omit<NoticeInput, "title" | "description" | "variant">) => void;
  success: (title: string, description?: string, options?: Omit<NoticeInput, "title" | "description" | "variant">) => void;
  warning: (title: string, description?: string, options?: Omit<NoticeInput, "title" | "description" | "variant">) => void;
  error: (title: string, description?: string, options?: Omit<NoticeInput, "title" | "description" | "variant">) => void;
};

const NotifierContext = createContext<NotifierValue | null>(null);

const DEFAULT_DURATION_MS = 3500;
const DEDUPE_WINDOW_MS = 2000;

const variantStyle: Record<NoticeVariant, string> = {
  info: "border-border bg-card text-foreground",
  success: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-200",
  warning: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200",
  error: "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-200",
};

const VariantIcon: Record<NoticeVariant, typeof Info> = {
  info: Info,
  success: CheckCircle2,
  warning: CircleAlert,
  error: XCircle,
};

export function NotifierProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<NoticeItem[]>([]);
  const idRef = useRef(1);
  const dedupeRef = useRef<Record<string, number>>({});
  const timerRef = useRef<Record<number, number>>({});

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
    const timer = timerRef.current[id];
    if (timer) {
      window.clearTimeout(timer);
      delete timerRef.current[id];
    }
  }, []);

  const notify = useCallback(
    (input: NoticeInput) => {
      const now = Date.now();
      if (input.dedupeKey) {
        const existing = dedupeRef.current[input.dedupeKey] ?? 0;
        if (existing > now) {
          return;
        }
        dedupeRef.current[input.dedupeKey] = now + DEDUPE_WINDOW_MS;
      }

      const id = idRef.current++;
      const item: NoticeItem = {
        id,
        title: input.title,
        description: input.description,
        variant: input.variant ?? "info",
        durationMs: input.durationMs ?? DEFAULT_DURATION_MS,
        dedupeKey: input.dedupeKey,
      };
      setItems((current) => [item, ...current].slice(0, 5));

      timerRef.current[id] = window.setTimeout(() => {
        dismiss(id);
      }, item.durationMs);
    },
    [dismiss]
  );

  const value = useMemo<NotifierValue>(() => {
    const withVariant =
      (variant: NoticeVariant) =>
      (title: string, description?: string, options?: Omit<NoticeInput, "title" | "description" | "variant">) => {
        notify({
          title,
          description,
          variant,
          durationMs: options?.durationMs,
          dedupeKey: options?.dedupeKey,
        });
      };

    return {
      notify,
      info: withVariant("info"),
      success: withVariant("success"),
      warning: withVariant("warning"),
      error: withVariant("error"),
    };
  }, [notify]);

  return (
    <NotifierContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-[90] flex w-[min(92vw,360px)] flex-col gap-2">
        {items.map((item) => {
          const Icon = VariantIcon[item.variant];
          return (
            <div
              key={item.id}
              className={cn(
                "pointer-events-auto rounded-lg border px-3 py-3 shadow-[0_12px_28px_rgba(0,0,0,0.15)]",
                "animate-in fade-in-0 slide-in-from-top-2 duration-200",
                variantStyle[item.variant]
              )}
              role="status"
            >
              <div className="flex items-start gap-2">
                <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold">{item.title}</div>
                  {item.description ? <div className="mt-1 text-xs opacity-90">{item.description}</div> : null}
                </div>
                <button
                  type="button"
                  className="rounded p-0.5 opacity-70 transition hover:bg-black/5 hover:opacity-100"
                  onClick={() => dismiss(item.id)}
                  aria-label="close"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </NotifierContext.Provider>
  );
}

export function useNotifier(): NotifierValue {
  const value = useContext(NotifierContext);
  if (!value) {
    throw new Error("useNotifier must be used inside NotifierProvider");
  }
  return value;
}
