import { useEffect, useState } from 'react'

/** Resolves where the traveller is, so nothing downstream assumes a home hub.
 *
 *  Asks the server, which falls back to IP. If the browser will share precise
 *  coordinates we ask again with those — but we never block on the permission
 *  prompt, so the first answer always arrives.
 */
export function useLocale() {
  const [locale, setLocale] = useState(null)
  const [airports, setAirports] = useState([])
  const [origin, setOrigin] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true

    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone

    async function ask(body) {
      const res = await fetch('/api/locale', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`locale ${res.status}`)
      return res.json()
    }

    function apply(data) {
      if (!live || !data) return
      setLocale(data.locale || null)
      setAirports(data.airports || [])
      setOrigin(data.origin_airport || null)
      setLoading(false)
    }

    ask({ timezone }).then(apply).catch(() => live && setLoading(false))

    // Upgrade to GPS if the browser offers it; silence on refusal is correct.
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          ask({
            timezone,
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
          }).then(apply).catch(() => {})
        },
        () => {},
        { timeout: 8000, maximumAge: 600000 }
      )
    }

    return () => { live = false }
  }, [])

  return { locale, airports, origin, loading, setOrigin }
}
