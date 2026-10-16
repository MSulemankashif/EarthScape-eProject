/**
 * Live Weather - the real-time heart of EarthScape.
 * Pulls live OpenWeatherMap conditions for 12 Pakistani cities, refreshes
 * on a timer, and lets you trigger a sync on demand. Every reading is
 * cleaned, stored in HDFS-style partitions and checked against alert rules
 * the moment it lands.
 */
import { useEffect, useRef, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import { PageHeader } from '../components/Layout.jsx'
import { Spinner, EmptyState, weatherEmoji, aqiInfo, timeAgo, prettyDateTime } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'

const CHART_METRICS = [
  { key: 'temperature_c', label: 'Temperature °C', color: '#5aabff' },
  { key: 'humidity_pct', label: 'Humidity %', color: '#46d9a3' },
  { key: 'wind_speed_kph', label: 'Wind kph', color: '#c084fc' },
  { key: 'pm25', label: 'PM2.5 µg/m³', color: '#ff6b7a' },
]

const POLL_MS = 30000   // gentle on the free API quota (auto-sync is 10 min)

export default function LiveWeather() {
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [latest, setLatest] = useState({ readings: [], synced_at: null })
  const [status, setStatus] = useState(null)
  const [metric, setMetric] = useState('temperature_c')
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const timer = useRef(null)

  const activeMetric = CHART_METRICS.find((m) => m.key === metric)

  const poll = async () => {
    try {
      const [l, s] = await Promise.all([
        api.get('/live/latest'),
        api.get('/live/status'),
      ])
      setLatest(l.data)
      setStatus(s.data)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  useEffect(() => {
    poll()
    timer.current = setInterval(poll, POLL_MS)
    return () => clearInterval(timer.current)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const syncNow = async () => {
    setSyncing(true)
    const started = Date.now()
    try {
      const { data } = await api.post('/live/sync', {})
      const secs = ((Date.now() - started) / 1000).toFixed(1)
      if (data.skipped) {
        toast.info(data.message, { title: 'Already fresh ☁' })
      } else {
        toast.success(
          `${data.readings} cities in ${secs}s`
          + (data.alerts_fired ? ` · ${data.alerts_fired} alert(s) raised 🚨` : ''),
          { title: 'Live weather synced 🌍' },
        )
      }
      await poll()
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Sync failed' })
    } finally {
      setSyncing(false)
    }
  }

  const readings = latest.readings || []
  const chartData = readings
    .map((r) => ({ city: r.city, value: r[metric] }))
    .filter((d) => d.value !== null && d.value !== undefined)

  return (
    <div>
      <PageHeader
        title="Live Weather"
        subtitle={
          'Real conditions for 12 Pakistani cities, pulled straight from OpenWeatherMap — '
          + 'cleaned, partitioned in HDFS-style storage and evaluated against your alert '
          + 'rules the moment they land.'
        }
        actions={(
          <>
            <span className="live-meta">
              <span className={readings.length ? 'pulse-dot on' : 'pulse-dot'} />
              <span className="muted">
                {readings.length
                  ? `updated ${timeAgo(latest.synced_at)}`
                  : 'waiting for first sync'}
              </span>
            </span>
            <span className="status-chip" title="Auto-sync cadence">
              <span className="dot" aria-hidden="true" />
              {status?.auto_sync
                ? `auto every ${status.interval_minutes} min`
                : 'auto-sync off'}
            </span>
            <button className="btn btn-warm" onClick={syncNow} disabled={syncing}>
              {syncing
                ? <><span className="spinner spinner-sm" aria-hidden="true" /> Syncing…</>
                : '☁ Sync now'}
            </button>
          </>
        )}
      />

      {error && <div className="alert alert-error">{error}</div>}

      {status?.last_error && !readings.length && (
        <div className="alert alert-error">
          Last sync problem: {status.last_error}
        </div>
      )}

      {readings.length === 0 ? (
        <EmptyState emoji="🌦️" title="The sky is quiet — for now">
          <p>
            {isAdmin
              ? 'Press “☁ Sync now” above and real conditions for all 12 cities appear within seconds.'
              : 'No live readings yet — an admin or analyst can kick off the first sync from this page.'}
          </p>
        </EmptyState>
      ) : (
        <>
          <div className="city-grid rise">
            {readings.map((r) => {
              const aqi = aqiInfo(r.aqi)
              return (
                <div className="city-card" key={r.station_id}>
                  <div className="city-card-top">
                    <span className="city-emoji" aria-hidden="true">
                      {weatherEmoji(r.weather_main)}
                    </span>
                    <span className={`tag ${aqi.cls}`} title="Air Quality Index">
                      AQI {r.aqi ?? '—'} · {aqi.label}
                    </span>
                  </div>
                  <p className="city-name">
                    {r.city} <span className="tag">{r.region ?? ''}</span>
                  </p>
                  <p className="city-temp">{r.temperature_c ?? '—'}°C</p>
                  <p className="city-cond">
                    {r.weather_desc || r.weather_main || ''}
                    {r.feels_like_c != null && ` · feels ${r.feels_like_c}°`}
                  </p>
                  <div className="city-metrics">
                    <span>💧 Humidity <b>{r.humidity_pct ?? '—'}%</b></span>
                    <span>💨 Wind <b>{r.wind_speed_kph ?? '—'} kph</b></span>
                    <span>🍃 PM2.5 <b>{r.pm25 ?? '—'}</b></span>
                    {(r.sunrise || r.sunset) && (
                      <span>
                        🌅 {r.sunrise?.slice(11, 16) ?? '—'}
                        {' · '}🌇 {r.sunset?.slice(11, 16) ?? '—'}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="card">
            <div className="card-head">
              <h3 style={{ margin: 0 }}>By city</h3>
              <label className="muted" style={{ margin: 0 }}>
                Metric
                <select value={metric} onChange={(e) => setMetric(e.target.value)}
                  aria-label="Choose comparison metric"
                  style={{ width: 'auto', marginLeft: 8, marginTop: 0 }}>
                  {CHART_METRICS.map((m) => (
                    <option key={m.key} value={m.key}>{m.label}</option>
                  ))}
                </select>
              </label>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2b3850" />
                <XAxis dataKey="city" stroke="#93a5bf" fontSize={11} />
                <YAxis stroke="#93a5bf" fontSize={12} domain={['auto', 'auto']} />
                <Tooltip cursor={{ fill: 'rgba(90,171,255,.07)' }}
                  contentStyle={{ background: '#1c2434', border: '1px solid #2b3850', borderRadius: 10 }} />
                <Bar dataKey="value" fill={activeMetric?.color || '#5aabff'}
                  radius={[6, 6, 0, 0]} name={activeMetric?.label} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <div className="card-head">
              <h3 style={{ margin: 0 }}>Latest readings ({readings.length})</h3>
              <span className="muted">
                {status?.last_duration_seconds != null
                  ? `last sync ${status.last_duration_seconds}s · ${status.calls_per_sync} API calls`
                  : ''}
              </span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Station</th><th>City</th><th>Observed</th><th>Temp °C</th>
                    <th>Feels °C</th><th>Humidity %</th><th>Wind kph</th>
                    <th>PM2.5</th><th>AQI</th><th>Pressure hPa</th><th>Condition</th>
                  </tr>
                </thead>
                <tbody>
                  {readings.map((r) => {
                    const aqi = aqiInfo(r.aqi)
                    return (
                      <tr key={r.station_id}>
                        <td>{r.station_id}</td>
                        <td>{r.city}</td>
                        <td className="muted">
                          {prettyDateTime(r.date)}
                          <div className="small">{timeAgo(r.date)}</div>
                        </td>
                        <td>{r.temperature_c ?? '—'}</td>
                        <td>{r.feels_like_c ?? '—'}</td>
                        <td>{r.humidity_pct ?? '—'}</td>
                        <td>{r.wind_speed_kph ?? '—'}</td>
                        <td className={r.pm25 > 150 ? 'danger-text' : ''}>
                          {r.pm25 ?? '—'}
                        </td>
                        <td><span className={`tag ${aqi.cls}`}>{r.aqi ?? '—'}</span></td>
                        <td>{r.pressure_hpa ?? '—'}</td>
                        <td>{weatherEmoji(r.weather_main)} {r.weather_main ?? '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
