import { describe, expect, it } from 'vitest'
import { fmt, fmtHours, pct } from './format'

describe('format helpers', () => {
  it('renders em dash for missing values', () => {
    expect(fmt(null)).toBe('—')
    expect(pct(undefined)).toBe('—')
    expect(fmtHours(null)).toBe('—')
  })
  it('switches hours to days after 48 h', () => {
    expect(fmtHours(24)).toBe('24 h')
    expect(fmtHours(72)).toBe('3.0 d')
  })
  it('formats percentages', () => {
    expect(pct(0.256, 1)).toBe('25.6%')
  })
})
