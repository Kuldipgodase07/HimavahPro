import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FlaskConical, RotateCcw } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Async, Badge, Button, Card, DataTable, Empty, Field, Input, PageHeader, Select, SimBanner, useToast, type Col } from '../components/ui'
import { CHART, SUPPLY_LABEL } from '../lib/format'

export default function Simulator() {
  const meta = useApi<any>('/api/simulations/kinds'); const runs = useApi<any>('/api/simulations/runs')
  return (
    <>
      <PageHeader title="What-if Logistics Simulator" sub="Test disruptions on an in-memory copy of the network. Nothing here changes live stock, routes or convoys." />
      <Async state={meta}>{(m) => <Body m={m} runs={runs} />}</Async>
    </>
  )
}

function Body({ m, runs }: { m: any; runs: any }) {
  const toast = useToast(); const { can } = useAuth(); const nav = useNavigate()
  const [kind, setKind] = useState('route_closure'); const [p, setP] = useState<any>({ route_id: m.demo.landslide_route_id, days: 3, pct: 25, supply_class: 'all', hours: 24, convoy_id: '', post_id: 'POST-K04', route_ids: [m.demo.landslide_route_id], rain_mm: 60, snow_cm: 30 })
  const [res, setRes] = useState<any>(null); const [prev, setPrev] = useState<any>(null); const [busy, setBusy] = useState(false); const [err, setErr] = useState(''); const [compare, setCompare] = useState(false)
  const [sel, setSel] = useState<string | null>(null)
  const set = (k: string, v: any) => setP({ ...p, [k]: v })
  const roadRoutes = m.routes.filter((r: any) => r.mode === 'road')
  async function run() {
    setBusy(true); setErr('')
    const params = kind === 'route_closure' ? { route_id: p.route_id, days: Number(p.days) } : kind === 'demand_surge' ? { pct: Number(p.pct), supply_class: p.supply_class } : kind === 'delivery_delay' ? { hours: Number(p.hours), convoy_id: p.convoy_id || null } : kind === 'sensor_outage' ? { post_id: p.post_id, hours: 48 } : { route_ids: p.route_ids, rain_mm: Number(p.rain_mm), snow_cm: Number(p.snow_cm), days: 2 }
    try { const r = await api('/api/simulations/run', { method: 'POST', body: { kind, params } }); setPrev(res); setRes(r); setSel(r.posts.find((x: any) => x.affected)?.post_id ?? r.posts[0]?.post_id ?? null); runs.reload(); toast('success', `Scenario ${r.run_id} complete. Logged to the audit trail.`) }
    catch (e) { setErr(e instanceof ApiError ? e.message : 'Scenario failed') } finally { setBusy(false) }
  }
  const reset = () => { setRes(null); setPrev(null); setErr(''); setCompare(false) }
  async function drafts() {
    try { const r = await api(`/api/simulations/${res.run_id}/drafts`, { method: 'POST' }); toast('success', `${r.created.filter((c: any) => c.id).length} draft recommendation(s) created. Review them in the inbox.`); nav('/app/recommendations') } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Failed') }
  }
  const demoClick = () => { setKind('route_closure'); setP({ ...p, route_id: m.demo.landslide_route_id, days: 3 }) }
  const selPost = res?.posts.find((x: any) => x.post_id === sel)
  return (
    <div className="space-y-4">
      <SimBanner>{m.banner}</SimBanner>
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card title="Scenario" action={<Badge tone="purple" icon={false}>{m.demo.scenario_name}</Badge>}>
          <div className="space-y-3">
            <Field label="Scenario type">{(i) => <Select id={i} value={kind} onChange={(e) => { setKind(e.target.value); setErr('') }}>{m.kinds.map((k: any) => <option key={k.id} value={k.id}>{k.label}</option>)}</Select>}</Field>
            {kind === 'route_closure' && <><Field label="Route">{(i) => <Select id={i} value={p.route_id} onChange={(e) => set('route_id', e.target.value)}>{roadRoutes.map((r: any) => <option key={r.id} value={r.id}>{r.label}{r.id === m.demo.landslide_route_id ? ' (landslide)' : ''}</option>)}</Select>}</Field><Field label="Unavailable for (days)">{(i) => <Input id={i} type="number" min={0.5} max={30} step={0.5} value={p.days} onChange={(e) => set('days', e.target.value)} />}</Field></>}
            {kind === 'demand_surge' && <><Field label={`Demand increase: ${p.pct}%`}>{(i) => <input id={i} type="range" min={5} max={100} value={p.pct} onChange={(e) => set('pct', e.target.value)} className="w-full accent-[#351A55]" />}</Field><Field label="Supply class">{(i) => <Select id={i} value={p.supply_class} onChange={(e) => set('supply_class', e.target.value)}><option value="all">All classes</option>{Object.entries(SUPPLY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}</Field></>}
            {kind === 'delivery_delay' && <><Field label="Convoy">{(i) => <Select id={i} value={p.convoy_id} onChange={(e) => set('convoy_id', e.target.value)}><option value="">All active convoys</option>{m.convoys.map((c: string) => <option key={c}>{c}</option>)}</Select>}</Field><Field label="Delay (hours)">{(i) => <Input id={i} type="number" min={1} max={240} value={p.hours} onChange={(e) => set('hours', e.target.value)} />}</Field></>}
            {kind === 'sensor_outage' && <Field label="Post with sensor outage">{(i) => <Select id={i} value={p.post_id} onChange={(e) => set('post_id', e.target.value)}>{m.posts.map((x: any) => <option key={x.id} value={x.id}>{x.id} {x.name}</option>)}</Select>}</Field>}
            {kind === 'weather_disruption' && <><Field label="Affected routes (hold Ctrl/Cmd for several)">{(i) => <select id={i} multiple size={5} value={p.route_ids} onChange={(e) => set('route_ids', [...e.target.selectedOptions].map((o) => o.value))} className="w-full rounded-lg border border-line bg-white px-2 py-1 text-[13px]">{roadRoutes.map((r: any) => <option key={r.id} value={r.id}>{r.label}</option>)}</select>}</Field><div className="grid grid-cols-2 gap-2"><Field label="Rain (mm)">{(i) => <Input id={i} type="number" min={0} max={300} value={p.rain_mm} onChange={(e) => set('rain_mm', e.target.value)} />}</Field><Field label="Snow (cm)">{(i) => <Input id={i} type="number" min={0} max={200} value={p.snow_cm} onChange={(e) => set('snow_cm', e.target.value)} />}</Field></div></>}
            {err && <p role="alert" className="text-sm font-medium text-crit-ink">{err}</p>}
            {!m.can_run && <p className="rounded-lg bg-[#eceef3] p-2 text-xs text-muted">Your role can view scenarios but not run them.</p>}
            <div className="flex flex-wrap gap-2"><Button variant="primary" loading={busy} disabled={!m.can_run} onClick={run}><FlaskConical className="h-4 w-4" aria-hidden />Run scenario</Button><Button onClick={reset}><RotateCcw className="h-4 w-4" aria-hidden />Reset Scenario</Button>{prev && <Button onClick={() => setCompare(!compare)} aria-pressed={compare}>Compare Results</Button>}</div>
            <button onClick={demoClick} className="text-xs font-medium text-deep underline">Load “Simulated Landslide Disruption” (3-day closure)</button>
          </div>
        </Card>
        <div className="space-y-4">
          {!res ? <Card><Empty title="No scenario run yet" hint="Choose a scenario and press Run. Results compare the baseline with the simulated outcome." /></Card> : <Results res={res} prev={prev} compare={compare} sel={sel} setSel={setSel} selPost={selPost} onDrafts={can('recs.create') ? drafts : undefined} />}
          <Card title="Recent scenario runs" pad={false}><DataTable rowKey={(r: any) => r.id} cols={[{ key: 'id', label: 'Run' }, { key: 'kind', label: 'Type', render: (r: any) => m.kinds.find((k: any) => k.id === r.kind)?.label }, { key: 'actor', label: 'Run by' }, { key: 'aff', label: 'Posts affected', align: 'right', render: (r: any) => r.summary.affected }] as Col<any>[]} rows={runs.data?.items ?? []} empty={<p className="p-4 text-sm text-muted">No runs recorded.</p>} /></Card>
        </div>
      </div>
    </div>
  )
}

function Results({ res, prev, compare, sel, setSel, selPost, onDrafts }: any) {
  const s = res.summary
  const chart = res.chart.days.map((d: number, i: number) => ({ day: d, baseline: res.chart.baseline_in_stockout[i], scenario: res.chart.scenario_in_stockout[i], ...(compare && prev ? { previous: prev.chart.scenario_in_stockout[i] } : {}) }))
  const affected = res.posts.filter((x: any) => x.affected)
  const series = selPost?.series ?? []
  const [cls, setCls] = useState<string>('')
  useEffect(() => setCls(selPost?.worst_class ?? ''), [selPost?.post_id])
  const one = series.find((x: any) => x.supply_class === cls) ?? series[0]
  const line = one ? one.baseline.series.map((v: number, i: number) => ({ day: i, baseline: v, scenario: one.scenario.series[i] })) : []
  return (
    <>
      <Card title={`${res.label} · ${res.run_id}`} action={onDrafts && s.scenario_stockout_series > 0 ? <Button size="sm" variant="primary" onClick={onDrafts}>Create draft recommendations</Button> : undefined}>
        <ul className="mb-3 list-disc space-y-1 pl-4 text-[13px] text-gray">{res.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[['Posts affected', s.posts_affected], ['Stockout risks (baseline)', s.baseline_stockout_series], ['Stockout risks (scenario)', s.scenario_stockout_series], ['New stockout risks', s.new_stockout_series]].map(([k, v]: any) => <div key={k} className="rounded-xl border border-line p-3"><div className="text-xs text-muted">{k}</div><div className={`num text-2xl font-bold ${k === 'New stockout risks' && v > 0 ? 'text-crit-ink' : ''}`}>{v}</div></div>)}</div>
        {res.convoy_effects.length > 0 && <p className="mt-3 text-[13px]"><b>Convoy effects:</b> {res.convoy_effects.map((c: any) => `${c.convoy} → ${c.post} +${c.delay_h} h`).join(' · ')}</p>}
      </Card>
      <Card title="Before and after" sub="Count of post/supply series projected below zero stock, by day (14-day horizon)">
        <div className="h-56" role="img" aria-label="Number of series in stockout by day, baseline versus scenario"><ResponsiveContainer><LineChart data={chart}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="day" fontSize={11} unit="d" /><YAxis allowDecimals={false} fontSize={11} width={28} /><Tooltip /><Legend iconType="plainline" wrapperStyle={{ fontSize: 11 }} /><Line dataKey="baseline" name="Baseline" stroke="#6b6c75" strokeDasharray="5 4" dot={false} strokeWidth={2} /><Line dataKey="scenario" name="This scenario" stroke={CHART.purple} strokeWidth={2.5} dot={false} />{compare && prev && <Line dataKey="previous" name="Previous run" stroke={CHART.teal} dot={false} strokeWidth={2} />}</LineChart></ResponsiveContainer></div>
        {compare && !prev && <p className="text-xs text-muted">Run a second scenario to compare with the first.</p>}
      </Card>
      <Card title="Affected posts" pad={false}>
        {affected.length === 0 ? <p className="p-4 text-sm text-muted">No posts are materially affected in this scenario.</p> : <DataTable rowKey={(r: any) => r.post_id} onRow={(r) => setSel(r.post_id)} cols={[{ key: 'post_id', label: 'Post', render: (r: any) => <><b>{r.post_id}</b><div className="text-[11px] text-muted">{r.post_name}</div></> }, { key: 'w', label: 'Worst class', render: (r: any) => SUPPLY_LABEL[r.worst_class] }, { key: 'b', label: 'Days to stockout (baseline)', align: 'right', render: (r: any) => r.projected_dos_baseline ?? '>14' }, { key: 's', label: 'Days to stockout (scenario)', align: 'right', render: (r: any) => <b className={r.stockout_risk ? 'text-crit-ink' : ''}>{r.projected_dos_scenario ?? '>14'}</b> }, { key: 'r', label: 'Risk', render: (r: any) => (r.stockout_risk ? <Badge tone="crit">Stockout risk</Badge> : <Badge tone="warn">Reduced buffer</Badge>) }] as Col<any>[]} rows={affected} />}
      </Card>
      {selPost && one && <Card title={`${selPost.post_id} · projected stock`} action={<Select aria-label="Supply class" className="w-auto" value={cls} onChange={(e) => setCls(e.target.value)}>{series.map((x: any) => <option key={x.supply_class} value={x.supply_class}>{SUPPLY_LABEL[x.supply_class]}</option>)}</Select>}>
        <div className="h-52" role="img" aria-label="Projected stock, baseline versus scenario"><ResponsiveContainer><AreaChart data={line}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="day" fontSize={11} unit="d" /><YAxis fontSize={11} width={48} /><Tooltip /><Legend iconType="plainline" wrapperStyle={{ fontSize: 11 }} /><ReferenceLine y={0} stroke="#D64545" /><Area dataKey="baseline" name={`Baseline (${one.unit})`} stroke="#6b6c75" fill="#6b6c75" fillOpacity={0.1} /><Area dataKey="scenario" name="Scenario" stroke={CHART.purple} fill={CHART.lilac} fillOpacity={0.3} /></AreaChart></ResponsiveContainer></div>
        <div className="mt-2 grid gap-2 text-[13px] md:grid-cols-2"><div><b>Confidence:</b> {one.confidence}{one.suggested_qty && <> · <b>Replenishment suggested:</b> <span className="num">{one.suggested_qty} {one.unit}</span></>}</div>
          <div>{selPost.alternatives?.length ? <><b>Alternative routes:</b><ul className="list-disc pl-4 text-xs text-gray">{selPost.alternatives.map((a: any, i: number) => <li key={i}>{a.label}: {a.time_h} h, {(a.reliability * 100).toFixed(0)}% reliable</li>)}</ul></> : <span className="text-muted">No alternative route data for this post.</span>}</div></div>
      </Card>}
      <Card title="Confidence limitations"><ul className="list-disc space-y-1 pl-4 text-[13px] text-gray">{res.limitations.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul></Card>
    </>
  )
}
