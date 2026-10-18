import { Link } from 'react-router-dom'
import { CloudSnow, Mountain, Radio, Truck } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { SUPPLY_LABEL, fmt, fmtDateTime, fmtHours } from '../lib/format'
import { Badge, ConfBadge, ErrorState, HealthBadge, RiskBadge, Skeleton, StatusBadge, UrgBadge } from './ui'

export function PostPanel({ postId }: { postId: string }) {
  const s = useApi<any>(`/api/posts/${postId}`, [postId])
  if (s.error && !s.data) return <ErrorState error={s.error} onRetry={s.reload} />
  if (!s.data) return <div className="space-y-2"><Skeleton className="h-6 w-2/3" /><Skeleton className="h-32" /><Skeleton className="h-24" /></div>
  const d = s.data, n = d.node
  return (
    <div className="space-y-4 text-[13px]">
      <div><div className="flex items-center gap-2"><h3 className="text-base font-bold">{n.id}</h3><Badge tone="gray" icon={false}>Tier {n.tier}</Badge></div><p className="text-muted">{n.name} · {n.formation} · {n.alt_m.toLocaleString()} m{n.helipad ? ' · helipad' : ''}</p><p className="text-[11px] text-muted">Fictional post. Synthetic data.</p></div>
      {d.weather && <div className="flex flex-wrap gap-3 rounded-lg bg-lilac-soft px-3 py-2 text-xs text-deep"><span className="flex items-center gap-1"><CloudSnow className="h-3.5 w-3.5" aria-hidden />{d.weather.temp_c}°C · {d.weather.snow_cm} cm snow</span><span className="flex items-center gap-1"><Mountain className="h-3.5 w-3.5" aria-hidden />Wind {d.weather.wind_kph} km/h</span><span className="text-muted">simulated weather</span></div>}
      <div><h4 className="mb-1 font-semibold">Inventory health</h4>
        <ul className="divide-y divide-line rounded-lg border border-line">{d.inventory.map((i: any) => (
          <li key={i.id} className="flex items-center justify-between gap-2 px-3 py-2"><div><div className="font-medium">{SUPPLY_LABEL[i.supply_class]}</div><div className="num text-xs text-muted">{fmt(i.usable)} {i.unit} · {i.dos} d supply · stockout ~{fmtHours(i.tts_p50_h)}</div></div><div className="flex flex-col items-end gap-1"><HealthBadge h={i.health} />{i.confidence === 'Low' && <ConfBadge c="Low" />}</div></li>))}</ul></div>
      <div><h4 className="mb-1 font-semibold">Connected routes</h4>
        <ul className="space-y-1">{d.routes.map((r: any) => <li key={r.id} className="flex items-center justify-between rounded-lg border border-line px-3 py-1.5"><Link to={`/app/routes?route=${r.id}`} className="font-medium text-deep hover:underline">{r.id} {r.a === n.id ? r.b : r.a}</Link><span className="flex items-center gap-2"><span className="num text-xs text-muted">{r.rri === null ? '—' : `RRI ${r.rri.toFixed(2)}`}</span><RiskBadge r={r.risk} /></span></li>)}</ul></div>
      {d.inbound.length > 0 && <div><h4 className="mb-1 font-semibold">Inbound (simulated)</h4>{d.inbound.map((c: any) => <div key={c.id} className="flex items-center justify-between rounded-lg border border-line px-3 py-1.5"><span className="flex items-center gap-1.5"><Truck className="h-3.5 w-3.5 text-lilac" aria-hidden />{c.id} · {fmt(c.qty)} {c.unit} {SUPPLY_LABEL[c.supply_class]}</span><span className="flex items-center gap-2 text-xs text-muted">ETA {fmtDateTime(c.est_eta)}<StatusBadge s={c.status} /></span></div>)}</div>}
      {d.recommendations.length > 0 && <div><h4 className="mb-1 font-semibold">Recommendations</h4>{d.recommendations.map((r: any) => <Link key={r.id} to={`/app/recommendations?open=${r.id}`} className="mb-1 flex items-center justify-between rounded-lg border border-line px-3 py-1.5 hover:bg-lilac-soft"><span>{r.id} · {fmt(r.qty)} {r.unit} {SUPPLY_LABEL[r.supply_class]}</span><span className="flex gap-1"><UrgBadge u={r.urgency} /><StatusBadge s={r.status} /></span></Link>)}</div>}
      <div><h4 className="mb-1 font-semibold">Sensors</h4><ul className="space-y-1">{d.sensors.map((x: any) => <li key={x.id} className="flex items-center justify-between text-xs"><span className="flex items-center gap-1.5"><Radio className="h-3.5 w-3.5 text-lilac" aria-hidden />{x.id} · {x.kind}</span><span className="flex items-center gap-2 text-muted">{x.battery_pct}%<Badge tone={x.health === 'ok' ? 'ok' : x.health === 'degraded' ? 'warn' : 'crit'}>{x.health}</Badge></span></li>)}</ul></div>
      <div className="flex gap-2"><Link to={`/app/forecasts?post=${n.id}`} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-deep hover:bg-lilac-soft">Open forecast</Link><Link to={`/app/inventory?post=${n.id}`} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-deep hover:bg-lilac-soft">Open inventory</Link></div>
    </div>
  )
}
