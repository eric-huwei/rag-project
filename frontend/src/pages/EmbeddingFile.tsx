import { useEffect, useMemo, useState } from 'react'
import { CyberModulePage } from '../components/layout/CyberModulePage'
import { RequestStatus } from '../components/status/RequestStatus'
import { useToast } from '../components/status/toast'
import { useRequest } from '../hooks/useRequest'
import { apiFetch } from '../lib/apiClient'

const STORAGE_KEY = 'rag.embeddingModel'

type EmbeddingOption = {
  id: string
  label: string
  note?: string
}

type UploadItem = {
  run_id: string
  created_at?: string | null
  filename?: string | null
  content_type?: string | null
  raw_path?: string | null
  size_bytes?: number | null
}

type UploadListResponse = {
  items: UploadItem[]
}

type UploadDetailResponse = {
  run_id: string
  load?: unknown
  files: Array<{ name: string; path: string; size_bytes: number }>
}

const DEFAULT_OPTIONS: EmbeddingOption[] = [
  { id: 'bge-m3', label: 'bge-m3', note: '通用多语种，效果与速度较平衡' },
  { id: 'bge-large-zh-v1.5', label: 'bge-large-zh-v1.5', note: '中文场景常用' },
  { id: 'text-embedding-3-small', label: 'text-embedding-3-small', note: 'OpenAI 系列示例' },
  { id: 'all-MiniLM-L6-v2', label: 'all-MiniLM-L6-v2', note: '轻量本地示例' },
]

function loadSaved() {
  const v = localStorage.getItem(STORAGE_KEY)?.trim()
  return v && v.length > 0 ? v : DEFAULT_OPTIONS[0]!.id
}

export function EmbeddingFilePage() {
  const toast = useToast()
  const [selectedEmbedding, setSelectedEmbedding] = useState<string>(() => loadSaved())
  const [custom, setCustom] = useState<string>('')
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string>('')
  const [detail, setDetail] = useState<UploadDetailResponse | null>(null)

  const options = useMemo(() => {
    const customOpt =
      custom.trim().length > 0
        ? [{ id: custom.trim(), label: custom.trim(), note: '自定义' } satisfies EmbeddingOption]
        : []
    const merged = [...customOpt, ...DEFAULT_OPTIONS]
    const uniq = new Map<string, EmbeddingOption>()
    merged.forEach((o) => uniq.set(o.id, o))
    return Array.from(uniq.values())
  }, [custom])

  const current = useMemo(
    () => options.find((o) => o.id === selectedEmbedding),
    [options, selectedEmbedding],
  )

  const loadUploads = useRequest(async () => apiFetch<UploadListResponse>('/api/load/uploads'), {
    errorTitle: '获取文档列表失败',
    showSuccessToast: false,
  })

  const loadDetail = useRequest(
    async (runId: string) => apiFetch<UploadDetailResponse>(`/api/load/uploads/${runId}`),
    { errorTitle: '获取文档详情失败', showSuccessToast: false },
  )

  const deleteDoc = useRequest(
    async (runId: string) =>
      apiFetch<{ ok: boolean; run_id: string }>(`/api/load/uploads/${runId}`, { method: 'DELETE' }),
    { errorTitle: '删除失败', showSuccessToast: true, successTitle: '已删除' },
  )

  useEffect(() => {
    void loadUploads
      .run()
      .then((res) => {
        setUploads(res.items || [])
        if (!selectedRunId && res.items?.length) setSelectedRunId(res.items[0]!.run_id)
      })
      .catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectedUpload = useMemo(
    () => uploads.find((u) => u.run_id === selectedRunId) || null,
    [uploads, selectedRunId],
  )

  return (
    <CyberModulePage
      title="Embedding File"
      subtitle="选择已上传文档并执行查看、删除，同时管理当前使用的 Embedding。"
      left={
        <div className="space-y-3">
          <div className="text-sm font-semibold text-cyan-200">控制面板</div>

          <div className="space-y-2 rounded-lg border border-cyan-400/25 bg-[#081324] p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-cyan-100">文档选择</div>
              <button
                className="rounded-md border border-cyan-400/30 bg-[#07111f] px-2 py-1 text-xs font-medium text-cyan-100 hover:border-cyan-300/60 hover:bg-cyan-400/10 disabled:opacity-60"
                disabled={loadUploads.loading}
                onClick={() => {
                  setDetail(null)
                  void loadUploads.run().then((res) => setUploads(res.items || [])).catch(() => undefined)
                }}
              >
                {loadUploads.loading ? '刷新中...' : '刷新列表'}
              </button>
            </div>

            <label className="block text-sm text-[#a8b7d1]">
              选择文档
              <select
                className="mt-1.5 w-full rounded-lg border border-[#2f476f] bg-[#050a13] px-3 py-2.5 text-sm text-[#e8eeff] outline-none focus:border-cyan-300/65 focus:ring-2 focus:ring-cyan-300/25"
                value={selectedRunId}
                onChange={(e) => {
                  setSelectedRunId(e.target.value)
                  setDetail(null)
                }}
              >
                <option value="" disabled>
                  {uploads.length ? '请选择...' : '暂无文档，请先在“数据导入”上传'}
                </option>
                {uploads.map((u) => (
                  <option key={u.run_id} value={u.run_id}>
                    {(u.filename || '未命名') + ` (${u.run_id})`}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex flex-wrap gap-2">
              <button
                className="inline-flex items-center justify-center rounded-lg border border-cyan-300/55 bg-gradient-to-r from-cyan-700 to-cyan-400 px-3 py-2 text-sm font-semibold text-[#06131f] shadow-[0_0_24px_rgba(34,211,238,0.3)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
                disabled={!selectedRunId || loadDetail.loading}
                onClick={() => {
                  if (!selectedRunId) return
                  void loadDetail.run(selectedRunId).then((d) => setDetail(d)).catch(() => undefined)
                }}
              >
                {loadDetail.loading ? '加载中...' : '查看详情'}
              </button>
              <button
                className="inline-flex items-center justify-center rounded-lg border border-rose-300/50 bg-rose-500/15 px-3 py-2 text-sm font-medium text-rose-100 transition hover:bg-rose-500/25 disabled:opacity-60"
                disabled={!selectedRunId || deleteDoc.loading}
                onClick={() => {
                  if (!selectedRunId) return
                  void deleteDoc
                    .run(selectedRunId)
                    .then(() => loadUploads.run())
                    .then((res) => {
                      setUploads(res.items || [])
                      setDetail(null)
                      setSelectedRunId(res.items?.[0]?.run_id || '')
                    })
                    .catch(() => undefined)
                }}
              >
                {deleteDoc.loading ? '删除中...' : '删除文档'}
              </button>
            </div>

            <RequestStatus
              loading={loadUploads.loading || loadDetail.loading || deleteDoc.loading}
              error={loadUploads.error || loadDetail.error || deleteDoc.error}
            />
          </div>

          <label className="block text-sm text-[#a8b7d1]">
            可选 Embedding
            <select
              className="mt-1.5 w-full rounded-lg border border-[#2f476f] bg-[#050a13] px-3 py-2.5 text-sm text-[#e8eeff] outline-none focus:border-cyan-300/65 focus:ring-2 focus:ring-cyan-300/25"
              value={selectedEmbedding}
              onChange={(e) => setSelectedEmbedding(e.target.value)}
            >
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm text-[#a8b7d1]">
            自定义 Embedding（可选）
            <input
              className="mt-1.5 w-full rounded-lg border border-[#2f476f] bg-[#050a13] px-3 py-2.5 text-sm text-[#e8eeff] outline-none transition placeholder:text-[#617392] focus:border-cyan-300/65 focus:ring-2 focus:ring-cyan-300/25"
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              placeholder="例如 my-embedding-model-v1"
            />
          </label>

          <button
            className="inline-flex items-center justify-center rounded-lg border border-cyan-300/55 bg-gradient-to-r from-cyan-700 to-cyan-400 px-4 py-2 text-sm font-semibold text-[#06131f] shadow-[0_0_24px_rgba(34,211,238,0.3)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
            disabled={!selectedEmbedding.trim()}
            onClick={() => {
              localStorage.setItem(STORAGE_KEY, selectedEmbedding.trim())
              toast.push({ kind: 'success', title: '已保存 Embedding', message: selectedEmbedding.trim() })
            }}
          >
            保存
          </button>

          <button
            className="inline-flex items-center justify-center rounded-lg border border-cyan-400/35 bg-[#081324] px-3 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/65 hover:bg-cyan-400/10"
            onClick={() => {
              localStorage.removeItem(STORAGE_KEY)
              const v = loadSaved()
              setSelectedEmbedding(v)
              toast.push({ kind: 'info', title: '已重置', message: v })
            }}
          >
            重置为默认
          </button>
        </div>
      }
      right={
        <div className="space-y-3">
          <div className="text-sm font-semibold text-cyan-200">内容显示</div>
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="font-medium text-cyan-100">当前 Embedding</div>
              <div className="mt-2 font-mono text-xs">{selectedEmbedding}</div>
              {current?.note ? <div className="mt-2 text-xs text-[#9eb2d3]">说明：{current.note}</div> : null}
            </div>

            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="font-medium text-cyan-100">当前文档</div>
              {!selectedUpload ? (
                <div className="mt-2 text-sm text-[#96a9c8]">未选择或暂无文档。</div>
              ) : (
                <div className="mt-2 space-y-1 text-xs">
                  <div>
                    <span className="text-[#8fa4c3]">run_id：</span>
                    <span className="font-mono">{selectedUpload.run_id}</span>
                  </div>
                  <div>
                    <span className="text-[#8fa4c3]">filename：</span>
                    <span className="font-mono">{selectedUpload.filename || '（未知）'}</span>
                  </div>
                  <div>
                    <span className="text-[#8fa4c3]">size：</span>
                    <span className="font-mono">{selectedUpload.size_bytes ?? '（未知）'}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-cyan-400/25 bg-[#07111f] p-3 text-xs text-[#c9d6ef]">
            <div className="font-semibold text-cyan-200">文档详情</div>
            {!detail ? (
              <div className="mt-2 text-sm text-[#96a9c8]">点击左侧“查看详情”加载。</div>
            ) : (
              <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words">
                {JSON.stringify(detail, null, 2)}
              </pre>
            )}
          </div>

          <div className="rounded-lg border border-cyan-400/25 bg-[#07111f] p-3 text-xs text-[#c9d6ef]">
            <div className="font-semibold text-cyan-200">使用方式（约定）</div>
            <div className="mt-2">
              前端将值保存为 <span className="font-mono">{STORAGE_KEY}</span>，后续你可以在发起“导入/检索”请求时把它作为参数带给后端。
            </div>
          </div>
        </div>
      }
    />
  )
}
