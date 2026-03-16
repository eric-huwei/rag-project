export type NavItem = {
  label: string
  to: string
  description?: string
}

export const NAV_ITEMS: NavItem[] = [
  { label: '概览', to: '/', description: '系统概况与快捷入口' },
  { label: '数据导入', to: '/ingest', description: '上传/加载文档到知识库' },
  { label: '检索问答', to: '/search', description: 'RAG 检索与问答测试' },
  { label: 'Embedding File', to: '/embedding-file', description: '选择/管理 Embedding 配置' },
  { label: '设置', to: '/settings', description: '接口地址、参数与偏好' },
]

