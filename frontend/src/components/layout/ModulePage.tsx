import type { ReactNode } from 'react'

export function ModulePage({
  title,
  subtitle,
  left,
  right,
}: {
  title: string
  subtitle?: string
  left: ReactNode
  right: ReactNode
}) {
  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
        {subtitle ? <p className="text-sm text-slate-600">{subtitle}</p> : null}
      </header>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_1fr]">
        <div className="rounded-lg border border-slate-200 bg-white p-4">{left}</div>
        <div className="min-w-0 rounded-lg border border-slate-200 bg-white p-4">{right}</div>
      </section>
    </div>
  )
}

