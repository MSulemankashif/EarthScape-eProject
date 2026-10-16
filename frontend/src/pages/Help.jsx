/**
 * Help - in-app FAQs and mini-tutorials.
 * Satisfies the "user documentation: FAQs and tutorials" requirement
 * while staying one click away for real users.
 */
import { useState } from 'react'
import { PageHeader } from '../components/Layout.jsx'

const FAQ = [
  {
    q: 'I just logged in and the dashboard looks empty. What do I do?',
    a: <>Nothing is broken — the warehouse is waiting for its first pull of live
      weather. Click <strong>“☁ Sync live weather”</strong> on the Dashboard (a first
      sync also starts automatically). Real conditions for 12 Pakistani cities are
      fetched from OpenWeatherMap, cleaned, and stored in HDFS-partitioned folders —
      refresh afterwards and every chart fills in.</>,
  },
  {
    q: 'Where does the live data come from? Is it real?',
    a: <>It is real. The backend calls the <strong>OpenWeatherMap</strong> API
      (<code>/weather</code>, <code>/air_pollution</code>, <code>/forecast</code>) for
      12 cities, so temperatures, humidity, wind and PM2.5 are actual observations.
      Syncs run every 10 minutes automatically (plus on-demand), with a short cooldown
      protecting the free-tier quota of 60 calls/minute. Swap keys via the
      <code> OPENWEATHER_API_KEY</code> environment variable.</>,
  },
  {
    q: 'Why are CO₂ and sea level always “—”?',
    a: <>OpenWeatherMap has no outdoor CO₂ or sea-level sensor, so those columns are
      honestly stored as missing instead of being faked. The platform treats them the
      way it treats any missing reading: charts skip them, averages ignore them, and
      correlation analysis only uses metrics with real values.</>,
  },
  {
    q: 'How do I run the machine-learning models?',
    a: <>Open <strong>Analytics &amp; ML</strong> and press <strong>“Train ML models”</strong>.
      That fits the anomaly detector (Isolation Forest) plus linear trend models for
      metrics with enough live readings (temperature, rainfall…). Training takes a
      couple of seconds and the page shows how long it took and how fresh the model is.</>,
  },
  {
    q: 'What is the Live Weather page?',
    a: <>The real-time heart of the platform: current conditions for all 12 cities as
      live cards, a by-city comparison chart, and a detailed readings table. It
      refreshes every 30 seconds and the backend pulls fresh data every 10 minutes —
      or press <strong>“☁ Sync now”</strong>. Every reading is checked against your
      alert rules the moment it lands.</>,
  },
  {
    q: 'How do alerts work? Can I change the thresholds?',
    a: <>Each rule watches one metric with a threshold (for example
      <code> temperature_c &gt; 45 °C</code>). The engine evaluates every incoming reading
      against all enabled rules. Admins can add, edit, enable, disable and delete rules
      on the <strong>Alerts</strong> page — no code needed.</>,
  },
  {
    q: 'Who can see what?',
    a: <>Two roles exist. <strong>Admins</strong> manage users, alert rules, backups and
      the live data source. <strong>Analysts</strong> read data, run analytics,
      train models and file support tickets. Every API call checks your token’s role,
      so hiding buttons is not the only protection.</>,
  },
  {
    q: 'Where does the data actually live? Is Hadoop required?',
    a: <>By default the app runs in <em>simulation mode</em>: a local folder tree
      (<code>data/hdfs_sim/</code>) mirrors HDFS partitioning
      (<code>year=/month=/day=</code>). Set <code>EARTHSCAPE_MODE=hadoop</code> and the
      same code drives a real HDFS cluster through its CLI. Likewise
      <code>EARTHSCAPE_MONGO_URI</code> switches the document store to real MongoDB.</>,
  },
  {
    q: 'I typed the wrong password too many times and now I’m locked out.',
    a: <>That is the brute-force protection doing its job: five failed attempts lock the
      account for five minutes. Wait it out — the message tells you how long is left —
      then sign in carefully.</>,
  },
  {
    q: 'How do I back up my work?',
    a: <>Admins get a <strong>Back up now</strong> button on the Admin Console. It zips
      users, alerts, tickets, trained models, processed results and logs into
      <code>backups/</code>, keeps the newest 14 automatically, and can verify an
      archive’s integrity with one click.</>,
  },
  {
    q: 'Something looks wrong — how do I report it?',
    a: <>Open <strong>Support</strong>, pick a category (bug, question, idea…), describe
      what happened, and submit. Your ticket is stored with a status the team can track
      from open to resolved.</>,
  },
]

const TUTORIALS = [
  { icon: '①', title: 'Pull live weather', body: 'Dashboard → “☁ Sync live weather”. Real conditions for 12 cities land in seconds, then auto-refresh every 10 minutes.' },
  { icon: '②', title: 'Watch it live', body: 'Live Weather → city cards, comparison chart and full readings table — every row is checked against your alert rules on arrival.' },
  { icon: '③', title: 'Train & forecast', body: 'Analytics & ML → train models → open Forecasts for the real 5-day API forecast plus the model’s long-range projection.' },
  { icon: '④', title: 'Tune alert rules', body: 'Alerts → add a rule (metric, operator, threshold). The next matching live reading fires a notification.' },
]

export default function Help() {
  const [openIndex, setOpenIndex] = useState(0)

  return (
    <div>
      <PageHeader
        title="Help & FAQ"
        subtitle="Short answers to the questions we hear most — plus a 4-step tour if you are just getting started."
      />

      <div className="card">
        <h3>🚀 First-time tour</h3>
        <div className="steps">
          {TUTORIALS.map((t) => (
            <div className="step" key={t.title}>
              <span className="step-num" aria-hidden="true">{t.icon}</span>
              <strong>{t.title}</strong>
              <span>{t.body}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>❓ Frequently asked questions</h3>
        {FAQ.map((item, i) => {
          const open = openIndex === i
          return (
            <div className="faq-item" key={item.q}>
              <button className={`faq-q${open ? ' open' : ''}`}
                onClick={() => setOpenIndex(open ? -1 : i)}
                aria-expanded={open}>
                {item.q}
                <span className="chev" aria-hidden="true">▾</span>
              </button>
              {open && <div className="faq-a">{item.a}</div>}
            </div>
          )
        })}
      </div>

      <div className="card">
        <h3>⌨️ Keyboard tips & quick facts</h3>
        <p className="muted" style={{ lineHeight: 1.9 }}>
          <kbd>Tab</kbd> moves between controls, <kbd>Enter</kbd> submits forms ·
          Demo logins: <code>admin / admin@123</code> and <code>analyst / analyst@123</code> ·
          Backend health lives at <code>/api/health</code> ·
          All charts accept metric &amp; date filters — try changing them!
        </p>
        <p className="muted">
          Still stuck? Head to <strong>Support</strong> and open a ticket — it reaches
          the same team that maintains this platform.
        </p>
      </div>
    </div>
  )
}
