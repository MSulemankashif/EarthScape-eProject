/**
 * LiveStream - real-time sensor feed.
 * Polls /stream/latest + /stream/series every few seconds and renders a
 * moving chart of the selected metric. Admins can start/stop the simulator.
 */
import { useEffect, useRef, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import api, { errorMessage } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'

const METRICS = ['temperature_c', 'co2_ppm', 'pm25', 'wind_speed_kph',
                 'humidity_pct', 'rainfall_mm']

const POLL_MS = 3000

export default function LiveStream() {
  const { isAdmin } = useAuth()
  const [readings, setReadings] = useState([])
  const [series, setSeries] = useState({ timestamps: [], values: [] })
  const [metric, setMetric] = useState('temperature_c')
  const [active, setActive] = useState(false)
  const [error, setError] = useState('')
  const timer = useRef(null)

  const poll = async () => {
    try {
      const [latest, s] = await Promise.all([
        api.get('/stream/latest?limit=50'),
        api.get(`/stream/series?metric=${metric}&limit=120`),
      ])
      setReadings(latest.data.readings)
      setActive(latest.data.active)
      setSeries(s.data)
      setError('')
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  useEffect(() => {
    poll()
    timer.current = setInterval(poll, POLL_MS)
    return () => clearInterval(timer.current)
  }, [metric])

  const toggleStream = async () => {
    try {
      if (active) {
        await api.post('/stream/stop')
        setActive(false)
      } else {
        await api.post('/stream/start')
        setActive(true)
      }
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const chartData = series.timestamps.map((t, i) => ({
    time: t.slice(11, 19),
    value: series.values[i],
  }))

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Live Sensor Stream</h2>
          <p className="muted">
            Real-time readings pushed through the ingestion pipeline every few
            seconds.
          </p>
        </div>
        <div className="header-actions">
          <span className={active ? 'pulse-dot on' : 'pulse-dot'} />
          <span className="muted">{active ? 'streaming' : 'idle'}</span>
          {isAdmin && (
            <button className="btn btn-outline" onClick={toggleStream}>
              {active ? '⏸ Stop' : '▶ Start'} simulator
            </button>
          )}
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        <div className="card-head">
          <h3>Live metric</h3>
          <select value={metric} onChange={(e) => setMetric(e.target.value)}>
            {METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#243044" />
              <XAxis dataKey="time" stroke="#8aa0b8" fontSize={11} />
              <YAxis stroke="#8aa0b8" fontSize={12} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#16213a', border: '1px solid #2c3e57' }} />
              <Line type="monotone" dataKey="value" stroke="#37d399"
                strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="muted">Waiting for readings… start the simulator to
            see live data.</p>
        )}
      </div>

      <div className="card">
        <h3>Latest readings ({readings.length})</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th><th>Station</th><th>City</th><th>Temp °C</th>
                <th>CO₂</th><th>PM2.5</th><th>Wind</th><th>Event</th>
              </tr>
            </thead>
            <tbody>
              {readings.map((r, i) => (
                <tr key={i}>
                  <td>{r.timestamp?.slice(11, 19)}</td>
                  <td>{r.station_id}</td>
                  <td>{r.city}</td>
                  <td>{r.temperature_c}</td>
                  <td>{r.co2_ppm}</td>
                  <td className={r.pm25 > 150 ? 'danger-text' : ''}>{r.pm25}</td>
                  <td>{r.wind_speed_kph}</td>
                  <td>{r.simulated_event
                    ? <span className="tag tag-warn">{r.simulated_event} spike</span>
                    : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
