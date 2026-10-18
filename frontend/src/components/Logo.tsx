export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#351A55" />
      <g stroke="#B9B5DB" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none"><path d="M8 22 14 11 19 17 24 9" /></g>
      <g fill="#fff"><circle cx="8" cy="22" r="2.4" /><circle cx="14" cy="11" r="2.4" /><circle cx="19" cy="17" r="2.4" /></g>
      <circle cx="24" cy="9" r="2.4" fill="#7DC161" />
    </svg>
  )
}
export function Logo({ light = false, sub = true }: { light?: boolean; sub?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark />
      <div className="leading-tight">
        <div className={`text-[17px] font-bold tracking-tight ${light ? 'text-white' : 'text-deep'}`}>Himavah<span className={light ? 'text-[#B9B5DB]' : 'text-lilac'}>Pro</span></div>
        {sub && <div className={`text-[10.5px] font-medium ${light ? 'text-[#CFCBE6]' : 'text-muted'}`}>Predictive Logistics Intelligence</div>}
      </div>
    </div>
  )
}
