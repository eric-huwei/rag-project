import { ApiError } from '../../lib/apiClient'

export function RequestStatus({
  loading,
  error,
}: {
  loading: boolean
  error?: unknown
}) {
  if (!loading && !error) return null

  return (
    <div className="rounded-lg border border-cyan-400/25 bg-[#07111f] px-3 py-2 text-sm text-[#c9d6ef]">
      {loading ? <div className="text-cyan-100">加载中...</div> : null}
      {error ? (
        <div className="mt-1 text-rose-200">
          {error instanceof ApiError
            ? `(${error.status}) ${error.message}`
            : error instanceof Error
              ? error.message
              : '未知错误'}
        </div>
      ) : null}
    </div>
  )
}
