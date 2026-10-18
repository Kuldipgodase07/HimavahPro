import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, ClipboardCheck, CloudOff, MapPin, Route as RouteIcon, TrendingDown, TrendingUp, Triangle, Zap } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi } from '../lib/useApi'
import { useAuth } from '../lib/auth'
import { Async, Badge, Card, ConfBadge, HealthBadge, Kpi, PageHeader, RiskBadge, Select, SimBanner, StatusBadge, UrgBadge } from '../components/ui'
import { MapLegend, SynthMap, type MapLayers } from '../components/SynthMap'
import { PostPanel } from '../components/PostPanel'
import { filterNodes, useMapFilters } from './LogisticsMap'
import { CHART, HEALTH_COLOR, RISK_COLOR, SUPPLY_LABEL, ago, fmt, fmtDateTime } from '../lib/format'

export default function CommandCentre() {
  const s = useApi<any>('/api/dashboard'); const m = useApi<any>('/api/map')
  const { can } = useAuth()
  return (
    <>
      <PageHeader title="Command Centre" sub="Simulated Landslide Disruption scenario ready · all values come from synthetic demo data" actions={can('sim.run') ? <Link to="/app/simulator" className="inline-flex items-center gap-1.5 rounded-lg bg-deep px-3.5 py-2 text-[13px] font-medium text-white hover:bg-deep-2"><Zap className="h-4 w-4" aria-hidden />Run landslide scenario</Link> : undefined} />
      <div className="mb-4"><SimBanner /></div>
      <Async state={s}>{(d) => <Body d={d} map={m.data} />}</Async>
    </>
  )
}

function Body({ d, map }: { d: any; map: any }) {
  const k = d.kpis; const nav = useNavigate()
  const [f, setF] = useMapFilters(); const [sel, setSel] = useState<string | null>(null)
  const [layers] = useState<MapLayers>({ routes: true, air: true, weather: false, terrain: false, labels: true })
  const nodes = useMemo(() => (map ? filterNodes(map.nodes, f) : []), [map, f])
  const routes = useMemo(() => (map?.routes ?? []).filter((r: any) => !f.route || (f.route === 'closed' ? r.closed : r.risk === f.route)), [map, f.route])
  const riskData = Object.entries(d.charts.route_risk).map(([name, value]) => ({ name, value: value as number }))
  const demand = d.charts.demand_forecast
  const firstFc = demand.findIndex((x: any) => x.forecast)
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi icon={<MapPin />} label="Active simulated posts" value={k.active_posts} sub="Fictional network" />
        <Kpi icon={<AlertTriangle />} label="Posts requiring attention" value={k.posts_attention} tone={k.posts_attention ? 'warn' : undefined} sub="Any class below 7 days" />
        <Kpi icon={<TrendingDown />} label="Critical stock alerts" value={k.critical_alerts} tone={k.critical_alerts ? 'crit' : undefined} sub="Under 3 days of supply" />
        <Kpi icon={<RouteIcon />} label="Routes at elevated risk" value={`${k.routes_elevated}/${k.routes_total}`} tone={k.routes_elevated ? 'warn' : undefined} sub="Includes closed segments" />
        <Kpi icon={<ClipboardCheck />} label="Pending approvals" value={k.pending_approvals} sub={<Link to="/app/recommendations" className="text-deep hover:underline">Review now</Link>} />
        <Kpi icon={k.sync.label === 'Synchronised' ? <CheckCircle2 /> : <CloudOff />} label="Data synchronisation" value={<span className="text-lg">{k.sync.label}</span>} tone={k.sync.label === 'Synchronised' ? 'ok' : 'warn'} sub={`${k.sync.sources_ok}/${k.sync.sources_total} fresh · ${k.sync.sensors_unhealthy} sensor issue(s)`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <Card title="Logistics map" sub="Markers show worst stock health; lines show route reliability" action={<Link to="/app/map" className="text-xs font-medium text-deep hover:underline">Open full map</Link>} pad={false}>
          <div className="flex flex-wrap gap-2 border-b border-line p-3">
            <Select aria-label="Supply class" value={f.cls} onChange={(e) => setF({ ...f, cls: e.target.value })} className="w-auto"><option value="">All supply classes</option>{Object.entries(SUPPLY_LABEL).map(([a, b]) => <option key={a} value={a}>{b}</option>)}</Select>
            <Select aria-label="Stock health" value={f.health} onChange={(e) => setF({ ...f, health: e.target.value })} className="w-auto"><option value="">All stock health</option>{['healthy', 'attention', 'elevated', 'critical'].map((h) => <option key={h} value={h}>{h}</option>)}</Select>
            <Select aria-label="Route status" value={f.route} onChange={(e) => setF({ ...f, route: e.target.value })} className="w-auto"><option value="">All route status</option>{['low', 'moderate', 'elevated', 'high', 'closed'].map((h) => <option key={h} value={h}>{h}</option>)}</Select>
            <Select aria-label="Forecast horizon" value={f.horizon} onChange={(e) => setF({ ...f, horizon: e.target.value })} className="w-auto"><option value="1">24 h horizon</option><option value="3">72 h horizon</option><option value="7">7 d horizon</option></Select>
          </div>
          <div className="grid lg:grid-cols-[1fr_300px]">
            <div className="p-3">{map ? <SynthMap nodes={nodes} routes={routes} selected={sel} onSelect={setSel} layers={layers} className="h-[420px]" /> : <div className="skeleton h-[420px]" />}<div className="mt-2"><MapLegend /></div></div>
            <div className="max-h-[480px] overflow-auto border-t border-line p-4 lg:border-l lg:border-t-0">{sel ? <PostPanel postId={sel} /> : <div className="text-[13px] text-muted"><p className="font-medium text-gray">Selected post</p><p className="mt-1">Select a marker to see inventory health, connected routes, inbound movements and recommendations.</p>
              <p className="mt-3 text-xs">Forecast horizon filter ({f.horizon === '1' ? '24 h' : f.horizon === '3' ? '72 h' : '7 d'}) applies to the forecast workspace links.</p></div>}</div>
          </div>
        </Card>

        <div className="space-y-4">
          <Card title="Critical alerts" action={<Badge tone="crit">{d.alerts.length}</Badge>} pad={false}>
            <ul className="max-h-60 divide-y divide-line overflow-auto">{d.alerts.length === 0 && <li className="p-4 text-sm text-muted">No critical or elevated stock alerts.</li>}
              {d.alerts.map((a: any, i: number) => <li key={i}><button onClick={() => nav(`/app/forecasts?post=${a.post_id}&cls=${a.supply_class}`)} className="flex w-full items-start justify-between gap-2 px-4 py-2.5 text-left hover:bg-lilac-soft/60"><span><span className="block text-[13px] font-semibold">{a.post_id} · {SUPPLY_LABEL[a.supply_class]}</span><span className="block text-xs text-muted">{a.message}</span></span><HealthBadge h={a.severity} /></button></li>)}</ul></Card>
          <Card title="Recommendations requiring approval" action={<Link to="/app/recommendations" className="text-xs font-medium text-deep hover:underline">All</Link>} pad={false}>
            <ul className="divide-y divide-line">{d.pending_recommendations.length === 0 && <li className="p-4 text-sm text-muted">Nothing is waiting for review.</li>}
              {d.pending_recommendations.map((r: any) => <li key={r.id}><Link to={`/app/recommendations?open=${r.id}`} className="flex items-center justify-between gap-2 px-4 py-2.5 hover:bg-lilac-soft/60"><span><span className="block text-[13px] font-semibold">{r.id} · {r.post_id}</span><span className="num block text-xs text-muted">{fmt(r.qty)} {r.unit} {SUPPLY_LABEL[r.supply_class]} · {r.transport_mode}</span></span><span className="flex flex-col items-end gap-1"><UrgBadge u={r.urgency} />{r.mandatory_review && <Badge tone="crit">Mandatory review</Badge>}</span></Link></li>)}</ul></Card>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Forecast changes" sub="Mean daily demand vs 3 days ago (simulated model)" pad={false}>
          <ul className="divide-y divide-line">{d.forecast_changes.map((c: any, i: number) => <li key={i}><Link to={`/app/forecasts?post=${c.post_id}&cls=${c.supply_class}`} className="flex items-center justify-between px-4 py-2.5 hover:bg-lilac-soft/60"><span className="text-[13px] font-medium">{c.post_id} · {SUPPLY_LABEL[c.supply_class]}</span><span className={`num flex items-center gap-1 text-[13px] font-semibold ${c.change_pct > 0 ? 'text-orange-ink' : 'text-ok-ink'}`}>{c.change_pct > 0 ? <TrendingUp className="h-3.5 w-3.5" aria-hidden /> : <TrendingDown className="h-3.5 w-3.5" aria-hidden />}{c.change_pct > 0 ? '+' : ''}{c.change_pct}%</span></Link></li>)}</ul></Card>
        <Card title="Route disruptions" action={<Link to="/app/routes" className="text-xs font-medium text-deep hover:underline">Route intelligence</Link>} pad={false}>
          <ul className="divide-y divide-line">{d.route_disruptions.length === 0 && <li className="p-4 text-sm text-muted">No elevated-risk routes.</li>}{d.route_disruptions.map((r: any) => <li key={r.id}><Link to={`/app/routes?route=${r.id}`} className="flex items-center justify-between px-4 py-2.5 hover:bg-lilac-soft/60"><span><span className="block text-[13px] font-semibold">{r.id} · {r.a} ↔ {r.b}</span><span className="num block text-xs text-muted">{r.closed ? `Closed: ${r.closure_reason ?? 'simulated'}` : `RRI ${r.rri?.toFixed(2)} · ${r.time_h} h`}</span></span><RiskBadge r={r.risk} /></Link></li>)}</ul></Card>
        <Card title="Data quality & low-confidence" action={<Badge tone="warn">{d.data_quality_total}</Badge>} pad={false}>
          <ul className="max-h-72 divide-y divide-line overflow-auto">{d.data_quality.length === 0 && <li className="p-4 text-sm text-muted">No data-quality warnings.</li>}{d.data_quality.map((q: any, i: number) => <li key={i} className="px-4 py-2.5"><div className="flex items-center justify-between"><span className="text-[13px] font-semibold">{q.post_id} · {SUPPLY_LABEL[q.supply_class]}</span><ConfBadge c={q.confidence} /></div><p className="text-xs text-muted">{q.issues.join(' · ')}</p></li>)}</ul></Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Stock-health trend" sub={d.charts.trend_note}>
          <div className="h-60" role="img" aria-label="Stacked area chart of stock-health counts over 14 days"><ResponsiveContainer><AreaChart data={d.charts.stock_health_trend}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} fontSize={11} /><YAxis fontSize={11} width={28} /><Tooltip /><Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
            {(['healthy', 'attention', 'elevated', 'critical'] as const).map((h) => <Area key={h} isAnimationActive={false} type="monotone" stackId="1" dataKey={h} name={h[0].toUpperCase() + h.slice(1)} stroke={HEALTH_COLOR[h]} fill={HEALTH_COLOR[h]} fillOpacity={0.75} />)}</AreaChart></ResponsiveContainer></div></Card>
        <Card title="Demand forecast" sub="Index vs 14-day average = 100 · forecast to the right of the line (simulated, P50)">
          <div className="h-60" role="img" aria-label="Line chart of demand index by supply class, history and forecast"><ResponsiveContainer><LineChart data={demand}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} fontSize={11} /><YAxis fontSize={11} width={32} domain={['auto', 'auto']} /><Tooltip /><Legend iconType="plainline" wrapperStyle={{ fontSize: 11 }} />
            {firstFc > 0 && <ReferenceLine x={demand[firstFc].date} stroke="#999" strokeDasharray="4 3" label={{ value: 'Forecast', fontSize: 10, fill: '#6b6c75', position: 'insideTopRight' }} />}
            {([['rations', CHART.purple], ['fuel', CHART.teal], ['medical', CHART.blue], ['spares', CHART.lilac]] as const).map(([key, c]) => <Line key={key} dataKey={key} name={SUPPLY_LABEL[key]} stroke={c} dot={false} strokeWidth={2} />)}</LineChart></ResponsiveContainer></div></Card>
        <Card title="Route-risk distribution" sub="Road segments by Route Reliability class">
          <div className="h-52" role="img" aria-label="Bar chart of road segments by risk class"><ResponsiveContainer><BarChart data={riskData} layout="vertical" margin={{ left: 8 }}><CartesianGrid stroke={CHART.grid} horizontal={false} /><XAxis type="number" allowDecimals={false} fontSize={11} /><YAxis type="category" dataKey="name" fontSize={11} width={70} tickFormatter={(v) => v[0].toUpperCase() + v.slice(1)} /><Tooltip /><Bar dataKey="value" name="Segments" radius={[0, 4, 4, 0]}>{riskData.map((r) => <Cell key={r.name} fill={RISK_COLOR[r.name]} />)}</Bar></BarChart></ResponsiveContainer></div></Card>
        <Card title="Recent decisions & approvals" pad={false}>
          <ul className="max-h-56 divide-y divide-line overflow-auto">{d.recent_decisions.map((x: any, i: number) => <li key={i} className="flex items-start justify-between gap-2 px-4 py-2"><span><span className="block text-[13px] font-medium">{x.rec_id} · {x.action}</span><span className="block text-xs text-muted">{x.actor} · {fmtDateTime(x.ts)}</span>{x.reason && <span className="block text-xs text-gray">“{x.reason}”</span>}</span><StatusBadge s={x.to} /></li>)}</ul></Card>
      </div>
      <p className="text-center text-[11px] text-muted">Data as of {ago(d.as_of)} · Models: simulated statistical forecaster and rule-based route reliability. Not operational intelligence.</p>
    </div>
  )
}
