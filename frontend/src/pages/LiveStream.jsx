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
import { PageHeader } from '../components/Layout.jsx'
import { EmptyState } from '../components/ui.jsx'
import { useToast } from '../context/ToastContext.jsx'

const METRICS = ['temperature_c', 'co2_ppm', 'pm25', 'wind_speed_kph',
                 'humidity_pct', 'rainfall_mm']

const POLL_MS = 3000

export default function LiveStream() {
  const { isAdmin } = useAuth()
  const toast = useToast()
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
        toast.info('Simulator paused — the chart keeps the last readings.', { title: 'Stream stopped' })
      } else {
        await api.post('/stream/start')
        setActive(true)
        toast.success('Readings are flowing in every couple of seconds. Watch the Alerts bell!',
          { title: 'Live stream started 📡' })
      }
    } catch (err) {
      toast.error(errorMessage(err), { title: 'Could not toggle stream' })
    }
  }

  const chartData = series.timestamps.map((t, i) => ({
    time: t.slice(11, 19),
    value: series.values[i],
  }))

  return (
    <div>
      <PageHeader
        title="Live Sensor Stream"
        subtitle="Real-time readings pushed through the same ingestion pipeline as the batch files — every one of them is checked against your alert rules on arrival."
        actions={(
          <>
            <span className={active ? 'pulse-dot on' : 'pulse-dot'} />
            <span className="muted">{active ? 'streaming now' : 'idle'}</span>
            {isAdmin && (
              <button className="btn btn-primary" onClick={toggleStream}>
                {active ? '⏸ Stop simulator' : '▶ Start simulator'}
              </button>
            )}
            {!isAdmin && !active && (
              <span className="muted">Ask an admin to start the simulator</span>
            )}
          </>
        )}
      />

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
              <CartesianGrid strokeDasharray="3 3" stroke="#2b3850" />
              <XAxis dataKey="time" stroke="#93a5bf" fontSize={11} />
              <YAxis stroke="#93a5bf" fontSize={12} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#1c2434', border: '1px solid #2b3850', borderRadius: 10 }} />
              <Line type="monotone" dataKey="value" stroke="#46d9a3"
                strokeWidth={2.2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState emoji="📡" title="Nothing on the wire yet">
            <p>{isAdmin
              ? 'Press “Start simulator” above and readings will appear here within seconds.'
              : 'An admin needs to start the simulator — once running, live data paints this chart in real time.'}</p>
          </EmptyState>
        )}
      </div>

      <div className="card">
        <h3>Latest readings ({readings.length})</h3>
        {readings.length === 0 ? (
          <p className="muted">No live readings buffered yet — they appear here the
            moment the simulator starts.</p>
        ) : (
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
        )}
      </div>
    </div>
  )
}
