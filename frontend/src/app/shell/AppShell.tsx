import { Outlet } from 'react-router-dom'
import { SidebarNav } from '../../components/navigation/SidebarNav'
import { AppToaster, ToastProvider } from '../../components/status/toast'

function formatDate(date: Date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}/${m}/${d}`
}

export function AppShell() {
  const today = formatDate(new Date())

  return (
    <ToastProvider>
      <div className="cyber-screen min-h-screen text-[#cfeaff]">
        <div className="cyber-grid" aria-hidden="true" />

        <div className="relative z-10 grid min-h-screen grid-cols-1 md:grid-cols-[280px_1fr]">
          <aside className="sticky top-0 hidden h-screen border-r border-cyan-400/35 bg-[#071227]/75 backdrop-blur-sm md:block">
            <SidebarNav />
          </aside>

          <main className="min-w-0">
            <div className="border-b border-cyan-400/35 bg-[#071227]/90 md:hidden">
              <SidebarNav compact />
            </div>

            <div className="p-4 md:p-6">
              <header className="cyber-header-panel mb-4 md:mb-6">
                <h1 className="text-base font-semibold tracking-[0.18em] text-cyan-300 md:text-xl">
                  多模态大模型 RAG 系统
                </h1>
                <div className="text-sm font-medium text-cyan-300/90">{today}</div>
              </header>

              <Outlet />
            </div>
          </main>
        </div>

        <AppToaster />
      </div>
    </ToastProvider>
  )
}
