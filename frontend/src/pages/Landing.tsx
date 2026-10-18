import { Link } from 'react-router-dom'
import { Area, AreaChart, ResponsiveContainer } from 'recharts'
import { ArrowRight, BarChart3, Brain, Eye, Lock, Map as MapIcon, Package, Route as RouteIcon, ScrollText, ShieldCheck, Truck, UserCheck, Layers, Gauge, CheckCircle2 } from 'lucide-react'
import { Logo } from '../components/Logo'
import { Button } from '../components/ui'

const spark = [7, 8, 7.4, 6.9, 6.2, 5.8, 5.1, 4.6, 4.2, 3.9].map((v, i) => ({ i, v }))
const FEATURES = [
  { icon: BarChart3, t: 'Predictive Demand Intelligence', d: 'Multi-horizon forecasts with P10/P50/P90 uncertainty, Days of Supply and Time-to-Stockout for every post and supply class.' },
  { icon: RouteIcon, t: 'Route Reliability Index', d: 'Terrain- and weather-aware reliability expressed as a probability, with the reasons behind every score.' },
  { icon: Package, t: 'Smart Inventory Visibility', d: 'Sensor, manual and simulated readings reconciled with freshness and validation states, including offline field entry.' },
  { icon: Truck, t: 'Multimodal Optimisation', d: 'Dijkstra-based road routing, air alternatives and a what-if simulator to compare plans before anyone decides.' },
  { icon: Brain, t: 'Explainable AI', d: 'Each recommendation shows its evidence, alternatives, limitations and recomputed counterfactuals. Nothing is a black box.' },
  { icon: ShieldCheck, t: 'Responsible AI and Governance', d: 'Human approval, low-confidence escalation, a hash-chained audit trail and a DPDP-aligned privacy workspace.' },
]
const NAVL = [['Overview', '#overview'], ['Capabilities', '#capabilities'], ['Architecture', '#architecture'], ['Responsible AI', '#responsible'], ['Security', '#security']]

export default function Landing() {
  return (
    <div className="bg-white text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3">
          <Logo />
          <nav aria-label="Site" className="hidden gap-6 text-[13px] font-medium text-gray md:flex">{NAVL.map(([l, h]) => <a key={l} href={h} className="hover:text-deep">{l}</a>)}</nav>
          <Link to="/signin"><Button variant="primary">Secure Sign In</Button></Link>
        </div>
      </header>

      <section id="overview" className="bg-[linear-gradient(180deg,#f6f4fb,#ffffff)]">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-5 py-14 lg:grid-cols-[1fr_1.05fr] lg:py-20">
          <div>
            <p className="mb-3 inline-block rounded-full bg-lilac-soft px-3 py-1 text-xs font-semibold text-deep">Predict | Prepare | Optimise | Assure</p>
            <h1 className="text-4xl font-bold leading-[1.1] tracking-tight text-deep sm:text-5xl">Predictive Logistics.<br />Strengthen Readiness.</h1>
            <p className="mt-4 max-w-xl text-[17px] text-gray">AI-driven intelligence for resilient supply chains and uninterrupted operations. HimavahPro forecasts demand, flags routes at risk and recommends assured supply plans, and leaves every decision to authorised people.</p>
            <div className="mt-7 flex flex-wrap gap-3"><Link to="/signin"><Button variant="primary" size="md" className="px-5 py-2.5">Secure Sign In <ArrowRight className="h-4 w-4" /></Button></Link><a href="#capabilities"><Button className="px-5 py-2.5">Explore capabilities</Button></a></div>
            <p className="mt-4 text-xs text-muted">Smart India Hackathon 2026 prototype. Synthetic data; simulated models; no real operational information.</p>
          </div>
          <div role="img" aria-label="Preview of the HimavahPro Command Centre showing simulated logistics intelligence" className="rounded-2xl border border-line bg-white p-3 shadow-[0_20px_50px_-20px_rgba(53,26,85,.35)]">
            <div className="mb-2 flex items-center justify-between text-[11px] text-muted"><span className="font-semibold text-deep">Command Centre</span><span className="rounded-full bg-lilac-soft px-2 py-0.5 font-semibold text-deep">Simulated preview</span></div>
            <div className="grid grid-cols-3 gap-2">{[['Posts needing attention', '7'], ['Critical stock alerts', '2'], ['Pending approvals', '3']].map(([k, v]) => <div key={k} className="rounded-lg border border-line p-2"><div className="text-[10px] text-muted">{k}</div><div className="num text-xl font-bold text-deep">{v}</div></div>)}</div>
            <div className="mt-2 grid grid-cols-5 gap-2">
              <div className="relative col-span-3 h-44 overflow-hidden rounded-lg bg-[#eef0f6]">
                <svg viewBox="0 0 300 170" className="h-full w-full" aria-hidden>
                  <g stroke="#9c97c4" strokeWidth="2" fill="none"><path d="M30 130 90 100 140 120 200 70 260 50" /><path d="M90 100 110 50 170 40 200 70" strokeDasharray="4 3" stroke="#D64545" /><path d="M140 120 190 140 250 120" stroke="#7DC161" /></g>
                  {[[30, 130, '#7DC161'], [90, 100, '#FFCD2E'], [140, 120, '#7DC161'], [200, 70, '#D64545'], [260, 50, '#F57F2A'], [110, 50, '#7DC161'], [170, 40, '#FFCD2E'], [190, 140, '#7DC161'], [250, 120, '#7DC161']].map(([x, y, c], i) => <circle key={i} cx={x as number} cy={y as number} r="7" fill={c as string} stroke="#fff" strokeWidth="2" />)}
                </svg>
                <span className="absolute bottom-1 left-2 text-[9px] text-muted">Synthetic map</span>
              </div>
              <div className="col-span-2 space-y-2">
                <div className="rounded-lg border border-line p-2"><div className="text-[10px] text-muted">Days of Supply · POST-K04 fuel</div><div className="h-12"><ResponsiveContainer><AreaChart data={spark}><Area dataKey="v" stroke="#351A55" fill="#746FA7" fillOpacity={0.3} isAnimationActive={false} /></AreaChart></ResponsiveContainer></div></div>
                <div className="rounded-lg border border-line p-2 text-[10px]"><div className="font-semibold text-deep">Recommendation · pending review</div><div className="mt-1 text-muted">Awaiting human decision</div><div className="mt-1.5 flex gap-1"><span className="rounded bg-deep px-1.5 py-0.5 text-white">Approve</span><span className="rounded border border-line px-1.5 py-0.5">Reject</span></div></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="capabilities" className="mx-auto max-w-6xl px-5 py-14">
        <h2 className="text-2xl font-bold text-deep">What HimavahPro does</h2><p className="mt-1 max-w-2xl text-gray">One command centre for forecasts, stock health, route risk and supply decisions, built around uncertainty and accountability.</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{FEATURES.map((f) => <div key={f.t} className="rounded-xl border border-line p-5"><span className="grid h-10 w-10 place-items-center rounded-full bg-lilac-soft text-deep"><f.icon className="h-5 w-5" aria-hidden /></span><h3 className="mt-3 font-semibold">{f.t}</h3><p className="mt-1 text-[13px] text-gray">{f.d}</p></div>)}</div>
      </section>

      <section id="architecture" className="bg-bg">
        <div className="mx-auto max-w-6xl px-5 py-14">
          <h2 className="text-2xl font-bold text-deep">Sense → Think → Act</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {[[Layers, 'Sense', 'Sensor, manual and field readings, weather and terrain inputs, consumption history. Offline-ready entry with a safe sync queue.'], [Gauge, 'Think', 'Forecasting, route reliability, Dijkstra routing and a what-if simulator turn data into ranked, explained options.'], [UserCheck, 'Act', 'Recommendations go to a human for approve, edit or reject. Every decision is audited. Dispatch is simulated only.']].map(([I, t, d]: any, i) => (
              <div key={t} className="relative rounded-xl border border-line bg-white p-5"><span className="text-xs font-bold text-lilac">0{i + 1}</span><div className="mt-1 flex items-center gap-2"><I className="h-5 w-5 text-deep" aria-hidden /><h3 className="font-semibold">{t}</h3></div><p className="mt-2 text-[13px] text-gray">{d}</p></div>))}
          </div>
          <p className="mt-5 text-[13px] text-gray">Stack: React + TypeScript, FastAPI + Pydantic, SQLAlchemy (SQLite for the demo, PostgreSQL-ready), MapLibre GL, Docker Compose. External model and IoT integrations sit behind replaceable service interfaces.</p>
        </div>
      </section>

      <section id="responsible" className="mx-auto max-w-6xl px-5 py-14">
        <h2 className="text-2xl font-bold text-deep">Responsible AI, by design</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[[UserCheck, 'Human approval', 'AI recommends; authorised personnel decide. Rejections and overrides require a reason.'], [Eye, 'Confidence indicators', 'High, Medium and Low labels with the reasons. Low confidence forces mandatory review.'], [ScrollText, 'Auditability', 'Consequential actions are written to a hash-chained audit log with integrity verification.'], [Lock, 'Private deployment', 'Designed for on-premises or approved government hosting. No external API is needed to load a screen.']].map(([I, t, d]: any) => (
            <div key={t} className="rounded-xl border border-line p-5"><I className="h-5 w-5 text-deep" aria-hidden /><h3 className="mt-2 font-semibold">{t}</h3><p className="mt-1 text-[13px] text-gray">{d}</p></div>))}
        </div>
      </section>

      <section id="security" className="bg-deep text-white">
        <div className="mx-auto grid max-w-6xl gap-6 px-5 py-12 md:grid-cols-[1.3fr_1fr]">
          <div><h2 className="text-2xl font-bold">Security and privacy posture</h2><p className="mt-2 max-w-xl text-[#D8D4EC]">Role-based access is enforced on the server, not just in the interface. The privacy workspace distinguishes personal from non-personal data and follows data minimisation and purpose limitation.</p>
            <p className="mt-3 text-sm font-medium text-[#B9B5DB]">DPDP-aligned by design; subject to deployment-specific legal and security review.</p></div>
          <ul className="space-y-2 text-sm">{['Least-privilege roles and a permission matrix', 'Hash-chained audit log with tamper detection', 'Demonstration authentication behind a replaceable identity boundary', 'Not certified, not security-audited, not officially approved'].map((x) => <li key={x} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#7DC161]" aria-hidden />{x}</li>)}</ul>
        </div>
      </section>
      <footer className="border-t border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-6 text-xs text-muted"><Logo sub={false} /><p className="max-w-xl">HimavahPro is a Smart India Hackathon 2026 prototype built on synthetic data. It is not connected to any operational system and uses no real locations, movements or personal data. Models shown are simulated or rule-based.</p></div>
      </footer>
    </div>
  )
}
