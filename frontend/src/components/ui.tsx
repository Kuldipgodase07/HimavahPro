import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle, Inbox, ShieldAlert } from 'lucide-react'
import clsx from 'clsx'
import { ApiError } from '../lib/api'

export const cx = clsx

export function Card({ title, action, children, className, pad = true, sub }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; pad?: boolean; sub?: ReactNode }) {
  return (
    <section className={cx('rounded-xl border border-line bg-white shadow-[0_1px_2px_rgba(20,16,40,.04)]', className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div><h2 className="text-[14px] font-semibold text-ink">{title}</h2>{sub && <p className="text-xs text-muted">{sub}</p>}</div>{action}
        </header>
      )}
      <div className={pad ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; size?: 'sm' | 'md'; loading?: boolean }
export function Button({ variant = 'secondary', size = 'md', loading, className, children, disabled, ...rest }: BtnProps) {
  const v = { primary: 'bg-deep text-white hover:bg-deep-2 border-deep', secondary: 'bg-white text-ink hover:bg-lilac-soft border-line', ghost: 'bg-transparent text-deep hover:bg-lilac-soft border-transparent', danger: 'bg-crit text-white hover:bg-crit-ink border-crit' }[variant]
  return (
    <button {...rest} disabled={disabled || loading} className={cx('inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50', size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-[13px]', v, className)}>
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}{children}
    </button>
  )
}

const TONES: Record<string, string> = {
  ok: 'bg-[#e9f6e3] text-ok-ink', warn: 'bg-[#fff6d1] text-warn-ink', orange: 'bg-[#fde8d6] text-orange-ink', crit: 'bg-[#fbe3e3] text-crit-ink',
  info: 'bg-[#e4eef9] text-blue', purple: 'bg-lilac-soft text-deep', gray: 'bg-[#eceef3] text-gray',
}
const ICON: Record<string, ReactNode> = { ok: <CheckCircle2 className="h-3 w-3" />, warn: <Info className="h-3 w-3" />, orange: <AlertTriangle className="h-3 w-3" />, crit: <XCircle className="h-3 w-3" /> }
export function Badge({ tone = 'gray', children, icon = true }: { tone?: keyof typeof TONES | string; children: ReactNode; icon?: boolean }) {
  return <span className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold', TONES[tone])}>{icon && ICON[tone]}{children}</span>
}
const HEALTH_TONE: Record<string, string> = { healthy: 'ok', attention: 'warn', elevated: 'orange', critical: 'crit' }
export const HealthBadge = ({ h }: { h: string }) => <Badge tone={HEALTH_TONE[h] ?? 'gray'}>{h[0].toUpperCase() + h.slice(1)}</Badge>
const RISK_TONE: Record<string, string> = { low: 'ok', moderate: 'warn', elevated: 'orange', high: 'crit', closed: 'gray' }
export const RiskBadge = ({ r }: { r: string }) => <Badge tone={RISK_TONE[r] ?? 'gray'}>{r === 'closed' ? 'Closed' : r[0].toUpperCase() + r.slice(1) + ' risk'}</Badge>
const CONF_TONE: Record<string, string> = { High: 'ok', Medium: 'warn', Low: 'crit' }
export const ConfBadge = ({ c }: { c: string }) => <Badge tone={CONF_TONE[c] ?? 'gray'}>{c} confidence</Badge>
const URG_TONE: Record<string, string> = { critical: 'crit', high: 'orange', medium: 'warn' }
export const UrgBadge = ({ u }: { u: string }) => <Badge tone={URG_TONE[u] ?? 'gray'}>{u[0].toUpperCase() + u.slice(1)}</Badge>
const STATUS_TONE: Record<string, string> = { Draft: 'gray', 'Pending Review': 'info', 'Info Requested': 'warn', Approved: 'ok', Rejected: 'crit', 'Simulated Dispatch': 'purple', Completed: 'ok', Withdrawn: 'gray', Planned: 'gray', 'In Transit': 'info', Delayed: 'orange', Incident: 'crit', Arrived: 'ok' }
export const StatusBadge = ({ s }: { s: string }) => <Badge tone={STATUS_TONE[s] ?? 'gray'}>{s}</Badge>

export function SimBanner({ children = 'SIMULATED ENVIRONMENT · Synthetic data · Not connected to any operational system' }: { children?: ReactNode }) {
  return <div role="note" className="flex items-center gap-2 rounded-lg border border-lilac-line bg-lilac-soft px-3 py-1.5 text-xs font-medium text-deep"><ShieldAlert className="h-3.5 w-3.5 shrink-0" aria-hidden />{children}</div>
}

export function Skeleton({ className }: { className?: string }) { return <div className={cx('skeleton', className)} aria-hidden /> }
export function PageSkeleton() { return <div role="status" aria-label="Loading" className="space-y-4"><div className="grid grid-cols-2 gap-3 lg:grid-cols-6">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div><Skeleton className="h-72" /><Skeleton className="h-48" /></div> }
export function Empty({ title = 'Nothing to show', hint }: { title?: string; hint?: string }) {
  return <div className="flex flex-col items-center gap-1 py-10 text-center text-muted"><Inbox className="h-7 w-7 text-lilac" aria-hidden /><p className="font-medium text-gray">{title}</p>{hint && <p className="text-xs">{hint}</p>}</div>
}
export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const denied = error.status === 403
  return (
    <div role="alert" className="mx-auto my-10 max-w-md rounded-xl border border-line bg-white p-6 text-center">
      {denied ? <ShieldAlert className="mx-auto h-8 w-8 text-crit" aria-hidden /> : <AlertTriangle className="mx-auto h-8 w-8 text-orange" aria-hidden />}
      <h2 className="mt-2 text-base font-semibold">{denied ? 'Permission denied' : 'Something went wrong'}</h2>
      <p className="mt-1 text-sm text-muted">{denied ? 'Your role does not have access to this workspace. The attempt has been recorded in the audit trail.' : error.message}</p>
      {!denied && onRetry && <Button className="mt-4" onClick={onRetry}>Try again</Button>}
    </div>
  )
}
export function Async<T>({ state, children, skeleton }: { state: { data: T | null; error: ApiError | null; loading: boolean; reload: () => void }; children: (d: T) => ReactNode; skeleton?: ReactNode }) {
  if (state.error && !state.data) return <ErrorState error={state.error} onRetry={state.reload} />
  if (!state.data) return <>{skeleton ?? <PageSkeleton />}</>
  return <>{children(state.data)}</>
}

export function Kpi({ icon, label, value, sub, tone }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode; tone?: 'crit' | 'warn' | 'ok' }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-line bg-white p-3.5">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-lilac-soft text-deep [&_svg]:h-5 [&_svg]:w-5" aria-hidden>{icon}</span>
      <div className="min-w-0"><div className="text-xs font-medium leading-tight text-muted">{label}</div>
        <div className={cx('num text-2xl font-bold leading-tight', tone === 'crit' ? 'text-crit-ink' : tone === 'warn' ? 'text-orange-ink' : 'text-ink')}>{value}</div>
        {sub && <div className="text-[11px] text-muted">{sub}</div>}</div>
    </div>
  )
}

// --- modal / drawer ---------------------------------------------------------------------------------------------
function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement as HTMLElement | null
    const el = ref.current
    el?.querySelector<HTMLElement>('[data-autofocus],input,select,textarea,button')?.focus()
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && el) {
        const f = [...el.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])')]
        if (!f.length) return
        const first = f[0], last = f[f.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('keydown', key); prev?.focus() }
  }, [open, onClose])
  return ref
}
export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useDialog(open, onClose); const id = useId()
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#1b1030]/50 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} className={cx('max-h-[90vh] w-full overflow-auto rounded-xl bg-white shadow-xl', wide ? 'max-w-2xl' : 'max-w-md')}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3"><h2 id={id} className="text-[15px] font-semibold">{title}</h2><button aria-label="Close" onClick={onClose} className="rounded p-1 hover:bg-lilac-soft"><X className="h-4 w-4" /></button></div>
        <div className="p-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line bg-bg px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}
export function Drawer({ open, onClose, title, children, width = 'max-w-xl' }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: string }) {
  const ref = useDialog(open, onClose); const id = useId()
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-[#1b1030]/40" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} className={cx('h-full w-full overflow-auto bg-white shadow-xl', width)}>
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-white px-5 py-3"><h2 id={id} className="text-[15px] font-semibold">{title}</h2><button aria-label="Close" onClick={onClose} className="rounded p-1 hover:bg-lilac-soft"><X className="h-4 w-4" /></button></div>
        <div className="p-5">{children}</div>
      </aside>
    </div>
  )
}
export function Confirm({ open, title, body, confirmLabel = 'Confirm', danger, onConfirm, onClose, loading }: { open: boolean; title: string; body: ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void; onClose: () => void; loading?: boolean }) {
  return <Modal open={open} onClose={onClose} title={title} footer={<><Button onClick={onClose}>Cancel</Button><Button variant={danger ? 'danger' : 'primary'} loading={loading} onClick={onConfirm}>{confirmLabel}</Button></>}><div className="text-sm text-gray">{body}</div></Modal>
}

// --- toasts -------------------------------------------------------------------------------------------------------
type Toast = { id: number; kind: 'success' | 'error' | 'info'; text: string }
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random()
    setItems((t) => [...t, { id, kind, text }]); setTimeout(() => setItems((t) => t.filter((x) => x.id !== id)), 5000)
  }, [])
  return (
    <ToastCtx.Provider value={push}>{children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(92vw,360px)] flex-col gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className="pointer-events-auto flex items-start gap-2 rounded-lg border border-line bg-white p-3 text-sm shadow-lg">
            {t.kind === 'success' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok-ink" /> : t.kind === 'error' ? <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-crit" /> : <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue" />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

// --- form bits ----------------------------------------------------------------------------------------------------
export function Field({ label, error, hint, children }: { label: string; error?: string | null; hint?: string; children: (id: string) => ReactNode }) {
  const id = useId()
  return <div><label htmlFor={id} className="mb-1 block text-xs font-semibold text-gray">{label}</label>{children(id)}{hint && !error && <p className="mt-1 text-[11px] text-muted">{hint}</p>}{error && <p role="alert" className="mt-1 text-xs font-medium text-crit-ink">{error}</p>}</div>
}
export const inputCls = 'rounded-lg border border-line bg-white px-3 py-2 text-[13px] placeholder:text-[#9a9ba5] focus:border-lilac'
const wcls = (c?: string) => (c && /(^|\s)w-/.test(c) ? c : cx('w-full', c))
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={cx(inputCls, wcls(p.className))} />
export const Select = (p: React.SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={cx(inputCls, 'pr-8', wcls(p.className))} />
export const Textarea = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={cx(inputCls, 'min-h-[72px]', wcls(p.className))} />

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div role="tablist" className="flex flex-wrap gap-1 rounded-lg bg-[#eceef3] p-1">
      {tabs.map((t) => <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)} className={cx('rounded-md px-3 py-1.5 text-[13px] font-medium', value === t.id ? 'bg-white text-deep shadow-sm' : 'text-gray hover:text-deep')}>{t.label}</button>)}
    </div>
  )
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-xl font-bold text-ink">{title}</h1>{sub && <p className="text-[13px] text-muted">{sub}</p>}</div><div className="flex flex-wrap items-center gap-2">{actions}</div></div>
}

export type Col<R> = { key: string; label: string; sortable?: boolean; render?: (r: R) => ReactNode; align?: 'right'; className?: string }
export function DataTable<R extends Record<string, any>>({ cols, rows, onRow, sort, onSort, empty, rowKey }: { cols: Col<R>[]; rows: R[]; onRow?: (r: R) => void; sort?: { key: string; order: 'asc' | 'desc' }; onSort?: (k: string) => void; empty?: ReactNode; rowKey: (r: R) => string | number }) {
  if (!rows.length) return <>{empty ?? <Empty />}</>
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-max text-left text-[13px]">
        <thead><tr className="border-b border-line text-[11px] uppercase tracking-wide text-muted">
          {cols.map((c) => (
            <th key={c.key} scope="col" aria-sort={sort?.key === c.key ? (sort.order === 'asc' ? 'ascending' : 'descending') : undefined} className={cx('px-3 py-2 font-semibold', c.align === 'right' && 'text-right')}>
              {c.sortable && onSort ? <button className="inline-flex items-center gap-1 uppercase hover:text-deep" onClick={() => onSort(c.key)}>{c.label}{sort?.key === c.key && <span aria-hidden>{sort.order === 'asc' ? '▲' : '▼'}</span>}</button> : c.label}
            </th>
          ))}
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)} onClick={onRow ? () => onRow(r) : undefined} onKeyDown={onRow ? (e) => { if (e.key === 'Enter') onRow(r) } : undefined} tabIndex={onRow ? 0 : undefined} className={cx('border-b border-line/70 last:border-0', onRow && 'cursor-pointer hover:bg-lilac-soft/60')}>
              {cols.map((c) => <td key={c.key} className={cx('px-3 py-2.5 align-middle', c.align === 'right' && 'num text-right', c.className)}>{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
export function Pager({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return <div className="flex items-center justify-between px-3 py-2 text-xs text-muted"><span>{total} records</span><div className="flex items-center gap-2"><Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button><span>Page {page} of {pages}</span><Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button></div></div>
}
export const Kv = ({ k, v }: { k: string; v: ReactNode }) => <div className="flex justify-between gap-4 border-b border-line/60 py-1.5 text-[13px] last:border-0"><span className="text-muted">{k}</span><span className="text-right font-medium">{v}</span></div>
export function Stepper({ flow, current }: { flow: string[]; current: string }) {
  const rejected = current === 'Rejected' || current === 'Withdrawn'
  const idx = flow.indexOf(current === 'Info Requested' ? 'Pending Review' : current)
  return (
    <ol className="flex flex-wrap items-center gap-1 text-[11px]" aria-label="Status progression">
      {flow.map((s, i) => {
        const done = !rejected && i < idx, now = !rejected && i === idx
        return <li key={s} className="flex items-center gap-1"><span className={cx('rounded-full px-2 py-0.5 font-semibold', now ? 'bg-deep text-white' : done ? 'bg-[#e9f6e3] text-ok-ink' : 'bg-[#eceef3] text-muted')}>{done ? '✓ ' : ''}{s}</span>{i < flow.length - 1 && <span className="text-muted" aria-hidden>→</span>}</li>
      })}
      {rejected && <li><Badge tone="crit">{current}</Badge></li>}
    </ol>
  )
}
