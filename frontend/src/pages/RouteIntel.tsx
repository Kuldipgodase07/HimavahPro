import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CloudRain, Mountain, Search, Snowflake } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Async, Badge, Button, Card, Confirm, DataTable, Field, Input, Kv, PageHeader, RiskBadge, Select, SimBanner, Skeleton, useToast, type Col } from '../components/ui'
import { CHART, fmtDateTime, fmt } from '../lib/format'

export default function RouteIntel() {
  const [sp, setSp] = useSearchParams(); const sel = sp.get('route')
  const [q, setQ] = useState(''); const [risk, setRisk] = useState('')
  const s = useApi<any>(`/api/routes?q=${encodeURIComponent(q)}&risk=${risk}&mode=`)
  const cols: Col<any>[] = [
    { key: 'id', label: 'Route', render: (r) => <><b>{r.id}</b><div className="text-[11px] text-muted">{r.a_name} ↔ {r.b_name}</div></> },
    { key: 'mode', label: 'Mode', render: (r) => <span className="capitalize">{r.mode}</span> },
    { key: 'time_h', label: 'Travel time', align: 'right', render: (r) => `${r.time_h} h` },
    { key: 'rri', label: 'Reliability (RRI)', align: 'right', render: (r) => (r.rri === null ? '—' : `${(r.rri * 100).toFixed(0)}%`) },
    { key: 'risk', label: 'Risk', render: (r) => <RiskBadge r={r.risk} /> },
    { key: 'slope_risk', label: 'Slope', align: 'right', render: (r) => r.slope_risk.toFixed(2) },
    { key: 'closure_count', label: 'Past closures', align: 'right' },
  ]
  return (
    <>
      <PageHeader title="Route Intelligence" sub="Route Reliability Index, terrain and weather scenarios, fastest vs most reliable" />
      <div className="mb-4"><SimBanner>Rule-based reliability formula on synthetic terrain and weather. A high score is not an operational safety clearance.</SimBanner></div>
      <div className="grid gap-4 xl:grid-cols-[1fr_460px]">
        <Card pad={false}>
          <div className="flex flex-wrap gap-2 border-b border-line p-3"><label className="relative min-w-[180px] flex-1"><span className="sr-only">Search routes</span><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden /><Input className="pl-9" placeholder="Search route or node" value={q} onChange={(e) => setQ(e.target.value)} /></label>
            <Select aria-label="Risk" className="w-auto" value={risk} onChange={(e) => setRisk(e.target.value)}><option value="">All risk</option>{['low', 'moderate', 'elevated', 'high', 'closed'].map((r) => <option key={r} value={r}>{r}</option>)}</Select></div>
          <Async state={s}>{(d) => <DataTable rowKey={(r) => r.id} cols={cols} rows={d.items} onRow={(r) => setSp({ route: r.id })} empty={<div className="py-10 text-center text-sm text-muted">No routes match.</div>} />}</Async>
        </Card>
        <div>{sel ? <Detail id={sel} onChanged={() => s.reload()} /> : <Card title="Route analysis"><p className="text-sm text-muted">Select a route to see its explanation, weather scenario inputs and alternative paths.</p></Card>}</div>
      </div>
    </>
  )
}

function Detail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { can } = useAuth(); const toast = useToast()
  const [rain, setRain] = useState<string>(''); const [snow, setSnow] = useState<string>('')
  const url = `/api/routes/${id}${rain !== '' || snow !== '' ? `?${new URLSearchParams({ ...(rain !== '' ? { rain } : {}), ...(snow !== '' ? { snow } : {}) })}` : ''}`
  const d = useApi<any>(url, [id, rain, snow])
  const [closing, setClosing] = useState(false); const [days, setDays] = useState('3'); const [busy, setBusy] = useState(false)
  async function act(close: boolean) {
    setBusy(true)
    try { const r = await api(`/api/routes/${id}/${close ? 'closure' : 'reopen'}`, { method: 'POST', body: close ? { days: Number(days), reason: 'Simulated landslide' } : undefined }); toast('success', close ? `${id} closed for ${days} day(s) (simulated). ${r.convoy_changes.length} convoy(s) re-planned, ${r.recommendation_changes.length} recommendation(s) updated.` : `${id} reopened.`); setClosing(false); d.reload(); onChanged() }
    catch (e) { toast('error', e instanceof ApiError ? e.message : 'Failed') } finally { setBusy(false) }
  }
  if (d.error && !d.data) return <Async state={d}>{() => null}</Async>
  if (!d.data) return <Skeleton className="h-96" />
  const x = d.data, a = x.assessment, sc = x.scenario, r = x.route
  const contrib = Object.entries(a.contributions).filter(([k]) => k !== 'intercept').map(([k, v]) => ({ k: ({ rain_mm: 'Rainfall', snow_cm: 'Snowfall', slope_risk: 'Slope', closure_count: 'Closure history' } as any)[k] ?? k, v: v as number }))
  const rows = x.comparison ? [['Fastest', x.comparison.fastest], ['Most reliable', x.comparison.reliable], ['Avoiding this segment', x.comparison.avoiding_this_segment]] : []
  return (
    <Card title={`${r.id} · ${x.a_name} ↔ ${x.b_name}`} action={<RiskBadge r={r.risk} />}>
      <div className="space-y-4 text-[13px]">
        <div className="grid grid-cols-3 gap-2 text-center"><div className="rounded-lg bg-lilac-soft p-2"><div className="text-[11px] text-muted">Reliability</div><div className="num text-xl font-bold text-deep">{a.rri === null ? '—' : `${(a.rri * 100).toFixed(0)}%`}</div></div><div className="rounded-lg bg-lilac-soft p-2"><div className="text-[11px] text-muted">Travel time</div><div className="num text-xl font-bold text-deep">{a.time_h} h</div></div><div className="rounded-lg bg-lilac-soft p-2"><div className="text-[11px] text-muted">Distance</div><div className="num text-xl font-bold text-deep">{r.distance_km} km</div></div></div>
        {r.closed && <div role="status" className="rounded-lg bg-[#eceef3] p-2 text-gray"><b>Closed</b> until {fmtDateTime(r.closed_until)} · {r.closure_reason} (simulated)</div>}
        <p>{a.explanation}</p>
        <div className="h-32" role="img" aria-label="Contribution of each factor to the reliability score"><ResponsiveContainer><BarChart data={contrib} layout="vertical" margin={{ left: 20 }}><CartesianGrid stroke={CHART.grid} horizontal={false} /><XAxis type="number" fontSize={10} /><YAxis type="category" dataKey="k" fontSize={11} width={95} /><Tooltip formatter={(v: any) => Number(v).toFixed(2)} /><Bar dataKey="v" name="Score contribution" fill={CHART.lilac} radius={[0, 3, 3, 0]} /></BarChart></ResponsiveContainer></div>
        <p className="-mt-2 text-[11px] text-muted">Logit contributions in the rule-based formula (negative = lowers reliability). Not SHAP.</p>
        <div><div className="mb-1 flex items-center gap-1.5 font-semibold"><CloudRain className="h-4 w-4 text-teal" aria-hidden />Weather scenario <span className="font-normal text-muted">(what-if, not saved)</span></div>
          <div className="grid grid-cols-2 gap-2"><Field label={`Rainfall mm (now ${r.rain_mm})`}>{(i) => <Input id={i} type="number" min={0} max={300} value={rain} onChange={(e) => setRain(e.target.value)} placeholder={String(r.rain_mm)} />}</Field><Field label={`Snowfall cm (now ${r.snow_cm})`}>{(i) => <Input id={i} type="number" min={0} max={200} value={snow} onChange={(e) => setSnow(e.target.value)} placeholder={String(r.snow_cm)} />}</Field></div>
          {sc && <div className="mt-2 rounded-lg border border-line p-2">Scenario: reliability <b className="num">{sc.rri === null ? '—' : `${(sc.rri * 100).toFixed(0)}%`}</b> ({sc.risk}) · {sc.time_h} h <span className="text-muted">(vs {a.rri === null ? '—' : `${(a.rri * 100).toFixed(0)}%`}, {a.time_h} h)</span> <button className="ml-2 text-xs font-medium text-deep underline" onClick={() => { setRain(''); setSnow('') }}>Reset</button></div>}</div>
        <div className="grid grid-cols-2 gap-x-4"><Kv k="Slope risk" v={<span className="flex items-center gap-1"><Mountain className="h-3.5 w-3.5" aria-hidden />{r.slope_risk.toFixed(2)}</span>} /><Kv k="Past closures (synthetic)" v={r.closure_count} /><Kv k="Rain / snow" v={<span className="flex items-center gap-1"><Snowflake className="h-3.5 w-3.5" aria-hidden />{r.rain_mm} mm / {r.snow_cm} cm</span>} /></div>
        {r.mode === 'road' && <div><h3 className="mb-1 font-semibold">Fastest vs more reliable alternative</h3>
          <table className="w-full text-left text-xs"><thead><tr className="text-muted"><th className="py-1">Option</th><th>Time</th><th>Reliability</th><th>Dist.</th><th>Fuel*</th></tr></thead><tbody>{rows.map(([n, p]: any) => <tr key={n} className="border-t border-line align-top"><td className="py-1.5 pr-2"><b>{n}</b><div className="text-muted">{p ? p.nodes.join(' → ') : 'No path'}</div></td><td className="num">{p ? `${p.time_h} h` : '—'}</td><td className="num">{p ? `${(p.reliability * 100).toFixed(0)}%` : '—'}</td><td className="num">{p ? `${p.distance_km} km` : '—'}</td><td className="num">{p ? `${fmt(p.fuel_l)} L` : '—'}</td></tr>)}</tbody></table>
          <p className="mt-1 text-[11px] text-muted">*Illustrative constant per km. Reliability = product of segment scores, assuming independence.</p></div>}
        {x.field_reports.length > 0 && <div><h3 className="mb-1 font-semibold">Field road-condition reports</h3>{x.field_reports.map((f: any, i: number) => <p key={i} className="text-xs text-gray">{fmtDateTime(f.ts)} · {f.actor}: <b>{f.condition}</b> {f.note}</p>)}</div>}
        <p className="rounded-lg bg-[#fff6d1] p-2 text-[11px] text-warn-ink">{x.caveat}</p>
        {x.can_close && (r.closed ? <Button onClick={() => act(false)} loading={busy}>Reopen route (simulated)</Button> : <Button variant="danger" onClick={() => setClosing(true)} disabled={r.mode !== 'road'}>Trigger simulated closure</Button>)}
        <Confirm open={closing} onClose={() => setClosing(false)} danger title={`Close ${id} (simulated)`} confirmLabel="Close route" loading={busy} onConfirm={() => act(true)} body={<><p>This marks the segment unavailable <b>inside the prototype only</b>. Active convoys will be re-planned and recommendations regenerated.</p><div className="mt-3 max-w-[160px]"><Field label="Duration (days)">{(i) => <Input id={i} type="number" min={0.5} max={30} step={0.5} value={days} onChange={(e) => setDays(e.target.value)} />}</Field></div></>} />
      </div>
    </Card>
  )
}
