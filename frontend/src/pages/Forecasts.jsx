/**
 * Forecasts - two honest sources of "what's next":
 *   1. LIVE 5-day / 3-hour forecast straight from OpenWeatherMap (default)
 *   2. The trained linear+seasonal model's long-range projection
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner, EmptyState, weatherEmoji } from '../components/ui.jsx'

const MODEL_METRICS = ['temperature_c', 'co2_ppm', 'rainfall_mm']
const HORIZONS = [30, 90, 180, 365]

const FRIENDLY = {
  temperature_c: 'Temperature',
  co2_ppm: 'CO₂',
  rainfall_mm: 'Rainfall',
}

/* "2026-10-16 15:00" -> "Thu 15:00" */
function slotLabel(iso) {
  if (!iso) return ''
  const d = new Date(iso.replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return iso
  const day = d.toLocaleDateString(undefined, { weekday: 'short' })
  return `${day} ${String(d.getHours()).padStart(2, '0')}:00`
}

export default function Forecasts() {
  const [cities, setCities] = useState([])
  const [city, setCity] = useState('Lahore')
  const [fc, setFc] = useState(null)          // OpenWeather 5-day forecast
  const [fcBusy, setFcBusy] = useState(true)
  const [fcError, setFcError] = useState('')

  // Secondary: ML model projection
  const [metric, setMetric] = useState('temperature_c')
  const [days, setDays] = useState(90)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/live/cities')
      .then(({ data }) => setCities(data.cities.map((c) => c.name)))
      .catch(() => setCities([]))
  }, [])

  const loadLive = async (name = city) => {
    setFcBusy(true)
    setFcError('')
    try {
      const { data } = await api.get(`/live/forecast?city=${encodeURIComponent(name)}`)
      setFc(data)
    } catch (err) {
      setFc(null)
      setFcError(errorMessage(err))
    } finally {
      setFcBusy(false)
    }
  }

  useEffect(() => { loadLive(city) }, [city]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadModel = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await api.get(`/analytics/ml/forecast?metric=${metric}&days=${days}`)
      setData(data)
    } catch (err) {
      setData(null)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { loadModel() }, [metric, days]) // eslint-disable-line react-hooks/exhaustive-deps

  const points = (fc?.points || []).map((p) => ({
    ...p,
    label: slotLabel(p.date),
    date: slotLabel(p.date),
  }))

  const temps = points.map((p) => p.temperature_c).filter((v) => v != null)
  const hums = points.map((p) => p.humidity_pct).filter((v) => v != null)
  const winds = points.map((p) => p.wind_speed_kph).filter((v) => v != null)
  const rainy = points.filter((p) => (p.precipitation_prob ?? 0) >= 0.4).length
  const cond = points.find((p) => p.weather_main)?.weather_main
  const avg = (arr) => (arr.length
    ? Math.round((arr.reduce((a, b) => a + b, 0) / arr.length) * 10) / 10
    : '—')

  const s = data?.summary

  return (
    <div>
      <PageHeader
        title="Forecasts"
        subtitle="Real 5-day forecasts from OpenWeatherMap up top, plus your trained model's long-range projection below — you always know which source you're reading."
        actions={(
          <select value={city} onChange={(e) => setCity(e.target.value)}
            aria-label="Forecast city">
            {(cities.length ? cities : [city]).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        )}
      />

      {/* ---------------- LIVE OpenWeather 5-day forecast ---------------- */}
      {fcError && (
        <div className="alert alert-error">
          {fcError} — try a “☁ Sync now” from the <Link to="/live">Live Weather</Link> page.
        </div>
      )}

      {fcBusy ? (
        <Spinner label={`Fetching the live ${city} forecast…`} />
      ) : points.length > 0 && (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <span className="stat-icon">{weatherEmoji(cond)}</span>
              <div>
                <p className="stat-label">High / Low (5 days)</p>
                <p className="stat-value">
                  {temps.length ? `${Math.max(...temps)}° / ${Math.min(...temps)}°` : '—'}
                </p>
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-icon">💧</span>
              <div>
                <p className="stat-label">Avg humidity</p>
                <p className="stat-value">{avg(hums)}%</p>
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-icon">🌧️</span>
              <div>
                <p className="stat-label">Rain expected</p>
                <p className="stat-value">{rainy} of {points.length} slots</p>
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-icon">💨</span>
              <div>
                <p className="stat-label">Avg wind</p>
                <p className="stat-value">{avg(winds)} kph</p>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <h3 style={{ margin: 0 }}>
                ☁ Live 5-day forecast — {city}
              </h3>
              <span className="muted">
                OpenWeatherMap · 3-hour steps · fetched {new Date().toLocaleTimeString()}
              </span>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={points}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2b3850" />
                <XAxis dataKey="date" stroke="#93a5bf" fontSize={10} interval={3} />
                <YAxis stroke="#93a5bf" fontSize={12} domain={['auto', 'auto']} />
                <Tooltip contentStyle={{
                  background: '#1c2434', border: '1px solid #2b3850', borderRadius: 10,
                }} />
                <Line type="monotone" dataKey="temperature_c" stroke="#5aabff"
                  strokeWidth={2.4} dot={false} name="Temp °C" />
                <Line type="monotone" dataKey="humidity_pct" stroke="#46d9a3"
                  strokeWidth={1.8} dot={false} strokeDasharray="5 4" name="Humidity %" />
              </LineChart>
            </ResponsiveContainer>
            <p className="muted" style={{ marginTop: 8 }}>
              Solid line = temperature · dashed = humidity · every point is real API data.
            </p>
          </div>
        </>
      )}

      {/* ---------------- Secondary: model projection ---------------- */}
      <div className="card">
        <div className="card-head">
          <h3 style={{ margin: 0 }}>
            🧠 Model projection
            <span className="muted" style={{ fontWeight: 400 }}>
              {' '}· trained on your live reading history
            </span>
          </h3>
          <div className="live-meta">
            <select value={metric} onChange={(e) => setMetric(e.target.value)}
              aria-label="Forecast metric">
              {MODEL_METRICS.map((m) => (
                <option key={m} value={m}>{FRIENDLY[m] || m}</option>
              ))}
            </select>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}
              aria-label="Forecast horizon">
              {HORIZONS.map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </div>
        </div>

        {s && (
          <div className="stat-grid">
            <div className="stat-card">
              <span className="stat-icon">📈</span>
              <div>
                <p className="stat-label">Trend direction</p>
                <p className="stat-value">{s.direction}</p>
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-icon">📐</span>
              <div>
                <p className="stat-label">Slope per year</p>
                <p className="stat-value">{s.slope_per_year}</p>
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-icon">🎯</span>
              <div>
                <p className="stat-label">Model fit (R²)</p>
                <p className="stat-value">{s.r2}</p>
              </div>
            </div>
            <div className="stat-card">
              <span className="stat-icon">🗓️</span>
              <div>
                <p className="stat-label">Trained until</p>
                <p className="stat-value">{s.trained_until}</p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="alert alert-info">
            {error} — train the models on the <Link to="/analytics">Analytics page</Link> first.
          </div>
        )}

        {data?.forecast?.length > 0 ? (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={data.forecast}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2b3850" />
              <XAxis dataKey="date" stroke="#93a5bf" fontSize={11} />
              <YAxis stroke="#93a5bf" fontSize={12} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#1c2434', border: '1px solid #2b3850', borderRadius: 10 }} />
              <Line type="monotone" dataKey={metric} stroke="#ffb45c"
                strokeWidth={2.4} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : busy ? (
          <Spinner label="Projecting the future…" />
        ) : !error && (
          <EmptyState emoji="🔮" title="No model projection yet">
            <p>Train the trend models on the <Link to="/analytics">Analytics page</Link> —
              once they are fresh, every metric here can look months ahead.</p>
          </EmptyState>
        )}
      </div>
    </div>
  )
}
