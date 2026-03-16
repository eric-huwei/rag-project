import { NavLink } from 'react-router-dom'
import { NAV_ITEMS } from './navItems'
import { cn } from '../ui/cn'

export function SidebarNav({ compact = false }: { compact?: boolean }) {
  return (
    <div className={cn('px-3 py-4 md:px-4', compact ? 'overflow-x-auto py-3' : '')}>
      <div className={cn('mb-4 border-b border-cyan-400/30 pb-3', compact ? 'mb-2 pb-2' : '')}>
        <div className="text-sm font-semibold tracking-[0.2em] text-cyan-300">RAG CONSOLE</div>
        {!compact ? <div className="mt-1 text-xs text-cyan-100/75">智能检索与知识增强平台</div> : null}
      </div>

      <nav className={cn(compact ? 'flex gap-2' : 'space-y-2')}>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              cn(
                'group block rounded-md border px-3 py-2 text-sm font-medium transition-all',
                compact ? 'whitespace-nowrap' : '',
                isActive
                  ? 'border-cyan-300/80 bg-cyan-300/20 text-cyan-100 shadow-[0_0_16px_rgba(34,211,238,0.3)]'
                  : 'border-cyan-400/25 bg-[#091a31]/45 text-cyan-100/90 hover:border-cyan-300/60 hover:bg-cyan-400/10 hover:text-white',
              )
            }
          >
            <div className="flex items-center justify-between gap-3">
              <span className="truncate">{item.label}</span>
            </div>
            {!compact && item.description ? (
              <div className="mt-1 text-xs text-cyan-100/60 group-hover:text-cyan-100/85">{item.description}</div>
            ) : null}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
