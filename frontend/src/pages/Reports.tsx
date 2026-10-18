import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Download, Search } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { download, ApiError } from '../lib/api'
import { Async, Button, Card, DataTable, Input, PageHeader, SimBanner, Tabs, useToast, Field, type Col } from '../components/ui'
import { CHART } from '../lib/format'

export default function Reports() {
  const idx = useApi<any>('/api/reports'); const [key, setKey] = useState('inventory-health'); const [q, setQ] = useState(''); const [from, setFrom] = useState(''); const [to, setTo] = useState(''); const toast = useToast()
  const s = useApi<any>(`/api/reports/${key}?${new URLSearchParams({ q, ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) })}`)
  async function csv() { try { await download(`/api/reports/${key}/csv?${new URLSearchParams({ q, ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) })}`, `himavahpro-${key}.csv`); toast('success', 'CSV exported (synthetic data).') } catch (e) { toast('error', e instanceof ApiError ? e.message : 'Export failed') } }
  const dated = key === 'recommendations' || key === 'responsible-ai'
  return (
    <>
      <PageHeader title="Reports & Analytics" sub="Calculated demo metrics on synthetic datasets" actions={<Button variant="primary" onClick={csv}><Download className="h-4 w-4" aria-hidden />Export CSV</Button>} />
      <div className="mb-4"><SimBanner>Synthetic data. Any improvement figures are targets until validated against a defined baseline.</SimBanner></div>
      <div className="mb-4 overflow-x-auto"><Tabs tabs={(idx.data?.items ?? []).map((r: any) => ({ id: r.key, label: r.title.replace(' report', '') }))} value={key} onChange={setKey} /></div>
      <Card className="mb-4" pad={false}><div className="flex flex-wrap items-end gap-3 p-3"><label className="relative min-w-[200px] flex-1"><span className="sr-only">Search report</span><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden /><Input className="pl-9" placeholder="Search this report" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <Field label="From" hint={dated ? undefined : 'Applies to dated reports'}>{(i) => <Input id={i} type="date" value={from} onChange={(e) => setFrom(e.target.value)} disabled={!dated} />}</Field><Field label="To">{(i) => <Input id={i} type="date" value={to} onChange={(e) => setTo(e.target.value)} disabled={!dated} />}</Field></div></Card>
      <Async state={s}>{(d) => (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{d.summary.map((x: any) => <div key={x.label} className="rounded-xl border border-line bg-white p-3.5"><div className="text-xs text-muted">{x.label}</div><div className="num text-2xl font-bold">{x.value ?? '—'}</div></div>)}</div>
          {d.chart.data.length > 0 && <Card title={d.title}><div className="h-60" role="img" aria-label={`${d.title} chart`}><ResponsiveContainer><BarChart data={d.chart.data}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey={d.chart.x} fontSize={11} /><YAxis fontSize={11} width={40} /><Tooltip /><Bar dataKey={d.chart.y} fill={CHART.purple} radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div></Card>}
          <Card pad={false}><DataTable rowKey={(r: any) => JSON.stringify(r)} rows={d.rows} cols={d.columns.map((c: string): Col<any> => ({ key: c, label: c.replace(/_/g, ' ') }))} empty={<p className="py-10 text-center text-sm text-muted">No rows for this filter.</p>} /><p className="border-t border-line p-3 text-[11px] text-muted">{d.note} Generated {d.generated_at}.</p></Card>
        </div>)}</Async>
    </>
  )
}
