import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CyberModulePage } from '../components/layout/CyberModulePage'
import { RequestStatus } from '../components/status/RequestStatus'
import { useToast } from '../components/status/toast'
import { useRequest } from '../hooks/useRequest'
import { apiFetch } from '../lib/apiClient'

type UploadResponse = {
  run_id: string
  result?: {
    filename?: string
    content_type?: string | null
    raw_path?: string
    size_bytes?: number
  }
}

export function IngestPage() {
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [loadingMethod, setLoadingMethod] = useState<'pymupdf' | 'unstructured'>('pymupdf')
  const [previewUrl, setPreviewUrl] = useState<string>('')
  const [lastUpload, setLastUpload] = useState<UploadResponse | null>(null)

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
      toast.push({ kind: 'success', title: '上传成功', message: `run_id: ${res.run_id}` })
      return res
    },
    { errorTitle: '上传失败', showSuccessToast: false },
  )

  return (
    <CyberModulePage
      title="数据导入"
      subtitle="上传 PDF 到后端（/api/load/upload），右侧可预览并查看返回结果。"
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
          <div className="text-sm font-semibold text-cyan-200">Document Preview</div>

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
        </div>
      }
    />
  )
}
