import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CyberModulePage } from '../components/layout/CyberModulePage'
import { RequestStatus } from '../components/status/RequestStatus'
import { useToast } from '../components/status/toast'
import { useRequest } from '../hooks/useRequest'
import { apiFetch } from '../lib/apiClient'

type UploadResponse = {
  run_id: string
  filepath?: string
  loaded_content?: unknown
  result?: {
    filename?: string
    content_type?: string | null
    json_path?: string
    size_bytes?: number
    total_chunks?: number
    total_pages?: number
    loading_method?: string
    loading_strategy?: string | null
    chunking_strategy?: string | null
    created_at?: string
  }
}

type UploadItem = {
  run_id: string
  created_at?: string | null
  filename?: string | null
  content_type?: string | null
  json_path?: string | null
  size_bytes?: number | null
  total_chunks?: number | null
  total_pages?: number | null
  loading_method?: string | null
  loading_strategy?: string | null
  chunking_strategy?: string | null
}

type UploadListResponse = {
  items: UploadItem[]
}

type UploadDetailResponse = {
  run_id: string
  load?: unknown
  files: Array<{ name: string; path: string; size_bytes: number }>
}

function formatSize(size?: number | null) {
  if (!size || size <= 0) return '未知'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

function formatTime(v?: string | null) {
  if (!v) return '未知'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString()
}

export function IngestPage() {
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [loadingMethod, setLoadingMethod] = useState<'pymupdf' | 'unstructured'>('pymupdf')
  const [activeTab, setActiveTab] = useState<'preview' | 'management'>('preview')
  const [previewUrl, setPreviewUrl] = useState<string>('')
  const [lastUpload, setLastUpload] = useState<UploadResponse | null>(null)
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string>('')
  const [detail, setDetail] = useState<UploadDetailResponse | null>(null)

  useEffect(() => {
    if (!file) {
      setPreviewUrl('')
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const fileHint = useMemo(() => {
    if (!file) return '请选择一个 PDF 文件'
    const mb = (file.size / 1024 / 1024).toFixed(2)
    return `${file.name} (${mb} MB)`
  }, [file])

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
      .then((res) => setUploads(res.items || []))
      .catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const uploadReq = useRequest(
    async () => {
      if (!file) throw new Error('请先选择 PDF 文件')
      const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
      if (!isPdf) throw new Error('只支持上传 PDF 文件')

      const form = new FormData()
      form.append('file', file)
      form.append('loading_method', loadingMethod)

      const res = await apiFetch<UploadResponse>('/api/load/upload', {
        method: 'POST',
        body: form,
      })

      setLastUpload(res)
      setActiveTab('management')
      toast.push({ kind: 'success', title: '上传成功', message: `run_id: ${res.run_id}` })

      try {
        const list = await loadUploads.run()
        setUploads(list.items || [])
      } catch {
        // Upload itself succeeded; list refresh failure should not block response.
      }

      return res
    },
    { errorTitle: '上传失败', showSuccessToast: false },
  )

  return (
    <CyberModulePage
      title="数据导入"
      subtitle="上传 PDF 到后端（/api/load/upload），右侧支持预览并查看返回结果。"
      left={
        <div className="space-y-3">
          <div className="text-sm font-semibold text-cyan-200">Upload PDF</div>

          <label className="block text-sm text-[#a8b7d1]">
            选择文件
            <input
              type="file"
              accept="application/pdf,.pdf"
              className="mt-1.5 block w-full rounded-lg border border-[#2f476f] bg-[#050a13] px-3 py-2.5 text-sm text-[#e8eeff] file:mr-3 file:rounded-md file:border-0 file:bg-cyan-400/20 file:px-2.5 file:py-1.5 file:text-xs file:font-semibold file:text-cyan-100"
              onChange={(e) => {
                const f = e.target.files?.[0] || null
                setFile(f)
                setLastUpload(null)
              }}
            />
            <div className="mt-1.5 text-xs text-[#90a5c5]">{fileHint}</div>
          </label>

          <label className="block text-sm text-[#a8b7d1]">
            Loading Method
            <select
              className="mt-1.5 w-full rounded-lg border border-[#2f476f] bg-[#050a13] px-3 py-2.5 text-sm text-[#e8eeff] outline-none focus:border-cyan-300/65 focus:ring-2 focus:ring-cyan-300/25"
              value={loadingMethod}
              onChange={(e) => setLoadingMethod(e.target.value as 'pymupdf' | 'unstructured')}
            >
              <option value="pymupdf">PyMuPDF</option>
              <option value="unstructured">Unstructured</option>
            </select>
          </label>

          <button
            className="inline-flex w-full items-center justify-center rounded-lg border border-cyan-300/55 bg-gradient-to-r from-cyan-700 to-cyan-400 px-4 py-2 text-sm font-semibold text-[#06131f] shadow-[0_0_24px_rgba(34,211,238,0.3)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
            disabled={!file || uploadReq.loading}
            onClick={() => {
              void uploadReq.run().catch(() => undefined)
            }}
          >
            {uploadReq.loading ? '上传中...' : '上传文件'}
          </button>

          <Link
            className="inline-flex items-center justify-center rounded-lg border border-cyan-400/35 bg-[#081324] px-3 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/65 hover:bg-cyan-400/10"
            to="/embedding-file"
          >
            打开文档管理
          </Link>

          <RequestStatus loading={uploadReq.loading} error={uploadReq.error} />
        </div>
      }
      right={
        <div className="space-y-3">
          <div className="inline-flex rounded-xl border border-cyan-400/30 bg-[#070f1d] p-1">
            <button
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                activeTab === 'preview'
                  ? 'border border-cyan-300/55 bg-cyan-400/15 text-cyan-100'
                  : 'text-[#9fb2d2] hover:text-cyan-100'
              }`}
              onClick={() => setActiveTab('preview')}
            >
              Document Preview
            </button>
            <button
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                activeTab === 'management'
                  ? 'border border-cyan-300/55 bg-cyan-400/15 text-cyan-100'
                  : 'text-[#9fb2d2] hover:text-cyan-100'
              }`}
              onClick={() => setActiveTab('management')}
            >
              Document Management
            </button>
          </div>

          {activeTab === 'preview' ? (
            <>
              <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3">
                {!previewUrl ? (
                  <div className="text-sm text-[#96a9c8]">请选择 PDF 后这里会显示预览。</div>
                ) : (
                  <iframe
                    title="pdf-preview"
                    src={previewUrl}
                    className="h-[520px] w-full rounded-md border border-cyan-400/20"
                  />
                )}
              </div>

              <div className="rounded-lg border border-cyan-400/25 bg-[#07111f] p-3 text-xs text-[#c9d6ef]">
                <div className="font-semibold text-cyan-200">Upload Result</div>
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words">
                  {lastUpload ? JSON.stringify(lastUpload, null, 2) : '（暂无）'}
                </pre>
              </div>
            </>
          ) : (
            <div className="space-y-3">
              <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-sm font-semibold text-cyan-200">Document Management</div>
                  <button
                    className="rounded-md border border-cyan-400/35 bg-[#07111f] px-2 py-1 text-xs text-cyan-100 hover:border-cyan-300/65 hover:bg-cyan-400/10 disabled:opacity-60"
                    disabled={loadUploads.loading}
                    onClick={() => {
                      void loadUploads.run().then((res) => setUploads(res.items || [])).catch(() => undefined)
                    }}
                  >
                    {loadUploads.loading ? '刷新中...' : '刷新列表'}
                  </button>
                </div>

                {!uploads.length ? (
                  <div className="text-sm text-[#96a9c8]">暂无文档，请先上传。</div>
                ) : (
                  <div className="space-y-2">
                    {uploads.map((u) => (
                      <div
                        key={u.run_id}
                        className="rounded-lg border border-cyan-400/20 bg-[#07111f] p-3 text-sm text-[#c9d6ef]"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate font-semibold text-cyan-100">{u.filename || '未命名文档'}</div>
                            <div className="mt-1 text-xs text-[#8fa4c3]">run_id: {u.run_id}</div>
                            <div className="mt-2 grid grid-cols-1 gap-1 text-xs md:grid-cols-2">
                              <div>Pages: {u.total_pages ?? '未知'}</div>
                              <div>Chunks: {u.total_chunks ?? '未知'}</div>
                              <div>Loading Method: {u.loading_method || '未知'}</div>
                              <div>Chunking Method: {u.chunking_strategy || 'by_page'}</div>
                              <div>Size: {formatSize(u.size_bytes)}</div>
                              <div>Created: {formatTime(u.created_at)}</div>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <button
                              className="rounded-md border border-cyan-300/55 bg-cyan-500/20 px-3 py-1.5 text-xs font-semibold text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-60"
                              disabled={loadDetail.loading}
                              onClick={() => {
                                setSelectedRunId(u.run_id)
                                void loadDetail.run(u.run_id).then((d) => setDetail(d)).catch(() => undefined)
                              }}
                            >
                              View
                            </button>
                            <button
                              className="rounded-md border border-rose-300/50 bg-rose-500/15 px-3 py-1.5 text-xs font-semibold text-rose-100 hover:bg-rose-500/25 disabled:opacity-60"
                              disabled={deleteDoc.loading}
                              onClick={() => {
                                void deleteDoc
                                  .run(u.run_id)
                                  .then(() => loadUploads.run())
                                  .then((res) => {
                                    setUploads(res.items || [])
                                    if (selectedRunId === u.run_id) {
                                      setSelectedRunId('')
                                      setDetail(null)
                                    }
                                  })
                                  .catch(() => undefined)
                              }}
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <RequestStatus
                loading={loadUploads.loading || loadDetail.loading || deleteDoc.loading}
                error={loadUploads.error || loadDetail.error || deleteDoc.error}
              />

              <div className="rounded-lg border border-cyan-400/25 bg-[#07111f] p-3 text-xs text-[#c9d6ef]">
                <div className="font-semibold text-cyan-200">Selected Detail</div>
                {!detail ? (
                  <div className="mt-2 text-sm text-[#96a9c8]">点击列表中的 View 查看详情。</div>
                ) : (
                  <>
                    <div className="mt-2 text-xs text-[#8fa4c3]">run_id: {selectedRunId || detail.run_id}</div>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words">
                      {JSON.stringify(detail, null, 2)}
                    </pre>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      }
    />
  )
}
