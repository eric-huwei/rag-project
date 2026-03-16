import { useState } from 'react'
import { ApiError, apiFetch } from '../lib/apiClient'
import { useRequest } from '../hooks/useRequest'

type EchoResponse = unknown

export function SearchPage() {
  const [query, setQuery] = useState('')

  const runQuery = useRequest(async () => apiFetch<EchoResponse>('/api/health'), {
    errorTitle: '检索失败',
  })

  const isDisabled = runQuery.loading || !query.trim()

  return (
    <div className="relative overflow-hidden rounded-2xl border border-cyan-400/35 bg-[#050d1c]/90 text-slate-100 shadow-[0_20px_60px_rgba(0,0,0,0.55)]">
      <div className="pointer-events-none absolute -left-20 -top-20 h-72 w-72 rounded-full bg-gradient-to-br from-[#1f4ea8]/45 via-[#0e2452]/30 to-transparent blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-16 h-80 w-80 rounded-full bg-gradient-to-tr from-cyan-300/20 via-cyan-500/10 to-transparent blur-3xl" />

      <div className="relative z-10 p-5 md:p-6">
        <header className="mb-6">
          <div className="inline-flex items-center rounded-full border border-cyan-300/40 bg-cyan-400/10 px-3 py-1 text-xs font-semibold tracking-[0.16em] text-cyan-200">
            RETRIEVAL CONSOLE
          </div>
          <h1 className="mt-3 text-2xl font-bold tracking-tight text-[#dfe8ff]">智能检索问答</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#9cadc9]">
            采用深蓝与墨黑基底，叠加青色发光边线，营造轻量化数据大屏科幻感。
          </p>
        </header>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_1fr]">
          <div className="rounded-xl border border-cyan-400/30 bg-gradient-to-b from-[#0c1424]/95 to-[#0a111f]/95 p-4 backdrop-blur-sm">
            <div className="mb-3 text-sm font-semibold text-cyan-200">控制面板</div>

            <label className="block text-sm text-[#a8b7d1]">
              Query
              <input
                className="mt-1.5 w-full rounded-lg border border-[#2f476f] bg-[#050a13] px-3 py-2.5 text-sm text-[#e8eeff] outline-none transition placeholder:text-[#617392] focus:border-cyan-300/65 focus:ring-2 focus:ring-cyan-300/25"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="输入你的检索问题..."
              />
            </label>

            <button
              className="mt-3 inline-flex items-center justify-center rounded-lg border border-cyan-300/55 bg-gradient-to-r from-cyan-700 to-cyan-400 px-4 py-2 text-sm font-semibold text-[#06131f] shadow-[0_0_24px_rgba(34,211,238,0.3)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
              disabled={isDisabled}
              onClick={() => {
                void runQuery.run().catch(() => undefined)
              }}
            >
              {runQuery.loading ? '检索中...' : '开始检索'}
            </button>

            {runQuery.error ? (
              <div className="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                {runQuery.error instanceof ApiError
                  ? `(${runQuery.error.status}) ${runQuery.error.message}`
                  : runQuery.error instanceof Error
                    ? runQuery.error.message
                    : '发生未知错误'}
              </div>
            ) : null}
          </div>

          <div className="min-w-0 rounded-xl border border-cyan-400/30 bg-gradient-to-b from-[#0b1221]/95 to-[#080f1b]/95 p-4 backdrop-blur-sm">
            <div className="mb-3 text-sm font-semibold text-cyan-200">内容显示</div>

            {!runQuery.data ? (
              <div className="rounded-lg border border-dashed border-[#3b4e74] bg-[#0a1222]/70 px-4 py-6 text-sm text-[#96a9c8]">
                暂无结果。请在左侧输入 Query 并点击开始检索。
              </div>
            ) : (
              <div className="rounded-lg border border-[#334a73] bg-[#060d19]/90 p-3 text-xs text-[#c9d6ef]">
                <div className="font-semibold text-cyan-200">响应（占位）</div>
                <pre className="mt-2 overflow-auto whitespace-pre-wrap break-words text-[#c2d1ee]">
                  {JSON.stringify(runQuery.data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
