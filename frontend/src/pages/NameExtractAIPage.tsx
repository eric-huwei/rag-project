import { useMemo, useState } from 'react'
import { ApiError, apiFetch } from '../lib/apiClient'
import { CyberModulePage } from '../components/layout/CyberModulePage'
import { useToast } from '../components/status/toast'
import { useRequest } from '../hooks/useRequest'
import {
  extractNamesFromConversation,
  formatNameSource,
  type NameExtractionResult,
} from '../lib/nameExtractor'

const SAMPLE_CONVERSATION = `张敏：你好，我是张敏，今天跟你确认面试时间。
李雷：收到，我叫李雷，下午三点可以参加。
张敏：好的，我再拉上韩梅梅老师一起进群。
Alice Chen: Hi, this is Alice Chen from HR.
Bob Li: Thanks Alice, I am Bob Li and I will join the call too.
请把补充资料发给韩梅梅老师和 Alice Chen。`

const AI_NAME_PROMPT = `请从下面的对话文本中提取人物姓名。

要求：
1. 只提取真实姓名，不要提取职位、部门、组织、泛称或代词。
2. 去掉姓名后的称谓，例如“老师、经理、总、女士、先生”等。
3. 对重复姓名去重，但保留 1 到 3 条证据片段。
4. 如果无法确定是姓名，不要强行输出。
5. 如果没有识别到姓名，返回：{"names":[]}
6. 只返回合法 JSON，不要输出任何解释。

返回格式：
{
  "names": [
    {
      "name": "张敏",
      "confidence": "high",
      "reason": "说话人标签和自我介绍均命中",
      "evidence": ["张敏：你好，我是张敏，今天跟你确认面试时间。"]
    }
  ]
}`

type AIChatResponse = {
  callId: string
  answer: string
}

type AINameItem = {
  name?: string
  confidence?: string
  reason?: string
  evidence?: string[]
}

type AINamePayload = {
  names?: AINameItem[]
}

function confidenceClass(confidence: '高' | '中' | '低') {
  if (confidence === '高') return 'border-emerald-400/45 bg-emerald-500/15 text-emerald-100'
  if (confidence === '中') return 'border-amber-400/45 bg-amber-500/15 text-amber-100'
  return 'border-slate-400/35 bg-slate-500/15 text-slate-100'
}

function buildAINamePrompt(conversation: string) {
  return `${AI_NAME_PROMPT}

对话文本：
${conversation}

请只返回 JSON。`
}

function createCallId() {
  return `name_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`
}

function cleanJsonText(text: string) {
  const trimmed = text.trim()
  if (!trimmed) return ''

  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fenced?.[1]) return fenced[1].trim()
  return trimmed
}

function parseAINamePayload(answer: string): AINamePayload | null {
  const cleaned = cleanJsonText(answer)
  if (!cleaned) return null

  try {
    const parsed = JSON.parse(cleaned) as AINamePayload
    if (!parsed || !Array.isArray(parsed.names)) return null
    return parsed
  } catch {
    return null
  }
}

function normalizeAIConfidence(confidence?: string) {
  if (!confidence) return '未知'
  const value = confidence.trim().toLowerCase()
  if (value === 'high') return '高'
  if (value === 'medium') return '中'
  if (value === 'low') return '低'
  return confidence
}

export function NameExtractAIPage() {
  const toast = useToast()
  const [conversation, setConversation] = useState('')
  const [ruleResult, setRuleResult] = useState<NameExtractionResult | null>(null)
  const [aiRawAnswer, setAiRawAnswer] = useState('')
  const [aiCallId, setAiCallId] = useState('')

  const aiRecognition = useRequest(
    async (payload: { callId: string; content: string }) =>
      apiFetch<AIChatResponse>('/api/ai/chat', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    { errorTitle: 'AI 识别失败', showSuccessToast: false },
  )

  const canAnalyze = conversation.trim().length > 0
  const parsedAI = useMemo(() => parseAINamePayload(aiRawAnswer), [aiRawAnswer])
  const aiNames = parsedAI?.names?.filter((item) => item?.name?.trim()) || []

  const handleRuleAnalyze = () => {
    if (!canAnalyze) {
      toast.push({ kind: 'warning', title: '请输入对话文本', message: '粘贴聊天记录后再开始分析。' })
      return
    }
    setRuleResult(extractNamesFromConversation(conversation))
  }

  const handleAIRecognize = () => {
    if (!canAnalyze) {
      toast.push({ kind: 'warning', title: '请输入对话文本', message: '需要先提供对话内容。' })
      return
    }

    const callId = createCallId()
    setAiCallId(callId)

    void aiRecognition
      .run({
        callId,
        content: buildAINamePrompt(conversation),
      })
      .then((res) => {
        setAiRawAnswer(res.answer || '')
        const parsed = parseAINamePayload(res.answer || '')
        if (parsed?.names?.length) {
          toast.push({
            kind: 'success',
            title: 'AI 姓名识别完成',
            message: `共识别 ${parsed.names.length} 个候选姓名`,
          })
        } else {
          toast.push({
            kind: 'info',
            title: 'AI 已返回结果',
            message: '返回内容未解析为标准 names JSON，已保留原始回答。',
          })
        }
      })
      .catch(() => undefined)
  }

  const handleFillSample = () => {
    setConversation(SAMPLE_CONVERSATION)
    setRuleResult(extractNamesFromConversation(SAMPLE_CONVERSATION))
    setAiRawAnswer('')
    setAiCallId('')
  }

  const handleClear = () => {
    setConversation('')
    setRuleResult(null)
    setAiRawAnswer('')
    setAiCallId('')
  }

  const handleCopyRuleNames = async () => {
    const names = ruleResult?.items.map((item) => item.name).join('\n') || ''
    if (!names) {
      toast.push({ kind: 'warning', title: '没有可复制的姓名', message: '请先执行一次规则分析。' })
      return
    }

    try {
      await navigator.clipboard.writeText(names)
      toast.push({
        kind: 'success',
        title: '已复制规则结果',
        message: `${ruleResult?.items.length || 0} 个候选姓名`,
      })
    } catch {
      toast.push({ kind: 'error', title: '复制失败', message: '当前环境不支持剪贴板写入。' })
    }
  }

  return (
    <CyberModulePage
      title="对话姓名提取"
      subtitle="支持本地规则提取，也支持调用后端 AI 接口做姓名识别。"
      left={
        <div className="space-y-4">
          <div>
            <div className="text-sm font-semibold text-cyan-200">输入对话文本</div>
            <p className="mt-1 text-xs leading-5 text-[#8ea4c6]">
              支持中文姓名、英文姓名、说话人标签、自我介绍、联系/转接等常见表达。
            </p>
          </div>

          <label className="block text-sm text-[#a8b7d1]">
            Conversation
            <textarea
              className="mt-1.5 min-h-[320px] w-full resize-y rounded-lg border border-[#2f476f] bg-[#050a13] px-3 py-2.5 text-sm text-[#e8eeff] outline-none transition placeholder:text-[#617392] focus:border-cyan-300/65 focus:ring-2 focus:ring-cyan-300/25"
              value={conversation}
              onChange={(e) => setConversation(e.target.value)}
              placeholder={`例如：\n张三：你好，我是张三。\n李四：请帮我联系王敏老师。`}
            />
          </label>

          <div className="rounded-lg border border-cyan-400/25 bg-[#081324] px-3 py-2 text-xs text-[#9eb2d3]">
            当前输入 {conversation.trim().length} 字符
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              className="inline-flex items-center justify-center rounded-lg border border-cyan-300/55 bg-gradient-to-r from-cyan-700 to-cyan-400 px-4 py-2 text-sm font-semibold text-[#06131f] shadow-[0_0_24px_rgba(34,211,238,0.3)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
              disabled={!canAnalyze}
              onClick={handleRuleAnalyze}
            >
              规则分析
            </button>

            <button
              className="inline-flex items-center justify-center rounded-lg border border-cyan-300/55 bg-gradient-to-r from-sky-700 to-blue-400 px-4 py-2 text-sm font-semibold text-[#06131f] shadow-[0_0_24px_rgba(59,130,246,0.28)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
              disabled={!canAnalyze || aiRecognition.loading}
              onClick={handleAIRecognize}
            >
              {aiRecognition.loading ? 'AI 识别中...' : 'AI 识别姓名'}
            </button>

            <button
              className="inline-flex items-center justify-center rounded-lg border border-cyan-400/35 bg-[#081324] px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/65 hover:bg-cyan-400/10"
              onClick={handleFillSample}
            >
              填充示例
            </button>

            <button
              className="inline-flex items-center justify-center rounded-lg border border-cyan-400/35 bg-[#081324] px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/65 hover:bg-cyan-400/10"
              disabled={!ruleResult?.items.length}
              onClick={() => {
                void handleCopyRuleNames()
              }}
            >
              复制规则结果
            </button>

            <button
              className="col-span-2 inline-flex items-center justify-center rounded-lg border border-rose-300/45 bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-100 transition hover:bg-rose-500/20"
              disabled={!conversation && !ruleResult && !aiRawAnswer}
              onClick={handleClear}
            >
              清空
            </button>
          </div>

          <div className="rounded-lg border border-cyan-400/25 bg-[#07111f] p-3 text-xs leading-6 text-[#c9d6ef]">
            <div className="font-semibold text-cyan-200">使用说明</div>
            <div className="mt-2">1. `规则分析` 使用前端本地规则快速抽取候选姓名。</div>
            <div>2. `AI 识别姓名` 会调用后端 `/api/ai/chat`，并自动生成 `callId`。</div>
            <div>3. 后端会把发给 AI 的 `content` 按 `callId` 存入内存对象。</div>
            <div>4. 如果 AI 返回标准 JSON，右侧会解析展示姓名和证据片段。</div>
          </div>
        </div>
      }
      right={
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="text-xs text-[#8fa4c3]">规则姓名数</div>
              <div className="mt-2 text-2xl font-semibold text-cyan-100">
                {ruleResult?.items.length || 0}
              </div>
            </div>
            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="text-xs text-[#8fa4c3]">AI 姓名数</div>
              <div className="mt-2 text-2xl font-semibold text-cyan-100">{aiNames.length}</div>
            </div>
            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="text-xs text-[#8fa4c3]">对话行数</div>
              <div className="mt-2 text-2xl font-semibold text-cyan-100">
                {ruleResult?.totalLines || 0}
              </div>
            </div>
            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="text-xs text-[#8fa4c3]">AI CallId</div>
              <div className="mt-2 truncate font-mono text-xs text-cyan-100">
                {aiCallId || '（未调用）'}
              </div>
            </div>
          </div>

          {ruleResult?.items.length ? (
            <>
              <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
                <div className="font-semibold text-cyan-200">规则抽取结果</div>
                <div className="mt-2 text-xs text-[#8fa4c3]">
                  {ruleResult.items.map((item) => item.name).join('、')}
                </div>
              </div>

              <div className="space-y-3">
                {ruleResult.items.map((item) => (
                  <div
                    key={item.name}
                    className="rounded-xl border border-cyan-400/25 bg-[#07111f] p-4 text-sm text-[#d9e6ff]"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-lg font-semibold text-cyan-100">{item.name}</div>
                        <div className="mt-1 text-xs text-[#8fa4c3]">
                          命中 {item.count} 次 / 评分 {item.score}
                        </div>
                      </div>
                      <div
                        className={`rounded-full border px-3 py-1 text-xs font-semibold ${confidenceClass(item.confidence)}`}
                      >
                        {item.confidence} 置信度
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      {item.sources.map((source) => (
                        <span
                          key={`${item.name}-${source}`}
                          className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2.5 py-1 text-xs text-cyan-100"
                        >
                          {formatNameSource(source)}
                        </span>
                      ))}
                    </div>

                    <div className="mt-3 space-y-2">
                      {item.matches.slice(0, 3).map((match) => (
                        <div
                          key={`${item.name}-${match.line}-${match.source}`}
                          className="rounded-lg border border-[#31476f] bg-[#050c18] px-3 py-2 text-xs text-[#c9d6ef]"
                        >
                          <div className="text-[#8fa4c3]">
                            第 {match.line} 行 · {formatNameSource(match.source)}
                          </div>
                          <div className="mt-1 whitespace-pre-wrap break-words">{match.excerpt}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="rounded-lg border border-dashed border-[#3b4e74] bg-[#0a1222]/70 px-4 py-6 text-sm text-[#96a9c8]">
              左侧点击“规则分析”后，这里会显示本地规则识别结果。
            </div>
          )}

          <div className="rounded-xl border border-sky-400/25 bg-[#07111f] p-4 text-sm text-[#d9e6ff]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-lg font-semibold text-sky-100">AI 识别结果</div>
                <div className="mt-1 text-xs text-[#8fa4c3]">通过后端 AI 接口返回的姓名识别结果</div>
              </div>
              {aiRecognition.error ? (
                <div className="rounded-full border border-rose-400/35 bg-rose-500/10 px-3 py-1 text-xs text-rose-100">
                  {aiRecognition.error instanceof ApiError
                    ? `(${aiRecognition.error.status}) ${aiRecognition.error.message}`
                    : aiRecognition.error instanceof Error
                      ? aiRecognition.error.message
                      : 'AI 请求失败'}
                </div>
              ) : null}
            </div>

            {!aiRawAnswer ? (
              <div className="mt-3 rounded-lg border border-dashed border-[#3b4e74] bg-[#0a1222]/70 px-4 py-6 text-sm text-[#96a9c8]">
                点击“AI 识别姓名”后，这里会展示模型返回结果。
              </div>
            ) : (
              <div className="mt-3 space-y-3">
                {aiNames.length ? (
                  <div className="space-y-3">
                    {aiNames.map((item, index) => (
                      <div
                        key={`${item.name || 'name'}-${index}`}
                        className="rounded-lg border border-sky-400/25 bg-[#050c18] p-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="text-base font-semibold text-sky-100">{item.name}</div>
                          <div className="rounded-full border border-sky-400/30 bg-sky-500/10 px-3 py-1 text-xs text-sky-100">
                            {normalizeAIConfidence(item.confidence)}
                          </div>
                        </div>
                        {item.reason ? (
                          <div className="mt-2 text-xs leading-5 text-[#a8b7d1]">原因：{item.reason}</div>
                        ) : null}
                        {item.evidence?.length ? (
                          <div className="mt-2 space-y-2">
                            {item.evidence.slice(0, 3).map((evidence, evidenceIndex) => (
                              <div
                                key={`${item.name || 'name'}-${evidenceIndex}`}
                                className="rounded-md border border-[#31476f] bg-[#081324] px-3 py-2 text-xs text-[#c9d6ef]"
                              >
                                {evidence}
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}

                <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-xs text-[#c9d6ef]">
                  <div className="font-semibold text-cyan-200">AI 原始回答</div>
                  <pre className="mt-2 overflow-auto whitespace-pre-wrap break-words">{aiRawAnswer}</pre>
                </div>
              </div>
            )}
          </div>
        </div>
      }
    />
  )
}
