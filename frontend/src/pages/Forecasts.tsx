import { useSearchParams } from 'react-router-dom'
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, Info } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { Async, Badge, Card, ConfBadge, DataTable, ErrorState, HealthBadge, Kv, PageHeader, Select, SimBanner, Skeleton } from '../components/ui'
import { CHART, SUPPLY_LABEL, fmt, fmtDateTime, fmtHours } from '../lib/format'

export default function Forecasts() {
  const [sp, setSp] = useSearchParams()
  const opts = useApi<any>('/api/forecast/options')
  const post = sp.get('post') ?? 'POST-K04', cls = sp.get('cls') ?? 'fuel', horizon = sp.get('h') ?? '3'
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }) }
  const f = useApi<any>(`/api/forecast?post=${post}&cls=${cls}&horizon=${horizon}`, [post, cls, horizon])
  return (
    <>
      <PageHeader title="Demand Forecasts" sub="Multi-horizon demand with P10 / P50 / P90 uncertainty" />
      <div className="mb-4"><SimBanner>Simulated statistical forecaster, not a trained deep-learning model. Synthetic consumption history.</SimBanner></div>
      <Card className="mb-4" pad={false}><div className="flex flex-wrap items-end gap-4 p-3">
        <label className="text-xs font-semibold text-gray">Simulated post<Select className="mt-1 w-56" value={post} onChange={(e) => set('post', e.target.value)}>{(opts.data?.posts ?? [{ id: post, name: '' }]).map((p: any) => <option key={p.id} value={p.id}>{p.id} {p.name}</option>)}</Select></label>
        <div><div className="mb-1 text-xs font-semibold text-gray" id="cls-l">Supply class</div><div role="radiogroup" aria-labelledby="cls-l" className="flex gap-1 rounded-lg bg-[#eceef3] p-1">{Object.entries(SUPPLY_LABEL).map(([k, v]) => <button key={k} role="radio" aria-checked={cls === k} onClick={() => set('cls', k)} className={`rounded-md px-3 py-1.5 text-[13px] font-medium ${cls === k ? 'bg-white text-deep shadow-sm' : 'text-gray'}`}>{v}</button>)}</div></div>
        <div><div className="mb-1 text-xs font-semibold text-gray" id="h-l">Forecast horizon</div><div role="radiogroup" aria-labelledby="h-l" className="flex gap-1 rounded-lg bg-[#eceef3] p-1">{[['1', '24 hours'], ['3', '72 hours'], ['7', '7 days']].map(([k, v]) => <button key={k} role="radio" aria-checked={horizon === k} onClick={() => set('h', k)} className={`rounded-md px-3 py-1.5 text-[13px] font-medium ${horizon === k ? 'bg-white text-deep shadow-sm' : 'text-gray'}`}>{v}</button>)}</div></div>
      </div></Card>
      {f.error && !f.data ? <ErrorState error={f.error} onRetry={f.reload} /> : !f.data ? <div className="space-y-3"><Skeleton className="h-24" /><Skeleton className="h-80" /></div> : <Detail d={f.data} />}
    </>
  )
}

function Detail({ d }: { d: any }) {
  const chart = [...d.history.map((h: any) => ({ date: h.date, actual: h.value })), ...d.forecast.map((x: any, i: number) => ({ date: x.date, p50: x.p50, band: [x.p10, x.p90], baseline: x.baseline, inHorizon: i < d.horizon_days }))]
  if (d.history.length && d.forecast.length) { const last = chart[d.history.length - 1]; last.p50 = last.actual }
  const show = chart.slice(0, d.history.length + d.horizon_days)
  const ht = d.horizon_totals
  return (
    <div className="space-y-4">
      {d.review_required && <div role="alert" className="flex items-start gap-2 rounded-xl border border-[#f0c4c4] bg-[#fbe3e3] p-3 text-sm text-crit-ink"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /><div><b>Human review required.</b> {d.review_message}</div></div>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[['Days of Supply', `${d.dos} d`, <HealthBadge key="h" h={d.health} />], ['Time-to-Stockout (P50)', fmtHours(d.tts.expected_h), <span key="r" className="text-[11px] text-muted">range {fmtHours(d.tts.earliest_h)} – {fmtHours(d.tts.latest_h)}</span>], ['Usable stock', `${fmt(d.usable)} ${d.unit}`, <span key="u" className="text-[11px] text-muted">{d.data.source} · {d.data.age_h} h old</span>], ['Forecast confidence', d.confidence, <ConfBadge key="c" c={d.confidence} />], ['Model', 'Simulated', <span key="m" className="text-[11px] text-muted">{d.model_version.split(' (')[0]}</span>]].map(([k, v, sub]: any) => <div key={k} className="rounded-xl border border-line bg-white p-3.5"><div className="text-xs font-medium text-muted">{k}</div><div className="num mt-0.5 text-2xl font-bold">{v}</div><div className="mt-0.5">{sub}</div></div>)}
      </div>
      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <Card title={`${SUPPLY_LABEL[d.supply_class]} consumption · ${d.post_id}`} sub={`Daily ${d.unit}: history, forecast median (P50) and P10–P90 uncertainty band vs a 7-day-average baseline`}>
          <div className="h-80" role="img" aria-label="Historical consumption with forecast median and uncertainty band"><ResponsiveContainer><ComposedChart data={show}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} fontSize={11} minTickGap={18} /><YAxis fontSize={11} width={44} domain={['auto', 'auto']} /><Tooltip formatter={(v: any) => (Array.isArray(v) ? `${v[0]} – ${v[1]}` : v)} /><Legend iconType="plainline" wrapperStyle={{ fontSize: 11 }} />
            <Area dataKey="band" name="P10–P90 band" stroke="none" fill={CHART.lilac} fillOpacity={0.25} connectNulls />
            <Line dataKey="actual" name="History" stroke={CHART.purple} dot={false} strokeWidth={2} />
            <Line dataKey="p50" name="Forecast P50" stroke={CHART.teal} strokeWidth={2.5} dot={false} />
            <Line dataKey="baseline" name="Baseline (7-day mean)" stroke="#6b6c75" strokeDasharray="5 4" dot={false} /></ComposedChart></ResponsiveContainer></div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-center sm:grid-cols-4">{[['P10 total', ht.p10], ['P50 total', ht.p50], ['P90 total', ht.p90], ['Baseline total', ht.baseline]].map(([k, v]: any) => <div key={k} className="rounded-lg bg-lilac-soft px-2 py-2"><div className="text-[11px] text-muted">{k} ({d.horizon_days} d)</div><div className="num text-base font-bold text-deep">{fmt(v)} <span className="text-xs font-normal">{d.unit}</span></div></div>)}</div>
        </Card>
        <div className="space-y-4">
          <Card title="Why did the forecast change?">
            {d.change.available ? <div className="space-y-2 text-[13px]"><p>Median daily demand moved <b className={d.change.change_pct > 0 ? 'text-orange-ink' : 'text-ok-ink'}>{d.change.change_pct > 0 ? '+' : ''}{d.change.change_pct.toFixed(1)}%</b> versus {d.change.days_ago} days ago.</p>
              <ul className="divide-y divide-line rounded-lg border border-line">{d.change.components.map((c: any) => <li key={c.driver} className="flex justify-between px-3 py-1.5"><span>{c.driver}</span><span className={`num font-semibold ${c.delta > 0 ? 'text-orange-ink' : 'text-ok-ink'}`}>{c.delta > 0 ? '+' : ''}{c.pct_of_prior.toFixed(1)}%</span></li>)}</ul>
              <p className="flex gap-1.5 text-[11px] text-muted"><Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />{d.change.method}</p></div> : <p className="text-sm text-muted">{d.change.reason}</p>}
          </Card>
          <Card title="Confidence & data"><div className="mb-2"><ConfBadge c={d.confidence} /></div><ul className="list-disc space-y-1 pl-4 text-[13px] text-gray">{d.confidence_reasons.map((r: string) => <li key={r}>{r}</li>)}</ul><p className="mt-2 text-[11px] text-muted">{d.confidence_definition}</p>
            <div className="mt-2"><Kv k="Stock reading" v={`${d.data.source} · ${d.data.validation}`} /><Kv k="Updated" v={fmtDateTime(d.data.updated_at)} /><Kv k="Fallback in use" v={d.fallback ? 'Yes (rule-based)' : 'No'} /></div></Card>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Key forecast drivers" pad={false}><DataTable rowKey={(r: any) => r.driver} cols={[{ key: 'driver', label: 'Driver' }, { key: 'effect', label: 'Value', align: 'right', render: (r: any) => `${r.effect} ${r.unit}` }, { key: 'note', label: 'How it is used', className: 'text-xs text-muted min-w-[220px]' }]} rows={d.drivers} /></Card>
        <Card title="Model vs baseline (back-test)" sub="One-day-ahead over the last 14 days of synthetic history">
          {d.backtest.n ? <div className="grid grid-cols-2 gap-3"><div className="rounded-lg bg-lilac-soft p-3"><div className="text-xs text-muted">Simulated model MAPE</div><div className="num text-2xl font-bold text-deep">{d.backtest.model_mape}%</div></div><div className="rounded-lg bg-[#eceef3] p-3"><div className="text-xs text-muted">Baseline MAPE</div><div className="num text-2xl font-bold">{d.backtest.baseline_mape}%</div></div></div> : <p className="text-sm text-muted">Not enough history to back-test.</p>}
          <p className="mt-2 text-[11px] text-muted">Computed on synthetic data; it says nothing about real-world accuracy. Model: {d.model_version}. Data as of {fmtDateTime(d.data.updated_at)}.</p></Card>
      </div>
    </div>
  )
}
