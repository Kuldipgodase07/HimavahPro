import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate, Navigate } from 'react-router-dom'
import { Activity, BarChart3, Bell, Brain, ChevronDown, ClipboardCheck, FileText, Gauge, LayoutDashboard, LogOut, Map as MapIcon, Menu, Package, Radio, Route as RouteIcon, ScrollText, Search, Settings, ShieldCheck, Truck, X, Lock, FlaskConical } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { useApi } from '../lib/useApi'
import { ago } from '../lib/format'
import { Logo } from './Logo'
import { Badge, cx } from './ui'

export const NAV = [
  { to: '/app', label: 'Command Centre', icon: LayoutDashboard, perm: 'dashboard.view', end: true },
  { to: '/app/map', label: 'Logistics Map', icon: MapIcon, perm: 'map.view' },
  { to: '/app/forecasts', label: 'Demand Forecasts', icon: BarChart3, perm: 'forecast.view' },
  { to: '/app/inventory', label: 'Inventory & Stock Health', icon: Package, perm: 'inventory.view' },
  { to: '/app/routes', label: 'Route Intelligence', icon: RouteIcon, perm: 'routes.view' },
  { to: '/app/recommendations', label: 'Supply Recommendations', icon: ClipboardCheck, perm: 'recs.view' },
  { to: '/app/simulator', label: 'What-if Simulator', icon: FlaskConical, perm: 'sim.view' },
  { to: '/app/convoys', label: 'Convoy & Movement Status', icon: Truck, perm: 'convoy.view' },
  { to: '/app/field', label: 'IoT & Field Reports', icon: Radio, perm: 'field.use' },
  { to: '/app/responsible-ai', label: 'Responsible AI', icon: Brain, perm: 'ai.view' },
  { to: '/app/governance', label: 'Privacy & Security', icon: Lock, perm: 'governance.view' },
  { to: '/app/audit', label: 'Audit & Governance', icon: ScrollText, perm: 'audit.view' },
  { to: '/app/reports', label: 'Reports', icon: FileText, perm: 'reports.view' },
  { to: '/app/admin', label: 'Administration', icon: Settings, perm: 'admin.view' },
]

export function RequireAuth() {
  const { user, ready } = useAuth(); const loc = useLocation()
  if (!ready) return <div className="grid min-h-screen place-items-center text-muted" role="status">Loading…</div>
  if (!user) return <Navigate to="/signin" state={{ from: loc.pathname }} replace />
  return <Shell />
}

function Shell() {
  const { user, can, signOut } = useAuth(); const nav = useNavigate(); const loc = useLocation()
  const [open, setOpen] = useState(false); const [menu, setMenu] = useState(false); const [bell, setBell] = useState(false); const [q, setQ] = useState('')
  const dash = useApi<any>(can('dashboard.view') ? '/api/dashboard' : null)
  const items = NAV.filter((n) => can(n.perm))
  useEffect(() => setOpen(false), [loc.pathname])
  const current = useMemo(() => NAV.find((n) => (n.end ? loc.pathname === n.to : loc.pathname.startsWith(n.to)))?.label ?? '', [loc.pathname])
  const searchRef = useRef<HTMLInputElement>(null)
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === '/' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement)) { e.preventDefault(); searchRef.current?.focus() } }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [])
  const results = useMemo(() => {
    const s = q.trim().toLowerCase(); if (!s) return []
    const pages = items.filter((n) => n.label.toLowerCase().includes(s)).map((n) => ({ label: n.label, to: n.to, hint: 'Page' }))
    const posts = /^post|k\d|^\d/i.test(s) ? Array.from({ length: 18 }, (_, i) => `POST-K${String(i + 1).padStart(2, '0')}`).filter((p) => p.toLowerCase().includes(s)).map((p) => ({ label: p, to: `/app/map?post=${p}`, hint: 'Post' })) : []
    const recs = /^rec/i.test(s) ? [{ label: `Search recommendations for “${q}”`, to: `/app/recommendations?q=${encodeURIComponent(q)}`, hint: 'Recommendations' }] : []
    return [...pages, ...posts, ...recs].slice(0, 7)
  }, [q, items])
  const kp = dash.data?.kpis
  const Side = (
    <nav aria-label="Primary" className="flex h-full flex-col bg-deep text-white">
      <div className="px-4 py-4"><Logo light /></div>
      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-4">
        {items.map((n) => (
          <li key={n.to}><NavLink to={n.to} end={n.end} className={({ isActive }) => cx('flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors', isActive ? 'bg-white/15 text-white' : 'text-[#D8D4EC] hover:bg-white/10')}>
            <n.icon className="h-4 w-4 shrink-0" aria-hidden />{n.label}</NavLink></li>
        ))}
      </ul>
      <div className="border-t border-white/10 p-3 text-[11px] leading-snug text-[#CFCBE6]">Prototype · synthetic data only. Not an operational system.</div>
    </nav>
  )
  return (
    <div className="min-h-screen bg-bg">
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 lg:block">{Side}</aside>
      {open && <div className="fixed inset-0 z-40 lg:hidden"><div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} /><div className="absolute inset-y-0 left-0 w-64">{Side}<button aria-label="Close menu" className="absolute right-2 top-3 rounded p-1 text-white" onClick={() => setOpen(false)}><X className="h-5 w-5" /></button></div></div>}
      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 border-b border-line bg-white">
          <div className="flex items-center gap-3 px-4 py-2.5">
            <button className="rounded p-1.5 hover:bg-lilac-soft lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button>
            <div className="hidden min-w-0 sm:block"><div className="text-[11px] text-muted">HimavahPro / {current}</div></div>
            <div className="relative mx-auto w-full max-w-md">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden />
              <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && results[0]) { nav(results[0].to); setQ('') } if (e.key === 'Escape') setQ('') }} aria-label="Global search" placeholder="Search pages, posts (POST-K04), recommendations…  ( / )" className="w-full rounded-lg border border-line bg-bg py-2 pl-9 pr-3 text-[13px] focus:border-lilac" />
              {q && <ul className="absolute z-30 mt-1 w-full rounded-lg border border-line bg-white p-1 shadow-lg">{results.length ? results.map((r) => <li key={r.label}><button className="flex w-full items-center justify-between rounded px-3 py-2 text-left text-[13px] hover:bg-lilac-soft" onClick={() => { nav(r.to); setQ('') }}>{r.label}<span className="text-[11px] text-muted">{r.hint}</span></button></li>) : <li className="px-3 py-2 text-xs text-muted">No matches</li>}</ul>}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <Badge tone="purple" icon={false}><FlaskConical className="mr-1 h-3 w-3" aria-hidden />Simulated</Badge>
              {dash.data && <span className="hidden items-center gap-1 text-[11px] text-muted xl:flex"><Activity className="h-3.5 w-3.5" aria-hidden />Data as of {ago(dash.data.as_of)}</span>}
              <div className="relative">
                <button aria-label="Notifications" aria-expanded={bell} onClick={() => { setBell(!bell); setMenu(false) }} className="relative rounded-lg p-2 hover:bg-lilac-soft"><Bell className="h-[18px] w-[18px]" />{(dash.data?.alerts?.length ?? 0) > 0 && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-crit" aria-hidden />}</button>
                {bell && <div className="absolute right-0 z-30 mt-2 w-80 rounded-xl border border-line bg-white p-2 shadow-lg"><div className="px-2 py-1 text-xs font-semibold text-muted">Notifications</div>
                  {(dash.data?.alerts ?? []).slice(0, 4).map((a: any, i: number) => <button key={i} onClick={() => { nav('/app'); setBell(false) }} className="block w-full rounded px-2 py-2 text-left text-[13px] hover:bg-lilac-soft"><span className="font-medium">{a.post_id}</span> · {a.message}</button>)}
                  {kp && <button onClick={() => { nav('/app/recommendations'); setBell(false) }} className="block w-full rounded px-2 py-2 text-left text-[13px] hover:bg-lilac-soft">{kp.pending_approvals} recommendation(s) awaiting review</button>}
                  {!dash.data && <p className="px-2 py-3 text-xs text-muted">No notifications available for your role.</p>}</div>}
              </div>
              <div className="relative">
                <button aria-expanded={menu} aria-haspopup="menu" onClick={() => { setMenu(!menu); setBell(false) }} className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-lilac-soft">
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-deep text-xs font-bold text-white" aria-hidden>{user!.name.split(' ').slice(-2).map((w) => w[0]).join('')}</span>
                  <span className="hidden text-left leading-tight md:block"><span className="block text-[13px] font-semibold">{user!.name}</span><span className="block text-[11px] text-muted">{user!.role_label}</span></span><ChevronDown className="h-3.5 w-3.5" aria-hidden />
                </button>
                {menu && <div role="menu" className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-line bg-white p-1 shadow-lg">
                  <div className="px-3 py-2 text-xs text-muted">{user!.role_label}{user!.post_id && ` · ${user!.post_id}`}<br />Demonstration sign-in</div>
                  <button role="menuitem" className="flex w-full items-center gap-2 rounded px-3 py-2 text-[13px] hover:bg-lilac-soft" onClick={async () => { await signOut(); nav('/') }}><LogOut className="h-4 w-4" aria-hidden />Sign out</button></div>}
              </div>
            </div>
          </div>
        </header>
        <main id="main" className="px-4 py-5 lg:px-6"><Outlet /></main>
      </div>
    </div>
  )
}
