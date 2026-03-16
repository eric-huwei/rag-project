import { useCallback, useMemo, useState } from 'react'
import { ApiError } from '../lib/apiClient'
import { useToast } from '../components/status/toast'

export type RequestState<T> = {
  loading: boolean
  data?: T
  error?: unknown
}

export function useRequest<TArgs extends any[], TData>(
  fn: (...args: TArgs) => Promise<TData>,
  opts?: {
    successTitle?: string
    errorTitle?: string
    showSuccessToast?: boolean
    showErrorToast?: boolean
  },
) {
  const toast = useToast()
  const [state, setState] = useState<RequestState<TData>>({ loading: false })

  const run = useCallback(
    async (...args: TArgs) => {
      setState((s) => ({ ...s, loading: true, error: undefined }))
      try {
        const data = await fn(...args)
        setState({ loading: false, data })
        if (opts?.showSuccessToast) {
          toast.push({ kind: 'success', title: opts.successTitle || '操作成功' })
        }
        return data
      } catch (err) {
        setState((s) => ({ ...s, loading: false, error: err }))
        if (opts?.showErrorToast ?? true) {
          const message =
            err instanceof ApiError
              ? `(${err.status}) ${err.message}`
              : err instanceof Error
                ? err.message
                : '未知错误'
          toast.push({ kind: 'error', title: opts?.errorTitle || '请求失败', message })
        }
        throw err
      }
    },
    [fn, opts?.errorTitle, opts?.showErrorToast, opts?.showSuccessToast, opts?.successTitle, toast],
  )

  const api = useMemo(() => ({ ...state, run }), [state, run])
  return api
}

