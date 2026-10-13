// One colour ramp per hazard, pale to intense: heat is gold to plum, drought is sand to umber, rain is ice to indigo.
const RAMPS = {
  heat: [[255, 233, 168], [255, 179, 71], [255, 106, 61], [214, 32, 74], [122, 27, 109]],
  dry: [[250, 238, 200], [232, 190, 110], [196, 128, 52], [140, 72, 32], [84, 38, 24]],
  rain: [[206, 238, 255], [110, 196, 244], [48, 128, 226], [46, 78, 196], [66, 36, 140]],
};

export function ramp(palette, t) {
  const stops = RAMPS[palette] || RAMPS.heat;
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

export const fmtDate = (iso, precision = "day") =>
  new Date(iso + "T00:00:00").toLocaleDateString(
    "en-GB",
    precision === "month" ? { month: "short", year: "numeric" } : { day: "numeric", month: "short", year: "numeric" },
  );

export const fmtCoord = (lat, lon) =>
  `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;
