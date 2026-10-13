import { useState } from "react";
import { Download, Printer, TriangleAlert } from "lucide-react";
import { ContextChart, MetricChart, PrimaryChart } from "./Charts.jsx";
import { fmtDate, ramp } from "../utils.js";

function Stripes({ rows, display }) {
  const key = display.primary.key;
  const max = Math.max(1, ...rows.map((r) => r[key]));
  return (
    <figure className="stripes-wrap">
      <div className="stripes" role="img" aria-label={`One stripe per year, a stronger colour means more ${display.primary.noun}`}>
        {rows.map((r) => (
          <div
            key={r.year}
            className="stripe"
            style={{ background: ramp(display.palette, r[key] / max), opacity: r.low_coverage ? 0.35 : 1 }}
            title={`${r.year}: ${r[key]} ${display.primary.noun}${r.low_coverage ? " (incomplete data)" : ""}`}
          />
        ))}
      </div>
      <figcaption>
        <span>{rows[0].year}</span>
        <span>Each stripe is a year. The stronger the colour, the more {display.primary.noun} it had.</span>
        <span>{rows[rows.length - 1].year}</span>
      </figcaption>
    </figure>
  );
}

function Facts({ data }) {
  const { yearly: rows, display } = data;
  const key = display.primary.key;
  const longest = data.events.reduce((best, e) => (!best || e.duration > best.duration ? e : best), null);
  const slope = data.trend.mann_kendall.sens_slope;
  const facts = [
    { value: rows.reduce((a, r) => a + r.events, 0), label: display.event_label },
    { value: rows.reduce((a, r) => a + r[key], 0), label: display.total_label },
    { value: longest ? `${longest.duration} ${display.duration_unit}` : "none", label: longest ? `longest, from ${fmtDate(longest.start, display.date_precision)}` : "no events in this range" },
    { value: `${slope >= 0 ? "+" : ""}${slope.toFixed(2)}`, label: `${display.primary.label.toLowerCase()} per year (Sen's slope)` },
    { value: `${data.quality.coverage_pct}%`, label: "of days had usable data" },
  ];
  return (
    <dl className="facts">
      {facts.map((f) => (
        <div key={f.label}><dd>{f.value}</dd><dt>{f.label}</dt></div>
      ))}
    </dl>
  );
}

export default function Results({ data, csvHref }) {
  const { insight, region, params, trend, display } = data;
  const [metric, setMetric] = useState(display.metrics[0].key);
  const activeMetric = display.metrics.find((m) => m.key === metric) || display.metrics[0];
  const sortKey = display.event_sort;
  const topEvents = [...data.events].sort((a, b) => b[sortKey] - a[sortKey] || b.duration - a.duration).slice(0, 10);

  return (
    <article className="results">
      <header className="hero">
        <h1>{region.name}</h1>
        <p className="headline">{insight.headline}</p>
        <div className="badges">
          <span className={`badge ${insight.significant ? "sig" : "nosig"}`}>
            {insight.significant ? "Statistically significant trend" : "Trend not statistically significant"}
          </span>
          <span className="badge plain">{display.label}, {params.start_year} to {params.end_year}</span>
          <span className="badge plain">{display.definition}</span>
        </div>
        {insight.detail && <p className="detail">{insight.detail}</p>}
        <Stripes rows={data.yearly} display={display} />
        <div className="actions no-print">
          <a className="btn ghost" href={csvHref} download><Download size={16} aria-hidden="true" /> Download CSV</a>
          <button className="btn ghost" type="button" onClick={() => window.print()}><Printer size={16} aria-hidden="true" /> Save as PDF</button>
        </div>
      </header>

      <Facts data={data} />

      <section className="panel">
        <div className="panel-head">
          <h2>{display.primary.label} each year</h2>
          <p>Bars are grey where a year had too little valid data. Those years are left out of the trend.</p>
        </div>
        <div className="chart tall"><PrimaryChart rows={data.yearly} display={display} /></div>
        <p className="foot">
          Linear fit: {trend.linear.slope >= 0 ? "+" : ""}{trend.linear.slope.toFixed(2)} a year (R² {trend.linear.r2}).
          Mann-Kendall: {trend.mann_kendall.trend}, tau {trend.mann_kendall.tau}, p {trend.mann_kendall.p_value}.
        </p>
      </section>

      <div className="two">
        <section className="panel">
          <div className="panel-head">
            <h2>{activeMetric.label} by year</h2>
            <div className="seg small" role="group" aria-label="Metric">
              {display.metrics.map((m) => (
                <button key={m.key} type="button" className={activeMetric.key === m.key ? "on" : ""} onClick={() => setMetric(m.key)}>{m.label}</button>
              ))}
            </div>
          </div>
          <div className="chart"><MetricChart rows={data.yearly} metric={activeMetric.key} display={display} /></div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>{data.context.title}</h2>
            <p>{data.context.caption}</p>
          </div>
          <div className="chart"><ContextChart context={data.context} display={display} /></div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>{display.events_title}</h2>
          <p>Up to ten events in the range, ranked by {display.event_sort_label}.</p>
        </div>
        {topEvents.length === 0 ? (
          <p className="empty">No events met the definition in this range. Try a longer range or a different region.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Started</th><th>Ended</th><th className="num">{display.duration_unit === "months" ? "Months" : "Days"}</th>
                  {display.event_columns.map((c) => <th key={c.key} className="num">{c.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {topEvents.map((e) => (
                  <tr key={e.start}>
                    <td>{fmtDate(e.start, display.date_precision)}</td>
                    <td>{fmtDate(e.end, display.date_precision)}</td>
                    <td className="num">{e.duration}</td>
                    {display.event_columns.map((c) => <td key={c.key} className="num">{c.prefix}{e[c.key]}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel method">
        <h2>How to read this honestly</h2>
        <p>{display.method}</p>
        <ul className="caveats">
          {insight.caveats.map((c) => (
            <li key={c}><TriangleAlert size={15} aria-hidden="true" /><span>{c}</span></li>
          ))}
        </ul>
        <p className="source">
          Data: Open-Meteo Historical Weather API (ERA5 reanalysis), cleaned: {data.quality.outliers_removed} outlier values removed,{" "}
          {data.quality.short_gaps_filled} short gaps filled, {data.quality.missing_days} days still missing.
        </p>
      </section>
    </article>
  );
}
