/**
 * Dashboard - the live "how is our planet doing?" home screen.
 * Every number here is REAL: OpenWeatherMap conditions for 12 Pakistani
 * cities, synced on a timer (and on demand with the ☁ Sync button).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import StatCard from '../components/StatCard.jsx'
import { PageHeader, greetingFor } from '../components/Layout.jsx'
import { Spinner, EmptyState, weatherEmoji, timeAgo } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'

const CHART_METRICS = [
  { key: 'temperature_c', label: 'Temperature', unit: '°C', color: '#5aabff' },
  { key: 'humidity_pct', label: 'Humidity', unit: '%', color: '#46d9a3' },
  { key: 'wind_speed_kph', label: 'Wind', unit: 'kph', color: '#c084fc' },
  { key: 'pm25', label: 'PM2.5', unit: 'µg/m³', color: '#ff6b7a' },
  { key: 'rainfall_mm', label: 'Rainfall', unit: 'mm', color: '#4fd1c5' },
]

const FREQ_LABEL = {
  '5min': 'rolling average · minutes since the first sync',
  h: 'hourly average · live since the first sync',
  D: 'daily average',
  ME: 'monthly average',
}

export default function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [trend, setTrend] = useState(null)
  const [health, setHealth] = useState(null)
  const [live, setLive] = useState(null)      // /api/live/status
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [metric, setMetric] = useState('temperature_c')
  const autoTried = useRef(false)             // auto first-sync guard
  const toast = useToast()

  const greeting = useMemo(() => greetingFor(new Date().getHours()), [])
  const activeMetric = CHART_METRICS.find((m) => m.key === metric) || CHART_METRICS[0]

  const load = async () => {
    try {
      const [s, h, l] = await Promise.all([
        api.get('/analytics/summary'),
        api.get('/health'),
        api.get('/live/status').catch(() => ({ data: null })),
      ])
      setSummary(s.data)
      setHealth(h.data)
      setLive(l.data)
      if (s.data.available) {
        const t = await api.get(`/analytics/timeseries?metric=${metric}&months=36`)
        setTrend(t.data)
      } else {
        setTrend(null)
        // First visit with an empty warehouse: pull live weather right away
        // so the user never stares at a blank dashboard.
        if (h.data && !autoTried.current) {
          autoTried.current = true
          toast.info('Pulling real conditions for 12 cities from OpenWeather…',
            { title: 'First live sync' })
          syncLive()
        }
      }
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Could not reach the backend' })
    } finally {
      setLoading(false)
    }
  }

  /* Reload just the chart when the metric changes */
  useEffect(() => {
    if (!summary?.available) return
    api.get(`/analytics/timeseries?metric=${metric}&months=36`)
      .then(({ data }) => setTrend(data))
      .catch((err) => toast.error(errorMessage(err)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric])

  const syncLive = async () => {
    setBusy(true)
    const started = Date.now()
    try {
      const { data } = await api.post('/live/sync', {})
      const secs = ((Date.now() - started) / 1000).toFixed(1)
      if (data.skipped) {
        toast.info(data.message, { title: 'Already fresh ☁' })
      } else {
        toast.success(
          `${data.readings} cities synced in ${secs}s · `
          + `${data.forecast_rows} forecast rows stored`
          + (data.alerts_fired ? ` · ${data.alerts_fired} alert(s) 🚨` : ''),
          { title: 'Live weather refreshed 🌍' },
        )
      }
      await load()
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Live sync failed' })
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const avg = summary?.averages || {}

  if (loading) {
    return <Spinner label="Checking the skies…" />
  }

  const freqHint = FREQ_LABEL[trend?.frequency] || 'average'

  return (
    <div>
      <PageHeader
        title={`${greeting.text}, ${greeting.icon}`}
        wave
        subtitle={summary?.available
          ? `Live from OpenWeather — ${summary.stations} cities reporting · `
            + `${summary.total_readings.toLocaleString()} readings · `
            + `${summary.date_range.start} → ${summary.date_range.end}`
          : 'Your climate warehouse is warmed up — one click away from live weather.'}
        actions={(
          <>
            <span className="status-chip" title="OpenWeather live source">
              <span className="dot" aria-hidden="true" />
              {live?.last_sync_at
                ? `Live · synced ${timeAgo(live.last_sync_at)}`
                : '🌍 Live · OpenWeather'}
            </span>
            <span className="status-chip" title="API backend">
              <span className="dot" aria-hidden="true" />
              {health?.storage_backend || '…'} · {health?.database_backend || '…'}
            </span>
            <button className="btn btn-warm" onClick={() => syncLive()} disabled={busy}>
              {busy
                ? <><span className="spinner spinner-sm" aria-hidden="true" /> Syncing…</>
                : '☁ Sync live weather'}
            </button>
          </>
        )}
      />

      {!summary?.available && (
        <EmptyState
          emoji="🌍"
          title="Let's pull in live weather"
        >
          <p>
            One click connects this dashboard to real, live conditions — no sample
            files, no dummy readings.
          </p>
          <div className="steps">
            <div className="step">
              <span className="step-num">1</span>
              <strong>Sync live weather</strong>
              <span>Press “☁ Sync live weather” above — real conditions for 12 Pakistani cities plus their 5-day forecasts land in HDFS-style partitions.</span>
            </div>
            <div className="step">
              <span className="step-num">2</span>
              <strong>Train the models</strong>
              <span>Head to Analytics &amp; ML and train the anomaly + trend detectors on the live history.</span>
            </div>
            <div className="step">
              <span className="step-num">3</span>
              <strong>Watch it live</strong>
              <span>Open Live Weather — readings refresh on a timer and every one of them checks your alert rules on arrival.</span>
            </div>
          </div>
        </EmptyState>
      )}

      {summary?.available && (
        <>
          <div className="stat-grid">
            <StatCard label="Avg Temperature" value={`${avg.temperature_c ?? '—'} °C`} icon="🌡️" />
            <StatCard label="Avg Humidity" value={`${avg.humidity_pct ?? '—'} %`} icon="💧" />
            <StatCard label="Avg Wind" value={`${avg.wind_speed_kph ?? '—'} kph`} icon="💨" />
            <StatCard label="Avg PM2.5" value={`${avg.pm25 ?? '—'} µg/m³`} icon="🍃" />
            <StatCard label="Readings" value={summary.total_readings.toLocaleString()} icon="📦" />
            <StatCard label="Missing Values" value={summary.missing_values} icon="⚠️" />
          </div>

          <div className="card">
            <div className="card-head">
              <h3 style={{ margin: 0 }}>
                {activeMetric.label} trend
                <span className="muted" style={{ fontWeight: 400 }}> · {freqHint}</span>
              </h3>
              <label className="muted" style={{ margin: 0 }}>
                Metric
                <select value={metric} onChange={(e) => setMetric(e.target.value)}
                  aria-label="Choose chart metric"
                  style={{ width: 'auto', marginLeft: 8, marginTop: 0 }}>
                  {CHART_METRICS.map((m) => (
                    <option key={m.key} value={m.key}>{m.label} ({m.unit})</option>
                  ))}
                </select>
              </label>
            </div>
            {trend?.points?.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trend.points}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2b3850" />
                  <XAxis dataKey="date" stroke="#93a5bf" fontSize={12} />
                  <YAxis stroke="#93a5bf" fontSize={12} />
                  <Tooltip contentStyle={{
                    background: '#1c2434', border: '1px solid #2b3850',
                    borderRadius: 10,
                  }} />
                  <Line type="monotone" dataKey="value" stroke={activeMetric.color}
                    strokeWidth={2.4} dot={false} name={activeMetric.unit} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="muted">No readings for this metric yet — each sync adds
                another point to this chart.</p>
            )}
          </div>

          <div className="card">
            <h3>Current conditions across cities</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Station</th><th>City</th><th>Region</th><th>Now</th>
                    <th>Temp °C</th><th>Humidity %</th><th>Wind kph</th>
                    <th>PM2.5</th><th>Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.latest_by_station.map((r) => (
                    <tr key={r.station_id}>
                      <td>{r.station_id}</td>
                      <td>{r.city}</td>
                      <td><span className="tag">{r.region ?? '—'}</span></td>
                      <td title={r.weather_main || ''}>
                        {weatherEmoji(r.weather_main)}{' '}
                        <span className="muted">{r.weather_main ?? ''}</span>
                      </td>
                      <td>{r.temperature_c ?? '—'}</td>
                      <td>{r.humidity_pct ?? '—'}</td>
                      <td>{r.wind_speed_kph ?? '—'}</td>
                      <td className={r.pm25 > 150 ? 'danger-text' : ''}>
                        {r.pm25 ?? '—'}
                      </td>
                      <td className="muted">{r.date?.slice(0, 16)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
