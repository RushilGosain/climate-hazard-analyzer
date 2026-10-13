# Heatline: Climate Hazard Trend Analyzer

Heatline answers one question for any place on Earth: **are heatwaves getting more frequent, longer or more intense, and is that change real or just noise?** You pick a city, a point on the map or a latitude/longitude box, choose a time range, and get yearly charts, a Mann-Kendall trend test and a plain-language summary that says so honestly when a trend is not statistically significant.

> Live app: `ADD_DEPLOYED_URL`  
> API: `ADD_BACKEND_URL/api/health`  
> Demo video (optional): `ADD_LOOM_LINK`

## What it does

Three hazards work end to end, and heatwave is selected by default: **heatwave** (from daily maximum temperature), **drought** (a rainfall deficit index) and **heavy rainfall** (extreme daily rainfall). They share one pipeline, one database layout and one set of charts, and each hazard describes its own labels, definitions and caveats in the JSON it returns, so the interface adapts without hazard-specific screens.

The frontend lets you search a city or state, click a Leaflet map to drop a point or draw a lat/lon box, and pick a time range of 10 to 45 years. It shows a "warming stripes" band for the whole range, five headline facts, a chart of the main yearly metric with a 5-year average and linear trend, a switchable chart for three secondary metrics, a context chart (the seasonal temperature threshold, the drought index through time, or heavy rain by month), a table of the biggest events, and a short methodology note with caveats. CSV export and print-to-PDF are included (bonus items), as are the map UI and Mann-Kendall trend test.

## Architecture

```
React (Vite)  ──GET /api/...──>  Flask API  ──>  MongoDB (daily_series cache, analyses)
 Leaflet map                      validation        ^
 Chart.js                         rate limits       |  miss: fetch once
                                  HTTP cache        +──> Open-Meteo archive + geocoding
```

A request for a place and range works like this. The API validates every input. It checks MongoDB for a finished analysis for that grid cell, range and method version. If one exists it is returned straight away. If not, the pipeline looks for the cell's raw daily temperature series in MongoDB, fetches it from Open-Meteo only if the series is missing or too short, cleans it, computes thresholds, detects events, fits trends, stores the analysis, and then reads it back from the database to answer the request. A repeat request for the same place is therefore a database read with no network call.

Two MongoDB collections hold everything. `series_cache` has one document per 0.25 degree grid cell and weather variable with the raw daily array (temperature, or precipitation, which drought and heavy rainfall share), and `analyses` has one document per hazard, cell, range and method version with yearly metrics, events, trend statistics, insight text and chart data. Nearby clicks snap to the same cell, which is what makes the cache effective, and drought plus heavy rainfall for the same place download rainfall only once.

```
backend/
  app.py              routes, input validation, error handling, security headers
  config.py           all settings, overridable by environment variables
  db.py               MongoDB connection and indexes
  wsgi.py             gunicorn entry point
  services/
    openmeteo.py      defensive client for the weather and geocoding APIs
    heatwave.py       temperature cleaning, percentile thresholds, event detection
    drought.py        monthly rainfall, SPI-3, drought events
    rainfall.py       rainfall cleaning, heavy-day threshold, Rx1day, Rx5day, spells
    trends.py         Mann-Kendall, Sen's slope, linear fit, plain-language insight (shared)
    pipeline.py       ingest, cache, dispatch to a hazard module, store, read back
  tests/test_core.py  18 tests, run fully offline
frontend/src/
  App.jsx             layout, state, controls
  components/         RegionPicker (map and search), Charts, Results
```

## Data source

Daily maximum 2 m temperature (heatwave) and daily precipitation sum (drought and heavy rainfall) come from the **Open-Meteo Historical Weather API**, which serves ERA5 reanalysis data from 1940 onward at about 10 km resolution. It needs no API key for non-commercial use. Place search uses the Open-Meteo Geocoding API. Open-Meteo is a modelled reanalysis, not a weather station record, and the README and the app both say so.

## Hazard logic

A day is **hot** when its daily maximum temperature is above the 95th percentile for that calendar day. The percentile uses the 1991 to 2020 baseline (the WMO standard normal period) and a 15 day window centred on the day, so each threshold is built from roughly 450 values and follows the seasons smoothly. A **heatwave** is a run of three or more consecutive hot days, attributed to the year it starts in. Per year the app records the number of events, total heatwave days, longest event, average duration and mean intensity (how many degrees above the threshold the hot days were).

Calendar days are mapped on a leap-year calendar so that 1 March always lines up between leap and non-leap years, and the window wraps around New Year.

### Drought

Drought is measured with the **Standardised Precipitation Index over 3 months (SPI-3)**. Daily rainfall is summed per month (months with under 90% valid days are discarded, the rest scaled up for the missing days), then summed over a rolling 3 month window. Each window is ranked against the same calendar months in 1991 to 2020 and the percentile is converted to a z-score. Zero is normal, below -1 is drought, below -2 is extreme. A drought event is two or more such months in a row, counted in the year it starts. Ranking instead of fitting a gamma distribution is a deliberate choice: it needs no extra library and copes with months that are often completely dry. The yearly metrics are drought months, events, longest event, severity and worst SPI. SPI uses rainfall only, so it cannot see heat-driven drought, and the app says so.

### Heavy rainfall

Heavy rainfall follows the ETCCDI R95p convention. A wet day has at least 1 mm. A heavy rainfall day is a wet day above the 95th percentile of all wet days in 1991 to 2020, a single threshold in millimetres that is shown in the interface. Back-to-back heavy days are merged into one spell. The yearly metrics are heavy rainfall days, Rx1day (wettest day), Rx5day (wettest five days), and the share of annual rain that fell on heavy days. Places with almost no wet days (deserts) are rejected with a clear message instead of a meaningless result.

## Handling noisy data

Real data is messy, so the series is cleaned before any statistics are computed. For temperature, values outside -60 to 60 °C are treated as invalid, values that jump more than 25 °C away from the 7 day rolling median are treated as glitches, gaps of up to two days are filled by interpolation, and longer gaps are left empty on purpose because inventing data would bias the trend. For rainfall, negative values and anything above 1,500 mm a day are removed, and gaps are never interpolated because rain does not change smoothly. In both cases missing days are made explicit by reindexing to a full daily calendar. A missing day breaks a heatwave run, which is the conservative choice. Any year with too little valid data (under 90% of days, or under 75% of months for drought) is flagged in the chart and left out of the trend, and the response reports outliers removed, gaps filled and coverage.

## Trend analysis and honest insight

The trend metric is the main yearly count (heatwave days, drought months or heavy rainfall days). The app reports a **Mann-Kendall test** with tie correction and **Sen's slope**, which suit skewed, zero-heavy counts better than ordinary regression, plus a simple linear fit and a 5-year rolling mean for the chart. The headline compares the first and last ten usable years. If the Mann-Kendall p-value is 0.05 or higher, the headline says the change is not statistically significant instead of presenting a percentage as fact. Caveats are generated with every result: the baseline overlap, the reanalysis-versus-station difference, hazard-specific limits (SPI ignores evaporation, gridded rainfall understates cloudbursts), a warning when the early average is so small that percentage changes mislead, and any years excluded for poor coverage.

## API reference

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | Liveness check, exempt from rate limits |
| `GET /api/meta` | Available hazards, year limits, baseline, box size limit |
| `GET /api/geocode?q=Delhi` | Place search through Open-Meteo, cached for 24 hours |
| `GET /api/hazards/{hazard}?lat=28.61&lon=77.21&start=1990&end=2025&name=Delhi` | Full analysis as JSON. `{hazard}` is `heatwave`, `drought` or `heavy_rain`. Use `south`, `west`, `north`, `east` instead of `lat` and `lon` for a box |
| `GET /api/hazards/{hazard}/export.csv?...` | Yearly metrics as CSV, same parameters |

An unknown hazard returns 404. Every hazard returns the same top-level shape (`yearly`, `events`, `trend`, `insight`, `quality`, `display`, `context`), which is why one frontend renders all three. To add a fourth hazard you write one module with an `analyze()` function and add one line to `HAZARDS` in `pipeline.py`.

For a latitude/longitude box the analysis uses the box centre (see assumptions).

## Security and performance

Every query parameter is validated for type, finiteness and range before use, the place name is stripped of unexpected characters, boxes are limited to 5 degrees and ranges to 10 to 45 years. Outbound calls go only to hard-coded Open-Meteo hosts, so users cannot make the server request arbitrary URLs. Upstream errors are retried with backoff, time out, and are never passed to the browser raw. Flask-Limiter applies a per-client limit (20 analyses a minute, 300 requests an hour by default, all configurable), CORS is limited to the configured frontend origin and to GET, and responses carry `nosniff`, `no-referrer` and a locked-down content security policy. Performance comes from three cache layers: Flask-Caching for identical requests, finished analyses in MongoDB, and raw series in MongoDB, which means each grid cell hits the weather API once.

## Setup

You need Python 3.11 or newer, Node.js 18 or newer, and either Docker, a free MongoDB Atlas cluster, or neither (see step 3).

**1. Get the code**

```bash
git clone <your-repo-url> climate-hazard-analyzer
cd climate-hazard-analyzer
```

**2. Install the backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

**3. Choose a database**

Option A, local MongoDB with Docker: from the project root run `docker compose up -d`. The default `MONGODB_URI` already points to it.

Option B, MongoDB Atlas: create a free M0 cluster, add a database user, allow your IP, and paste the connection string into `MONGODB_URI` in `backend/.env`.

Option C, no database at all for a quick look: set `USE_MOCK_DB=1` in `backend/.env`. Data lives in memory and is lost on restart.

If you ran an earlier version of this project against a real MongoDB, nothing needs migrating: the cache now lives in a new `series_cache` collection and old `analyses` documents are ignored because the method version changed.

**4. Run the backend** (from `backend/`)

```bash
python app.py                    # serves http://127.0.0.1:5000
```

Check `http://127.0.0.1:5000/api/health`.

**5. Run the frontend** (new terminal, from `frontend/`)

```bash
npm install
npm run dev                      # serves http://localhost:5173
```

Open `http://localhost:5173`. The first analysis of a new place downloads about 35 years of daily data and can take up to a minute. After that it is instant, and switching between drought and heavy rainfall for the same place reuses the same rainfall download. Clicking a hazard in the sidebar runs the analysis immediately.

**6. Run the tests** (from `backend/`)

```bash
pytest
```

The tests cover cleaning, heatwave, drought and heavy rainfall detection (each with an injected known event), the Mann-Kendall test, all three hazards through the full API with a mocked weather source, the database cache (a second request, or the other rainfall hazard, makes no upstream call), and rejection of bad input.

## Map setup and troubleshooting

The map is built with **Leaflet** (the mapping engine) and **react-leaflet** (the React wrapper). It needs no API key and no account. Background tiles come from CARTO's dark basemap, built on OpenStreetMap data, and attribution is displayed on the map as their terms require.

**What you must have for the map to appear**

1. The packages installed: `npm install leaflet react-leaflet@4` (version 4 matches React 18, which this project uses).
2. Leaflet's stylesheet imported once, which is already done in `frontend/src/main.jsx` with `import "leaflet/dist/leaflet.css";`. Without it the map shows as a scrambled pile of image tiles.
3. A container with a real height. Leaflet draws into a box and cannot size it for you. Here the box is `.map` in `styles.css` (260 px) and the map fills it.
4. Internet access to the tile servers, because the tiles are images fetched live from the web.

**If you see a problem**

| What you see | Cause and fix |
| --- | --- |
| Nothing where the map should be | The container has no height, or `leaflet.css` is not imported. Check points 2 and 3 above |
| Grey squares or a broken jigsaw of tiles | The map was measured before the layout settled. The app already re-measures on resize, so a hard refresh (Ctrl+Shift+R) normally fixes stale cache |
| Map frame loads but no streets | Tiles are blocked by an ad blocker, VPN, school or office firewall. The app automatically retries with standard OpenStreetMap tiles, and if those fail too it shows a message. Try another network or disable the blocker for `localhost` |
| Console error about `useContext` or "Cannot read properties of null" | react-leaflet and React versions do not match. React 18 needs `react-leaflet@4`, React 19 needs `react-leaflet@5` |
| Nothing happens when you click | In Point mode one click selects. In Lat/lon box mode you click two opposite corners, and boxes over 5 degrees on a side are refused with a message under the search box |
| Works locally but not after deploying | Open the browser console. A blocked request means a content-security-policy or mixed-content problem: the site must be https and must allow images from `*.basemaps.cartocdn.com` and `tile.openstreetmap.org` |

The sidebar also has **Type coordinates instead**, which accepts a latitude and longitude (or a box) directly, so the app is fully usable even if map tiles can never load on your network.

If you later want Mapbox, you would create a Mapbox account, get a public access token, put it in `frontend/.env` as `VITE_MAPBOX_TOKEN`, and swap the `TileLayer` URL in `RegionPicker.jsx` for the Mapbox tile URL. It is not required for this project.

## Libraries, packages and APIs

### Backend (Python)

Install everything at once with `pip install -r requirements.txt`. Or one by one, with what each is for:

```bash
pip install Flask flask-cors Flask-Caching Flask-Limiter pymongo numpy pandas requests python-dotenv gunicorn mongomock pytest
```

| Package | What it does here |
| --- | --- |
| Flask | The web framework: routes, JSON responses, error handlers |
| flask-cors | CORS. Browsers block a frontend on one address (`localhost:5173`, or your Vercel URL) from calling an API on another (`localhost:5000`, or your Render URL) unless the API says it is allowed. This package adds those permission headers, and we restrict it to your frontend's origin and to GET requests |
| python-dotenv | Reads the `backend/.env` file into environment variables so settings like the database URL stay out of the code and out of GitHub |
| Flask-Caching | Remembers responses for identical requests for an hour |
| Flask-Limiter | Rate limiting, so one visitor cannot hammer the API or burn the weather API quota |
| pymongo | The MongoDB driver |
| numpy and pandas | Time-series handling: gaps, rolling windows, percentiles, resampling to months |
| requests | Calls to the Open-Meteo APIs, with retries and timeouts |
| gunicorn | The production server used on Render (Flask's built-in server is for development only) |
| mongomock | A fake in-memory MongoDB, used by the tests and by the `USE_MOCK_DB=1` quick start |
| pytest | Test runner |

### Frontend (JavaScript)

Install everything at once with `npm install` inside `frontend/`. Or one by one:

```bash
npm install react@18 react-dom@18 leaflet react-leaflet@4 chart.js react-chartjs-2 lucide-react
npm install -D vite @vitejs/plugin-react
```

| Package | What it does here |
| --- | --- |
| react, react-dom | The UI library |
| vite and @vitejs/plugin-react | Dev server and production build. In development Vite also proxies `/api` calls to Flask, which is why no CORS setup is needed locally |
| chart.js and react-chartjs-2 | All charts |
| leaflet and react-leaflet | The map (see the map section above) |
| lucide-react | Icons |

Fonts (Bricolage Grotesque and Public Sans) load from Google Fonts in `index.html`.

### External services and keys

| Service | Used for | Key needed |
| --- | --- | --- |
| Open-Meteo Historical Weather API (`archive-api.open-meteo.com`) | Daily maximum temperature and daily precipitation | No for non-commercial use. For commercial use buy a plan and put the key in `OPEN_METEO_API_KEY` |
| Open-Meteo Geocoding API (`geocoding-api.open-meteo.com`) | City and state search | No |
| MongoDB Atlas (free M0 cluster) | Production database | A connection string in `MONGODB_URI` |
| CARTO and OpenStreetMap tile servers | Map background | No, attribution is shown on the map |
| Render and Vercel (or Netlify) | Hosting the backend and frontend | Free accounts |

### Environment variables

Backend (`backend/.env`, copied from `.env.example`): `MONGODB_URI`, `MONGODB_DB`, `USE_MOCK_DB`, `CORS_ORIGINS`, `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_ANALYZE`, `CACHE_TTL_SECONDS`, `OPEN_METEO_API_KEY`. Only `MONGODB_URI` and `OPEN_METEO_API_KEY` are secrets. Never commit `.env` (it is in `.gitignore`).

Frontend (`frontend/.env`): `VITE_API_URL`, empty in development and your backend URL in production. Anything in a `VITE_` variable is visible to every visitor, so never put a secret in it.

## Deployment

**Database:** create an Atlas M0 cluster, add a user, and allow network access from anywhere (`0.0.0.0/0`) because free hosting has no fixed IP.

**Backend on Render (free web service):** set the root directory to `backend`, build command `pip install -r requirements.txt`, start command `gunicorn wsgi:app --workers 1 --threads 4 --timeout 120`. Add the environment variables `PYTHON_VERSION=3.12.3`, `MONGODB_URI` and `CORS_ORIGINS` (your frontend URL, no trailing slash). One worker is deliberate: the rate limiter and HTTP cache are in-process, and a multi-worker setup would need Redis for both. Free instances sleep when idle, so the first request after a pause is slow.

**Frontend on Vercel or Netlify:** set the root directory to `frontend`, build command `npm run build`, output directory `dist`, and the environment variable `VITE_API_URL` to your Render URL with no trailing slash. Deploy the backend first so you have the URL.

Then paste both URLs at the top of this file.

## Assumptions

Drought and heavy rainfall use the same grid cell and 1991 to 2020 baseline as heatwave. A region given as a box or a state is analysed at its centre point, which is a single 0.25 degree cell, because one reliable series beats averaging many noisy ones within the time limit. Open-Meteo's daily maximum is taken in local time (`timezone=auto`). The latest complete calendar year is the end of the selectable range, because the archive lags real time by a few days. Percentile thresholds are always built from 1991 to 2020 regardless of the chosen range. Heatwaves are detected across the whole year rather than a hot season only.

## What I would improve with more time

Average a grid of points inside a box or state instead of using the centre. Add a warm-season-only option and a second definition for comparison (for example excess heat factor). Add evaporation to the drought index (SPEI) and a gamma-fitted SPI for comparison. Move rate limiting and caching to Redis so the API can run several workers. Compare ERA5 against station data where available. Add background jobs and a progress indicator for first-time fetches, request signing or an API key for the public endpoints, and end-to-end browser tests. Code-split the chart and map libraries to shrink the first load.

## AI tools used

I used **Claude (Anthropic)** to scaffold this project: the Flask API structure, the heatwave, drought and rainfall detection code, the React components and the stylesheet, and a first draft of this README. I then ran the tests, read through each module, and can explain and change any part of the code, including the percentile window, the cleaning rules, the Mann-Kendall implementation and the cache keys. *(Edit this paragraph so it describes exactly how you used AI, and say the same in the submission form.)*
