import { useMemo, useState } from 'react'
import { CyberModulePage } from '../components/layout/CyberModulePage'
import {
  getApiBaseUrl,
  getDefaultApiBaseUrl,
  resetApiBaseUrl,
  setApiBaseUrl,
} from '../lib/apiClient'
import { useToast } from '../components/status/toast'

export function SettingsPage() {
  const toast = useToast()
  const [baseUrl, setBaseUrlState] = useState(getApiBaseUrl)

  const normalized = useMemo(() => baseUrl.trim().replace(/\/+$/, ''), [baseUrl])

  return (
    <CyberModulePage
      title="设置"
      subtitle="统一配置 API Base URL 与系统访问参数。"
      left={
        <div className="space-y-3">
          <div className="text-sm font-semibold text-cyan-200">控制面板</div>
          <label className="block text-sm text-[#a8b7d1]">
            后端 Base URL
            <input
              className="mt-1.5 w-full rounded-lg border border-[#2f476f] bg-[#050a13] px-3 py-2.5 text-sm text-[#e8eeff] outline-none transition placeholder:text-[#617392] focus:border-cyan-300/65 focus:ring-2 focus:ring-cyan-300/25"
              value={baseUrl}
              onChange={(e) => setBaseUrlState(e.target.value)}
              placeholder={getDefaultApiBaseUrl() || '请输入后端地址'}
            />
          </label>
          <button
            className="inline-flex items-center justify-center rounded-lg border border-cyan-300/55 bg-gradient-to-r from-cyan-700 to-cyan-400 px-4 py-2 text-sm font-semibold text-[#06131f] shadow-[0_0_24px_rgba(34,211,238,0.3)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
            disabled={!normalized}
            onClick={() => {
              setApiBaseUrl(normalized)
              toast.push({ kind: 'success', title: '已保存', message: normalized })
            }}
          >
            保存
          </button>
          <button
            className="ml-3 inline-flex items-center justify-center rounded-lg border border-[#2f476f] px-4 py-2 text-sm font-semibold text-[#c9d6ef] transition hover:border-cyan-300/65 hover:text-cyan-100"
            onClick={() => {
              resetApiBaseUrl()
              const defaultBaseUrl = getApiBaseUrl()
              setBaseUrlState(defaultBaseUrl)
              toast.push({
                kind: 'success',
                title: '已恢复默认',
                message: defaultBaseUrl || '请先配置默认后端地址。',
              })
            }}
          >
            恢复默认
          </button>
        </div>
      }
      right={
        <div className="space-y-3">
          <div className="text-sm font-semibold text-cyan-200">内容显示</div>
          <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
            <div className="font-medium text-cyan-100">当前生效的 Base URL</div>
            <div className="mt-2 font-mono text-xs">{normalized || '（未设置）'}</div>
            <div className="mt-2 text-xs text-[#9eb2d3]">
              默认地址来自环境配置，保存的自定义地址优先使用；点击「恢复默认」可清除自定义地址。
            </div>
          </div>
        </div>
      }
    />
  )
}
