import { useCallback, useEffect, useMemo, useState } from "react";
import { CloudRain, Flame, LoaderCircle, Sun, TriangleAlert } from "lucide-react";
import RegionPicker from "./components/RegionPicker.jsx";
import Results from "./components/Results.jsx";
import { analyze, csvUrl, getMeta } from "./api.js";

const HAZARD_ICONS = { heatwave: Flame, drought: Sun, heavy_rain: CloudRain };
const DEFAULT_REGION = { name: "New Delhi, India", lat: 28.6139, lon: 77.209, bbox: null };

function toParams(region, range) {
  const p = { name: region.name, start: range.start, end: range.end };
  if (region.bbox) {
    const [south, west, north, east] = region.bbox;
    Object.assign(p, { south, west, north, east });
  } else {
    Object.assign(p, { lat: region.lat, lon: region.lon });
  }
  return p;
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [region, setRegion] = useState(DEFAULT_REGION);
  const [range, setRange] = useState({ start: 1990, end: 2025 });
  const [state, setState] = useState({ status: "loading" });
  const [hazard, setHazard] = useState("heatwave");
  const [last, setLast] = useState(null);

  const run = useCallback(async (r, rg, hz) => {
    const params = toParams(r, rg);
    setLast({ hazard: hz, params });
    setState({ status: "loading" });
    try {
      setState({ status: "done", data: await analyze(hz, params) });
    } catch (err) {
      setState({ status: "error", message: err.message });
    }
  }, []);

  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m);
        const rg = { start: 1990, end: m.max_year };
        setRange(rg);
        run(DEFAULT_REGION, rg, "heatwave");
      })
      .catch(() => setState({ status: "error", message: "Cannot reach the analysis server. Check that the backend is running." }));
  }, [run]);

  const years = useMemo(() => (meta ? Array.from({ length: meta.max_year - meta.min_year + 1 }, (_, i) => meta.max_year - i) : []), [meta]);
  const span = range.end - range.start + 1;
  const rangeError = meta && (span < meta.min_span_years ? `Pick at least ${meta.min_span_years} years.` : span > meta.max_span_years ? `Pick at most ${meta.max_span_years} years.` : "");

  return (
    <>
      <header className="topbar no-print">
        <div className="brand">
          <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#d6204a" /><path d="M6 21c3-7 5 5 10-2s6 3 10-5" stroke="#ffe9a8" strokeWidth="3" fill="none" strokeLinecap="round" /></svg>
          <span>Heatline</span>
        </div>
        <p>Are heatwaves getting more frequent where you live?</p>
      </header>

      <div className="shell">
        <aside className="controls no-print">
          <section>
            <h2>Region</h2>
            <p className="region-now">{region.name}</p>
            <RegionPicker region={region} onPick={setRegion} maxBox={meta?.max_bbox_deg ?? 5} />
          </section>

          <section>
            <h2>Hazard</h2>
            <div className="hazards" role="radiogroup" aria-label="Hazard type">
              {(meta?.hazards ?? [{ id: "heatwave", label: "Heatwave", enabled: true }]).map((h) => {
                const Icon = HAZARD_ICONS[h.id] ?? Flame;
                return (
                  <button
                    key={h.id} type="button" role="radio" aria-checked={hazard === h.id} disabled={!h.enabled || state.status === "loading"}
                    className={`hazard ${hazard === h.id ? "on" : ""}`}
                    onClick={() => { setHazard(h.id); if (!rangeError) run(region, range, h.id); }}
                  >
                    <Icon size={17} aria-hidden="true" /> {h.label}
                  </button>
                );
              })}
            </div>
          </section>

          <section>
            <h2>Time range</h2>
            <div className="range">
              <label>From
                <select value={range.start} onChange={(e) => setRange({ ...range, start: +e.target.value })}>
                  {[...years].reverse().map((y) => <option key={y}>{y}</option>)}
                </select>
              </label>
              <label>To
                <select value={range.end} onChange={(e) => setRange({ ...range, end: +e.target.value })}>
                  {years.map((y) => <option key={y}>{y}</option>)}
                </select>
              </label>
            </div>
            {rangeError && <p className="field-error" role="alert">{rangeError}</p>}
          </section>

          <button className="btn primary" type="button" disabled={!meta || !!rangeError || state.status === "loading"} onClick={() => run(region, range, hazard)}>
            {state.status === "loading" ? <><LoaderCircle size={17} className="spin" aria-hidden="true" /> Analysing</> : "Analyse"}
          </button>
        </aside>

        <main aria-live="polite">
          {state.status === "loading" && (
            <div className="loading">
              <div className="skeleton title" /><div className="skeleton line" /><div className="skeleton stripes-sk" />
              <p>Fetching daily temperatures and working out the thresholds. A new place can take up to a minute the first time, and is instant after that.</p>
            </div>
          )}
          {state.status === "error" && (
            <div className="error" role="alert">
              <TriangleAlert size={22} aria-hidden="true" />
              <div>
                <h2>The analysis did not finish</h2>
                <p>{state.message}</p>
                {meta && <button className="btn ghost" type="button" onClick={() => run(region, range, hazard)}>Try again</button>}
              </div>
            </div>
          )}
          {state.status === "done" && <Results key={state.data.display.id + state.data.region.name + state.data.params.start_year + state.data.params.end_year} data={state.data} csvHref={csvUrl(last.hazard, last.params)} />}
        </main>
      </div>

      <footer className="foot-bar no-print">
        Weather data from Open-Meteo (ERA5 reanalysis). Map tiles from OpenStreetMap contributors and CARTO.
      </footer>
    </>
  );
}
