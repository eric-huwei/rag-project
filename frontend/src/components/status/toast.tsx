import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { cn } from '../ui/cn'

export type ToastKind = 'info' | 'success' | 'warning' | 'error'

export type Toast = {
  id: string
  kind: ToastKind
  title: string
  message?: string
}

type ToastContextValue = {
  toasts: Toast[]
  push: (t: Omit<Toast, 'id'>) => void
  dismiss: (id: string) => void
  clear: () => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

function randomId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (t: Omit<Toast, 'id'>) => {
      const id = randomId()
      setToasts((prev) => [{ ...t, id }, ...prev].slice(0, 5))
      window.setTimeout(() => dismiss(id), 4500)
    },
    [dismiss],
  )

  const clear = useCallback(() => setToasts([]), [])

  const value = useMemo(() => ({ toasts, push, dismiss, clear }), [toasts, push, dismiss, clear])

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

export function AppToaster() {
  const { toasts, dismiss } = useToast()

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'pointer-events-auto rounded-lg border bg-white p-3 shadow-lg',
            t.kind === 'error' && 'border-rose-200',
            t.kind === 'success' && 'border-emerald-200',
            t.kind === 'warning' && 'border-amber-200',
            t.kind === 'info' && 'border-slate-200',
          )}
          role="status"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-900">{t.title}</div>
              {t.message ? <div className="mt-0.5 text-xs text-slate-600">{t.message}</div> : null}
            </div>
            <button
              className="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700"
              onClick={() => dismiss(t.id)}
              aria-label="关闭"
            >
              关闭
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
