import { useEffect, useMemo, useState } from "react";
import { getSummary } from "../api/client.js";

function money(n) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n ?? 0);
}

const W = 640;
const H = 190;
const PAD = 8;

function LineChart({ byDay }) {
  const entries = Object.entries(byDay).sort(([a], [b]) => (a < b ? -1 : 1));
  if (entries.length === 0) return null;

  const max = Math.max(...entries.map(([, v]) => v), 1);
  const stepX = entries.length > 1 ? (W - PAD * 2) / (entries.length - 1) : 0;
  const pts = entries.map(([, v], i) => [
    PAD + i * stepX,
    H - 26 - (v / max) * (H - 50),
  ]);
  const path = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${path} L${pts[pts.length - 1][0].toFixed(1)},${H - 20} L${pts[0][0].toFixed(1)},${H - 20} Z`;

  return (
    <svg className="line-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Daily spend line chart">
      {[0.25, 0.5, 0.75].map((f) => (
        <line
          key={f}
          x1={PAD}
          x2={W - PAD}
          y1={H - 26 - f * (H - 50)}
          y2={H - 26 - f * (H - 50)}
          stroke="rgba(61,36,101,0.45)"
          strokeDasharray="3 5"
        />
      ))}
      <path d={area} fill="rgba(107,63,160,0.14)" />
      <path d={path} fill="none" stroke="#6B3FA0" strokeWidth="2" />
      {entries[entries.length - 1] && (
        <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="3.5" fill="#C9A227" />
      )}
      <text x={PAD} y={H - 6} fill="#9C93B5" fontSize="11" fontFamily="IBM Plex Mono, monospace">
        {entries[0][0]}
      </text>
      <text x={W - PAD} y={H - 6} textAnchor="end" fill="#9C93B5" fontSize="11" fontFamily="IBM Plex Mono, monospace">
        {entries[entries.length - 1][0]}
      </text>
    </svg>
  );
}

export default function AnalyticsDashboard({ dataVersion }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getSummary()
      .then(setSummary)
      .catch((e) => setError(e.message));
  }, [dataVersion]);

  const monthKey = new Date().toISOString().slice(0, 7);

  const monthSpend = useMemo(() => {
    if (!summary) return 0;
    return Object.entries(summary.by_day || {})
      .filter(([d]) => d.startsWith(monthKey))
      .reduce((acc, [, v]) => acc + v, 0);
  }, [summary, monthKey]);

  if (error)
    return (
      <section>
        <h1 className="view-title">Dashboard</h1>
        <div className="error-note">{error}</div>
      </section>
    );

  if (!summary)
    return (
      <section>
        <h1 className="view-title">Dashboard</h1>
        <p className="empty-note">Opening the ledger…</p>
      </section>
    );

  const categories = Object.entries(summary.by_category || {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8);
  const maxCat = categories.length ? categories[0][1] : 1;

  const merchants = Object.entries(summary.by_merchant || {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  return (
    <section>
      <h1 className="view-title">Dashboard</h1>
      <p className="view-lede">Every receipt in the ledger, weighed and totaled.</p>

      <div className="plate">
        <p className="plate-label">Total spend on record</p>
        <p className="plate-figure">{money(summary.total_spend)}</p>
        <p className="plate-caption">
          Across {summary.receipt_count} {summary.receipt_count === 1 ? "receipt" : "receipts"} ·
          {" "}{summary.needs_review_count} flagged for review
        </p>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <p className="stat-label">This month ({monthKey})</p>
          <p className="stat-value">{money(monthSpend)}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Average per receipt</p>
          <p className="stat-value">
            {money(summary.receipt_count ? summary.total_spend / summary.receipt_count : 0)}
          </p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Flagged for review</p>
          <p className="stat-value">{summary.needs_review_count}</p>
        </div>
      </div>

      <div className="dash-grid">
        <div className="dash-panel wide">
          <p className="section-label">Daily spend</p>
          {Object.keys(summary.by_day || {}).length > 0 ? (
            <LineChart byDay={summary.by_day} />
          ) : (
            <p className="empty-note">No receipts in range yet.</p>
          )}
        </div>

        <div className="dash-panel">
          <p className="section-label">Spend by category</p>
          {categories.length > 0 ? (
            <div className="bar-list">
              {categories.map(([name, val], i) => (
                <div key={name} className="bar-row">
                  <span className="bar-name">{name}</span>
                  <span className="bar-track">
                    <span
                      className={`bar-fill${i === 0 ? " top" : ""}`}
                      style={{ width: `${Math.max((val / maxCat) * 100, 2)}%` }}
                    />
                  </span>
                  <span className="bar-amount">{money(val)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-note">No categorized items yet.</p>
          )}
        </div>

        <div className="dash-panel">
          <p className="section-label">Top merchants</p>
          {merchants.length > 0 ? (
            <ol className="merchant-list">
              {merchants.map(([name, val], i) => (
                <li key={name} className="merchant-row">
                  <span className="merchant-rank">{String(i + 1).padStart(2, "0")}</span>
                  <span className="merchant-name">{name}</span>
                  <span className="merchant-amount">{money(val)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="empty-note">No merchants yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}
