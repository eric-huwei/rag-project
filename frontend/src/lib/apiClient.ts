export class ApiError extends Error {
  status: number
  payload?: unknown

  constructor(message: string, status: number, payload?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

const BASE_URL_STORAGE_KEY = 'rag.apiBaseUrl'

export function getApiBaseUrl() {
  const v = localStorage.getItem(BASE_URL_STORAGE_KEY)?.trim()
  return v && v.length > 0 ? v.replace(/\/+$/, '') : 'http://localhost:8000'
}

export function setApiBaseUrl(url: string) {
  localStorage.setItem(BASE_URL_STORAGE_KEY, url.trim())
}

async function readJsonSafely(res: Response) {
  const text = await res.text()
  if (!text) return undefined
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { baseUrl?: string },
): Promise<T> {
  const baseUrl = init?.baseUrl ? init.baseUrl.replace(/\/+$/, '') : getApiBaseUrl()
  const url = `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`

  const isFormData =
    typeof FormData !== 'undefined' && init?.body && init.body instanceof FormData

  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: 'application/json',
      // Let the browser set multipart boundaries for FormData.
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  })

  if (!res.ok) {
    const payload = await readJsonSafely(res)
    const msg =
      typeof payload === 'string'
        ? payload
        : (payload as any)?.detail || (payload as any)?.message || res.statusText
    throw new ApiError(msg || '请求失败', res.status, payload)
  }

  if (res.status === 204) return undefined as T
  return (await readJsonSafely(res)) as T
}
