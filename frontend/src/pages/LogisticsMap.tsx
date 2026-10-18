import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search } from 'lucide-react'
import { useApi } from '../lib/useApi'
import { Async, Card, Input, PageHeader, Select, SimBanner, Badge, cx } from '../components/ui'
import { MapLegend, SynthMap, type MapLayers } from '../components/SynthMap'
import { PostPanel } from '../components/PostPanel'
import { RISK_COLOR, SUPPLY_LABEL } from '../lib/format'

export function useMapFilters() {
  return useState({ q: '', health: '', cls: '', route: '', horizon: '3' })
}
export function filterNodes(nodes: any[], f: { q: string; health: string; cls: string }) {
  return nodes.map((n) => {
    if (n.kind !== 'post') return n
    const inv = f.cls ? n.inventory.filter((i: any) => i.supply_class === f.cls) : n.inventory
    const worst = ['critical', 'elevated', 'attention', 'healthy'].find((h) => inv.some((i: any) => i.health === h)) ?? 'healthy'
    return { ...n, health: f.cls ? worst : n.health, _hide: (f.health && worst !== f.health) || (f.q && !(`${n.id} ${n.name}`.toLowerCase().includes(f.q.toLowerCase()))) }
  }).filter((n) => !n._hide)
}

export default function LogisticsMap() {
  const s = useApi<any>('/api/map')
  const [sp, setSp] = useSearchParams()
  const sel = sp.get('post')
  const [f, setF] = useMapFilters()
  const [layers, setLayers] = useState<MapLayers>({ routes: true, air: true, weather: false, terrain: false, labels: true })
  return (
    <>
      <PageHeader title="Logistics Map" sub="Synthetic Himalayan-style network · fictional posts and routes" actions={<Badge tone="purple" icon={false}>Simulated layers</Badge>} />
      <Async state={s}>{(d) => <MapBody d={d} f={f} setF={setF} layers={layers} setLayers={setLayers} sel={sel} setSel={(id: string | null) => setSp(id ? { post: id } : {})} />}</Async>
    </>
  )
}

function MapBody({ d, f, setF, layers, setLayers, sel, setSel }: any) {
  const nodes = useMemo(() => filterNodes(d.nodes, f), [d.nodes, f])
  const routes = useMemo(() => d.routes.filter((r: any) => !f.route || (f.route === 'closed' ? r.closed : r.risk === f.route)), [d.routes, f.route])
  const selNode = d.nodes.find((n: any) => n.id === sel && n.kind === 'post')
  const toggle = (k: keyof MapLayers) => setLayers({ ...layers, [k]: !layers[k] })
  return (
    <div className="space-y-3">
      <SimBanner>{d.frame_note}</SimBanner>
      <Card pad={false}><div className="flex flex-wrap items-end gap-3 p-3">
        <label className="relative min-w-[180px] flex-1"><span className="sr-only">Search posts</span><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden /><Input placeholder="Search post or name" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} className="pl-9" /></label>
        <Select aria-label="Supply class" value={f.cls} onChange={(e) => setF({ ...f, cls: e.target.value })} className="w-auto"><option value="">All supply classes</option>{Object.entries(SUPPLY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        <Select aria-label="Stock health" value={f.health} onChange={(e) => setF({ ...f, health: e.target.value })} className="w-auto"><option value="">All stock health</option>{['healthy', 'attention', 'elevated', 'critical'].map((h) => <option key={h} value={h}>{h}</option>)}</Select>
        <Select aria-label="Route status" value={f.route} onChange={(e) => setF({ ...f, route: e.target.value })} className="w-auto"><option value="">All route status</option>{['low', 'moderate', 'elevated', 'high', 'closed'].map((h) => <option key={h} value={h}>{h}</option>)}</Select>
        <fieldset className="flex flex-wrap gap-3 text-[12px]"><legend className="sr-only">Layers</legend>
          {([['routes', 'Road routes'], ['air', 'Air routes'], ['weather', 'Weather (simulated)'], ['terrain', 'Terrain (placeholder)'], ['labels', 'Labels']] as const).map(([k, l]) => <label key={k} className="flex items-center gap-1.5"><input type="checkbox" className="h-3.5 w-3.5 accent-[#351A55]" checked={layers[k]} onChange={() => toggle(k)} />{l}</label>)}</fieldset>
      </div></Card>
      <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
        <div><SynthMap nodes={nodes} routes={routes} selected={sel} onSelect={setSel} layers={layers} className="h-[560px]" /><div className="mt-2"><MapLegend /></div>
          <p className="mt-1 text-[11px] text-muted">Weather and terrain overlays are placeholders driven by simulated values; they do not represent live intelligence.</p></div>
        <Card title={selNode ? 'Selected post' : 'Select a post'} className="max-h-[640px] overflow-auto">
          {selNode ? <PostPanel postId={selNode.id} /> : <div className="space-y-3 text-[13px] text-muted"><p>Click a marker on the map, or choose a post below.</p>
            <ul className="max-h-[480px] space-y-1 overflow-auto">{nodes.filter((n: any) => n.kind === 'post').map((n: any) => <li key={n.id}><button onClick={() => setSel(n.id)} className="flex w-full items-center justify-between rounded-lg border border-line px-3 py-1.5 text-left hover:bg-lilac-soft"><span className="font-medium text-ink">{n.id} <span className="font-normal text-muted">{n.name}</span></span><span className="text-xs capitalize">{n.health}</span></button></li>)}</ul></div>}
        </Card>
      </div>
    </div>
  )
}
