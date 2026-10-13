import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Rectangle, useMap, useMapEvents } from "react-leaflet";
import { BoxSelect, LoaderCircle, MapPin, Search } from "lucide-react";
import { geocode } from "../api.js";
import { fmtCoord } from "../utils.js";

const TILES = {
  carto: {
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  },
  osm: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
};

function MapClicks({ mode, corner, setCorner, onPick, maxBox, onWarn }) {
  useMapEvents({
    click({ latlng: { lat, lng } }) {
      onWarn("");
      if (mode === "point") {
        onPick({ name: `Point at ${fmtCoord(lat, lng)}`, lat, lon: lng, bbox: null });
      } else if (!corner) {
        setCorner([lat, lng]);
      } else {
        const s = Math.min(corner[0], lat), n = Math.max(corner[0], lat);
        const w = Math.min(corner[1], lng), e = Math.max(corner[1], lng);
        setCorner(null);
        if (n - s > maxBox || e - w > maxBox) return onWarn(`Keep the box under ${maxBox}° on each side.`);
        if (n - s < 0.05 || e - w < 0.05) return onWarn("That box is too small. Click two corners further apart.");
        onPick({ name: `Box around ${fmtCoord((s + n) / 2, (w + e) / 2)}`, lat: (s + n) / 2, lon: (w + e) / 2, bbox: [s, w, n, e] });
      }
    },
  });
  return null;
}

// Leaflet measures its container once. If the container changes size afterwards (layout shifts, fonts
// loading, window resize) the map shows grey blocks until it is told to re-measure. This does that.
function KeepSized() {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    const fix = () => map.invalidateSize();
    const timer = setTimeout(fix, 150);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(fix) : null;
    ro?.observe(el);
    window.addEventListener("resize", fix);
    return () => { clearTimeout(timer); ro?.disconnect(); window.removeEventListener("resize", fix); };
  }, [map]);
  return null;
}

function Fly({ region }) {
  const map = useMap();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (region.bbox) {
      const [s, w, n, e] = region.bbox;
      map.fitBounds([[s, w], [n, e]], { maxZoom: 7, padding: [24, 24] });
    } else {
      map.flyTo([region.lat, region.lon], Math.max(map.getZoom(), 6), { duration: 0.8 });
    }
  }, [region]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function ManualCoords({ mode, maxBox, onPick, onWarn }) {
  const [v, setV] = useState({ lat: "", lon: "", south: "", west: "", north: "", east: "" });
  const set = (k) => (e) => setV({ ...v, [k]: e.target.value });
  function submit(e) {
    e.preventDefault();
    const n = Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x === "" ? NaN : Number(x)]));
    if (mode === "point") {
      if (!(Math.abs(n.lat) <= 90) || !(Math.abs(n.lon) <= 180)) return onWarn("Latitude must be -90 to 90 and longitude -180 to 180.");
      return onPick({ name: `Point at ${fmtCoord(n.lat, n.lon)}`, lat: n.lat, lon: n.lon, bbox: null });
    }
    const { south: s, west: w, north: no, east: ea } = n;
    if (![s, w, no, ea].every(Number.isFinite) || no <= s || ea <= w || Math.abs(s) > 90 || Math.abs(no) > 90 || Math.abs(w) > 180 || Math.abs(ea) > 180)
      return onWarn("Enter a valid box: north above south, east right of west.");
    if (no - s > maxBox || ea - w > maxBox) return onWarn(`Keep the box under ${maxBox}° on each side.`);
    onPick({ name: `Box around ${fmtCoord((s + no) / 2, (w + ea) / 2)}`, lat: (s + no) / 2, lon: (w + ea) / 2, bbox: [s, w, no, ea] });
  }
  const field = (k, label) => (
    <label key={k}>{label}<input type="number" step="any" value={v[k]} onChange={set(k)} /></label>
  );
  return (
    <details className="manual">
      <summary>Type coordinates instead</summary>
      <form onSubmit={submit}>
        <div className="fields">
          {mode === "point" ? [field("lat", "Latitude"), field("lon", "Longitude")] : [field("south", "South"), field("north", "North"), field("west", "West"), field("east", "East")]}
        </div>
        <button className="btn ghost" type="submit">Use these coordinates</button>
      </form>
    </details>
  );
}

export default function RegionPicker({ region, onPick, maxBox = 5 }) {
  const [mode, setMode] = useState("point");
  const [corner, setCorner] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [note, setNote] = useState("");
  const [tiles, setTiles] = useState("carto");
  const [tilesFailed, setTilesFailed] = useState(false);
  const errors = useRef(0);

  function onTileError() {
    errors.current += 1;
    if (errors.current < 6) return;
    if (tiles === "carto") { errors.current = 0; setTiles("osm"); } else setTilesFailed(true);
  }

  async function search(e) {
    e.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true);
    setNote("");
    try {
      const { results } = await geocode(query.trim());
      setResults(results);
      if (!results.length) setNote("No places matched. Try a nearby city name.");
    } catch (err) {
      setNote(err.message);
    } finally {
      setSearching(false);
    }
  }

  function choose(r) {
    setMode("point");
    setResults(null);
    setQuery("");
    onPick({ name: [r.name, r.admin1, r.country].filter(Boolean).join(", "), lat: r.lat, lon: r.lon, bbox: null });
  }

  return (
    <div className="picker">
      <form className="search" onSubmit={search} role="search">
        <Search size={16} aria-hidden="true" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search a city or state" aria-label="Search for a city or state" maxLength={80} />
        <button type="submit" disabled={searching} aria-label="Search">{searching ? <LoaderCircle size={16} className="spin" /> : "Find"}</button>
      </form>

      {results && results.length > 0 && (
        <ul className="suggestions">
          {results.map((r, i) => (
            <li key={i}>
              <button type="button" onClick={() => choose(r)}>
                <strong>{r.name}</strong>
                <span>{[r.admin1, r.country].filter(Boolean).join(", ")}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {note && <p className="note" role="status">{note}</p>}

      <div className="seg" role="group" aria-label="Selection mode">
        <button type="button" className={mode === "point" ? "on" : ""} onClick={() => { setMode("point"); setCorner(null); }}><MapPin size={15} aria-hidden="true" /> Point</button>
        <button type="button" className={mode === "box" ? "on" : ""} onClick={() => { setMode("box"); setCorner(null); }}><BoxSelect size={15} aria-hidden="true" /> Lat/lon box</button>
      </div>

      <div className="map">
        <MapContainer center={[region.lat, region.lon]} zoom={6} minZoom={2} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }} worldCopyJump>
          <TileLayer key={tiles} url={TILES[tiles].url} attribution={TILES[tiles].attribution} eventHandlers={{ tileerror: onTileError }} />
          <KeepSized />
          <MapClicks mode={mode} corner={corner} setCorner={setCorner} onPick={onPick} maxBox={maxBox} onWarn={setNote} />
          <Fly region={region} />
          {region.bbox ? (
            <Rectangle bounds={[[region.bbox[0], region.bbox[1]], [region.bbox[2], region.bbox[3]]]} pathOptions={{ color: "#ff6a3d", weight: 2, fillOpacity: 0.12 }} />
          ) : (
            <CircleMarker center={[region.lat, region.lon]} radius={9} pathOptions={{ color: "#ffe9a8", weight: 2, fillColor: "#d6204a", fillOpacity: 0.95 }} />
          )}
          {corner && <CircleMarker center={corner} radius={6} pathOptions={{ color: "#ffe9a8", fillColor: "#ff6a3d", fillOpacity: 1 }} />}
        </MapContainer>
        {tilesFailed && <p className="map-fail" role="alert">Map tiles could not load. Check your connection or ad blocker, or type coordinates below.</p>}
      </div>
      <p className="hint">
        {mode === "box" ? (corner ? "Now click the opposite corner." : "Click one corner of the box, then the opposite corner.") : "Click anywhere on the map to analyse that spot. Use the + and - buttons to zoom."}
      </p>
      <ManualCoords mode={mode} maxBox={maxBox} onPick={onPick} onWarn={setNote} />
    </div>
  );
}
