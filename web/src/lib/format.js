// Money and time, rendered the way the traveller's own locale writes them.

const ZERO_DECIMAL = new Set(['JPY', 'KRW', 'VND', 'IDR', 'CLP', 'ISK'])

/** Format an amount in its own currency. Never converts — we hold no rates. */
export function money(amount, currency = 'USD', { round = false } = {}) {
  if (amount == null || Number.isNaN(Number(amount))) return null
  const digits = ZERO_DECIMAL.has(currency) ? 0 : round ? 0 : 2
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(Number(amount))
  } catch {
    return `${currency} ${Number(amount).toFixed(digits)}`
  }
}

/** "09:00" from the agent's 2026-09-28T09:00, without shifting the zone.
 *  Flight times are local to their airport, which is how airlines publish
 *  them — reinterpreting them in the viewer's zone would be wrong. */
export function clockTime(iso) {
  if (!iso) return ''
  const match = String(iso).match(/T(\d{2}):(\d{2})/)
  return match ? `${match[1]}:${match[2]}` : ''
}

/** "28 Sep" */
export function shortDate(iso) {
  if (!iso) return ''
  const date = new Date(`${String(iso).slice(0, 10)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return String(iso).slice(0, 10)
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/** "28 Sep – 2 Oct" */
export function dateRange(from, to) {
  if (!from) return ''
  return to ? `${shortDate(from)} – ${shortDate(to)}` : shortDate(from)
}

/** "3h 10m" */
export function duration(minutes) {
  if (!minutes) return ''
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h}h${m ? ` ${m}m` : ''}` : `${m}m`
}

/** True when the airport's clock differs from the traveller's own. */
export function crossesTimezone(locale, airportTz) {
  return Boolean(locale?.timezone && airportTz && locale.timezone !== airportTz)
}
