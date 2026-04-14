import { useState } from 'react'
import { CyberModulePage } from '../components/layout/CyberModulePage'
import { useToast } from '../components/status/toast'
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

function confidenceClass(confidence: '高' | '中' | '低') {
  if (confidence === '高') return 'border-emerald-400/45 bg-emerald-500/15 text-emerald-100'
  if (confidence === '中') return 'border-amber-400/45 bg-amber-500/15 text-amber-100'
  return 'border-slate-400/35 bg-slate-500/15 text-slate-100'
}

export function NameExtractPage() {
  const toast = useToast()
  const [conversation, setConversation] = useState('')
  const [result, setResult] = useState<NameExtractionResult | null>(null)

  const canAnalyze = conversation.trim().length > 0

  const handleAnalyze = () => {
    if (!canAnalyze) {
      toast.push({ kind: 'warning', title: '请输入对话文本', message: '粘贴聊天记录后再开始分析。' })
      return
    }
    setResult(extractNamesFromConversation(conversation))
  }

  const handleFillSample = () => {
    setConversation(SAMPLE_CONVERSATION)
    setResult(extractNamesFromConversation(SAMPLE_CONVERSATION))
  }

  const handleClear = () => {
    setConversation('')
    setResult(null)
  }

  const handleCopy = async () => {
    const names = result?.items.map((item) => item.name).join('\n') || ''
    if (!names) {
      toast.push({ kind: 'warning', title: '没有可复制的姓名', message: '请先执行一次分析。' })
      return
    }

    try {
      await navigator.clipboard.writeText(names)
      toast.push({ kind: 'success', title: '已复制姓名列表', message: `${result?.items.length || 0} 个候选姓名` })
    } catch {
      toast.push({ kind: 'error', title: '复制失败', message: '当前环境不支持剪贴板写入。' })
    }
  }

  return (
    <CyberModulePage
      title="对话姓名提取"
      subtitle="面向客服、面试、群聊等文本场景，基于规则从对话中抽取候选姓名，并展示命中的上下文。"
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
              placeholder="例如：&#10;张三：你好，我是张三。&#10;李四：请帮我联系王敏老师。"
            />
          </label>

          <div className="rounded-lg border border-cyan-400/25 bg-[#081324] px-3 py-2 text-xs text-[#9eb2d3]">
            当前输入 {conversation.trim().length} 字符
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              className="inline-flex items-center justify-center rounded-lg border border-cyan-300/55 bg-gradient-to-r from-cyan-700 to-cyan-400 px-4 py-2 text-sm font-semibold text-[#06131f] shadow-[0_0_24px_rgba(34,211,238,0.3)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
              disabled={!canAnalyze}
              onClick={handleAnalyze}
            >
              开始分析
            </button>

            <button
              className="inline-flex items-center justify-center rounded-lg border border-cyan-400/35 bg-[#081324] px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/65 hover:bg-cyan-400/10"
              onClick={handleFillSample}
            >
              填充示例
            </button>

            <button
              className="inline-flex items-center justify-center rounded-lg border border-cyan-400/35 bg-[#081324] px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/65 hover:bg-cyan-400/10"
              disabled={!result?.items.length}
              onClick={() => {
                void handleCopy()
              }}
            >
              复制姓名
            </button>

            <button
              className="inline-flex items-center justify-center rounded-lg border border-rose-300/45 bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-100 transition hover:bg-rose-500/20"
              disabled={!conversation && !result}
              onClick={handleClear}
            >
              清空
            </button>
          </div>

          <div className="rounded-lg border border-cyan-400/25 bg-[#07111f] p-3 text-xs leading-6 text-[#c9d6ef]">
            <div className="font-semibold text-cyan-200">识别规则</div>
            <div className="mt-2">1. 识别类似 `张敏：`、`Alice Chen:` 的说话人标签。</div>
            <div>2. 识别类似 `我是张敏`、`I am Bob Li` 的自我介绍。</div>
            <div>3. 识别类似 `联系韩梅梅老师`、`send to Alice Chen` 的转接语句。</div>
            <div>4. 结果为候选姓名，适合快速筛选，不等同于专业 NER 模型。</div>
          </div>
        </div>
      }
      right={
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="text-xs text-[#8fa4c3]">姓名数量</div>
              <div className="mt-2 text-2xl font-semibold text-cyan-100">{result?.items.length || 0}</div>
            </div>
            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="text-xs text-[#8fa4c3]">对话行数</div>
              <div className="mt-2 text-2xl font-semibold text-cyan-100">{result?.totalLines || 0}</div>
            </div>
            <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
              <div className="text-xs text-[#8fa4c3]">总字符数</div>
              <div className="mt-2 text-2xl font-semibold text-cyan-100">{result?.totalCharacters || 0}</div>
            </div>
          </div>

          {!result ? (
            <div className="rounded-lg border border-dashed border-[#3b4e74] bg-[#0a1222]/70 px-4 py-8 text-sm text-[#96a9c8]">
              左侧粘贴一段对话文本后点击“开始分析”，这里会显示候选姓名和命中的上下文。
            </div>
          ) : !result.items.length ? (
            <div className="rounded-lg border border-amber-400/25 bg-amber-500/10 px-4 py-8 text-sm text-amber-100">
              未识别到明显的姓名。可以尝试补充说话人标签、自我介绍句式，或使用更完整的聊天记录。
            </div>
          ) : (
            <>
              <div className="rounded-lg border border-cyan-400/25 bg-[#081324] p-3 text-sm text-[#c9d6ef]">
                <div className="font-semibold text-cyan-200">抽取结果</div>
                <div className="mt-2 text-xs text-[#8fa4c3]">
                  {result.items.map((item) => item.name).join('、')}
                </div>
              </div>

              <div className="space-y-3">
                {result.items.map((item) => (
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
          )}
        </div>
      }
    />
  )
}
