export const SUPPLY_LABEL: Record<string, string> = { rations: 'Rations', fuel: 'Fuel', medical: 'Medical supplies', spares: 'Maintenance spares' }
export const fmt = (n: number | null | undefined, d = 0) => (n === null || n === undefined || Number.isNaN(n) ? '—' : n.toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d }))
export function fmtHours(h: number | null | undefined) {
  if (h === null || h === undefined) return '—'
  if (h < 48) return `${Math.round(h)} h`
  return `${(h / 24).toFixed(1)} d`
}
export const fmtDateTime = (iso?: string | null) => iso ? new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }) : '—'
export const fmtDate = (iso?: string | null) => iso ? new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export function ago(iso?: string | null) {
  if (!iso) return '—'
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  if (m < 2880) return `${Math.round(m / 60)} h ago`
  return `${Math.round(m / 1440)} d ago`
}
export const pct = (n: number | null | undefined, d = 0) => (n === null || n === undefined ? '—' : `${(n * 100).toFixed(d)}%`)
export const HEALTH_COLOR: Record<string, string> = { healthy: '#7DC161', attention: '#FFCD2E', elevated: '#F57F2A', critical: '#D64545' }
export const RISK_COLOR: Record<string, string> = { low: '#7DC161', moderate: '#FFCD2E', elevated: '#F57F2A', high: '#D64545', closed: '#4E4F4F' }
export const CHART = { purple: '#351A55', lilac: '#746FA7', teal: '#3498B3', blue: '#355493', grid: '#E4E6EC' }
