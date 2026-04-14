export type NameSource =
  | 'speaker'
  | 'self_intro'
  | 'contact'
  | 'title'
  | 'english_self_intro'
  | 'english_contact'

export type NameMatch = {
  line: number
  source: NameSource
  excerpt: string
}

export type ExtractedName = {
  name: string
  count: number
  score: number
  confidence: '高' | '中' | '低'
  sources: NameSource[]
  matches: NameMatch[]
}

export type NameExtractionResult = {
  items: ExtractedName[]
  totalLines: number
  totalCharacters: number
}

type InternalCandidate = {
  name: string
  count: number
  score: number
  sources: Set<NameSource>
  matches: NameMatch[]
}

const SOURCE_WEIGHT: Record<NameSource, number> = {
  speaker: 4,
  self_intro: 5,
  contact: 3,
  title: 2,
  english_self_intro: 5,
  english_contact: 3,
}

const SOURCE_LABEL: Record<NameSource, string> = {
  speaker: '说话人标记',
  self_intro: '中文自我介绍',
  contact: '中文联系/转接',
  title: '称谓识别',
  english_self_intro: '英文自我介绍',
  english_contact: '英文联系/转接',
}

const CHINESE_COMPOUND_SURNAMES = [
  '欧阳',
  '司马',
  '上官',
  '诸葛',
  '东方',
  '独孤',
  '夏侯',
  '尉迟',
  '公孙',
  '慕容',
  '司徒',
  '令狐',
  '宇文',
  '长孙',
  '南宫',
  '皇甫',
  '轩辕',
  '呼延',
  '澹台',
  '公冶',
  '宗政',
  '濮阳',
  '淳于',
  '单于',
  '太叔',
  '申屠',
]

const CHINESE_SINGLE_SURNAMES = new Set(
  Array.from(
    '赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包左石崔吉龚程嵇邢裴陆荣翁荀甄芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司黎薄印宿白怀蒲邰从鄂索籍赖卓蔺屠乔阴郁胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东殴殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公晋楚闫法汝鄢涂钦岳帅缑亢况郈有琴归海'
  ),
)

const CHINESE_STOPWORDS = new Set([
  '你好',
  '您好',
  '请问',
  '谢谢',
  '麻烦',
  '可以',
  '今天',
  '明天',
  '后天',
  '下午',
  '上午',
  '晚上',
  '现在',
  '这个',
  '那个',
  '这里',
  '这边',
  '客服',
  '客户',
  '用户',
  '同学',
  '老师',
  '经理',
  '女士',
  '先生',
  '主任',
  '老板',
  '公司',
  '系统',
  '平台',
  '团队',
  '你们',
  '我们',
  '他们',
  '大家',
  '自己',
  '情况',
  '资料',
  '流程',
  '问题',
  '需求',
  '结果',
  '面试',
  '会议',
  '电话',
  '消息',
  '一下',
  '一位',
  '一名',
  '一份',
  '收到',
  '辛苦',
])

const ENGLISH_STOPWORDS = new Set([
  'User',
  'Assistant',
  'Customer',
  'Agent',
  'System',
  'Support',
  'Manager',
  'Team',
  'Hello',
  'Thanks',
  'Thank',
  'Please',
  'Hr',
  'Admin',
  'Service',
])

function normalizeInput(text: string) {
  return text.replace(/\r\n?/g, '\n').replace(/[“”]/g, '"').replace(/[‘’]/g, "'").trim()
}

function cleanCandidate(value: string) {
  return value.trim().replace(/^[\s"'`]+|[\s"',.，。！？!?:：;；]+$/g, '')
}

function toSnippet(line: string) {
  const value = line.trim()
  if (value.length <= 96) return value
  return `${value.slice(0, 96)}...`
}

function isLikelyChineseName(candidate: string) {
  if (!/^[\u4e00-\u9fa5]{2,4}$/.test(candidate)) return false
  if (CHINESE_STOPWORDS.has(candidate)) return false
  if (candidate.split('').every((char) => char === candidate[0])) return false

  const compound = candidate.slice(0, 2)
  if (CHINESE_COMPOUND_SURNAMES.includes(compound)) return true
  return CHINESE_SINGLE_SURNAMES.has(candidate[0]!)
}

function normalizeEnglishWord(word: string) {
  if (word.length <= 1) return word.toUpperCase()
  return `${word[0]!.toUpperCase()}${word.slice(1).toLowerCase()}`
}

function normalizeEnglishName(value: string) {
  return value
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((word) =>
      word
        .split(/([-'`])/)
        .map((part) => (/[-'`]/.test(part) ? part : normalizeEnglishWord(part)))
        .join(''),
    )
    .join(' ')
}

function isLikelyEnglishName(candidate: string) {
  if (!/^[A-Za-z][A-Za-z.'`-]*(?: [A-Za-z][A-Za-z.'`-]*){0,2}$/.test(candidate)) return false

  const words = candidate.split(/\s+/).filter(Boolean)
  if (!words.length || words.length > 3) return false
  if (words.some((word) => word.length < 2)) return false

  const normalized = normalizeEnglishName(candidate)
  if (ENGLISH_STOPWORDS.has(normalized)) return false

  return words.every((word) => /^[A-Z][a-z.'`-]*$/.test(normalizeEnglishWord(word)))
}

function getConfidence(score: number, count: number, sources: Set<NameSource>): '高' | '中' | '低' {
  if (score >= 8 || count >= 3 || sources.has('self_intro') || sources.has('english_self_intro')) {
    return '高'
  }
  if (score >= 5 || count >= 2) return '中'
  return '低'
}

function pushCandidate(
  map: Map<string, InternalCandidate>,
  rawName: string,
  source: NameSource,
  line: number,
  excerpt: string,
) {
  const cleaned = cleanCandidate(rawName)
  if (!cleaned) return

  const name = /[\u4e00-\u9fa5]/.test(cleaned) ? cleaned : normalizeEnglishName(cleaned)
  const isValid = /[\u4e00-\u9fa5]/.test(name) ? isLikelyChineseName(name) : isLikelyEnglishName(name)

  if (!isValid) return

  const entry = map.get(name) || {
    name,
    count: 0,
    score: 0,
    sources: new Set<NameSource>(),
    matches: [],
  }

  entry.count += 1
  entry.score += SOURCE_WEIGHT[source]
  entry.sources.add(source)

  if (!entry.matches.some((item) => item.line === line && item.source === source)) {
    entry.matches.push({ line, source, excerpt })
  }

  map.set(name, entry)
}

export function formatNameSource(source: NameSource) {
  return SOURCE_LABEL[source]
}

export function extractNamesFromConversation(input: string): NameExtractionResult {
  const normalized = normalizeInput(input)
  if (!normalized) {
    return { items: [], totalLines: 0, totalCharacters: 0 }
  }

  const lines = normalized
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  const candidates = new Map<string, InternalCandidate>()

  const chinesePatterns: Array<{ source: NameSource; regex: RegExp }> = [
    { source: 'speaker', regex: /^([\u4e00-\u9fa5]{2,4})(?=\s*[:：])/g },
    { source: 'self_intro', regex: /(?:我是|我叫|名字叫|名字是|姓名是|本人是|这边是|这里是)([\u4e00-\u9fa5]{2,4})/g },
    {
      source: 'contact',
      regex: /(?:联系|找|咨询|转给|转接|请转|麻烦转给|发给)([\u4e00-\u9fa5]{2,4})(?:老师|经理|医生|女士|先生|主任|总)?/g,
    },
    { source: 'contact', regex: /(?:联系人|负责人|客户经理|接待老师)[：:\s]+([\u4e00-\u9fa5]{2,4})/g },
    { source: 'title', regex: /([\u4e00-\u9fa5]{2,4})(?:老师|经理|医生|女士|先生|主任|总)/g },
  ]

  const englishPatterns: Array<{ source: NameSource; regex: RegExp }> = [
    { source: 'speaker', regex: /^([A-Z][A-Za-z.'`-]*(?: [A-Z][A-Za-z.'`-]*){0,2})(?=\s*[:：])/g },
    {
      source: 'english_self_intro',
      regex: /\b(?:I am|I'm|my name is|My name is|This is)\s+([A-Z][A-Za-z.'`-]*(?: [A-Z][A-Za-z.'`-]*){0,2})/g,
    },
    {
      source: 'english_contact',
      regex: /\b(?:contact|find|ask for|transfer to|send to)\s+([A-Z][A-Za-z.'`-]*(?: [A-Z][A-Za-z.'`-]*){0,2})/gi,
    },
    {
      source: 'english_contact',
      regex: /(?:Contact|联系人|负责人)[：:\s]+([A-Z][A-Za-z.'`-]*(?: [A-Z][A-Za-z.'`-]*){0,2})/g,
    },
  ]

  lines.forEach((line, index) => {
    const excerpt = toSnippet(line)
    const lineNumber = index + 1

    chinesePatterns.forEach(({ source, regex }) => {
      for (const match of line.matchAll(regex)) {
        const name = match[1]
        if (name) pushCandidate(candidates, name, source, lineNumber, excerpt)
      }
    })

    englishPatterns.forEach(({ source, regex }) => {
      for (const match of line.matchAll(regex)) {
        const name = match[1]
        if (name) pushCandidate(candidates, name, source, lineNumber, excerpt)
      }
    })
  })

  const items = Array.from(candidates.values())
    .map((item) => ({
      name: item.name,
      count: item.count,
      score: item.score,
      confidence: getConfidence(item.score, item.count, item.sources),
      sources: Array.from(item.sources),
      matches: item.matches.sort((a, b) => a.line - b.line),
    }))
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score
      if (b.count !== a.count) return b.count - a.count
      return a.name.localeCompare(b.name, 'zh-CN')
    })

  return {
    items,
    totalLines: lines.length,
    totalCharacters: normalized.length,
  }
}
