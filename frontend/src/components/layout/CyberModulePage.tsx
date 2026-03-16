import type { ReactNode } from 'react'

export function CyberModulePage({
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
    <div className="relative overflow-hidden rounded-2xl border border-cyan-400/35 bg-[#050d1c]/90 text-slate-100 shadow-[0_20px_60px_rgba(0,0,0,0.55)]">
      <div className="pointer-events-none absolute -left-20 -top-20 h-72 w-72 rounded-full bg-gradient-to-br from-[#1f4ea8]/45 via-[#0e2452]/30 to-transparent blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-16 h-80 w-80 rounded-full bg-gradient-to-tr from-cyan-300/20 via-cyan-500/10 to-transparent blur-3xl" />

      <div className="relative z-10 p-5 md:p-6">
        <header className="mb-6">
          <div className="inline-flex items-center rounded-full border border-cyan-300/40 bg-cyan-400/10 px-3 py-1 text-xs font-semibold tracking-[0.16em] text-cyan-200">
            RETRIEVAL CONSOLE
          </div>
          <h1 className="mt-3 text-2xl font-bold tracking-tight text-[#dfe8ff]">{title}</h1>
          {subtitle ? <p className="mt-2 max-w-2xl text-sm leading-6 text-[#9cadc9]">{subtitle}</p> : null}
        </header>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_1fr]">
          <div className="rounded-xl border border-cyan-400/30 bg-gradient-to-b from-[#0c1424]/95 to-[#0a111f]/95 p-4 backdrop-blur-sm">
            {left}
          </div>
          <div className="min-w-0 rounded-xl border border-cyan-400/30 bg-gradient-to-b from-[#0b1221]/95 to-[#080f1b]/95 p-4 backdrop-blur-sm">
            {right}
          </div>
        </section>
      </div>
    </div>
  )
}
