# Heatline: Climate Hazard Trend Analyzer

Heatline is a web application that analyzes historical climate data to identify whether heatwaves, droughts, and heavy rainfall events are becoming more frequent, longer, or more intense.

Users can search for a location, select a point on the map or a latitude/longitude box, and explore yearly trends with statistical analysis and clear, evidence-based insights.

**Live Demo:** https://climate-hazard-analyzer-one.vercel.app/  
**Backend API:** https://climate-hazard-analyzer-api.onrender.com/api/health 

**GitHub:** https://github.com/RushilGosain/climate-hazard-analyzer

## Features

- **Three climate hazards:** Heatwaves, drought, and heavy rainfall.
- **Interactive location selection:** Search for places, select map coordinates, or define a geographic box.
- **Historical analysis:** Explore trends across 10–45 years.
- **Visualizations:** Yearly charts, warming stripes, rolling averages, and major event summaries.
- **Statistical testing:** Mann-Kendall trend test, Sen's slope, and linear trend analysis.
- **Honest insights:** Highlights statistically insignificant trends and data-quality limitations.
- **Data export:** Download yearly metrics as CSV or print results to PDF.
- **Caching:** Stores raw weather series and completed analyses in MongoDB to reduce repeated API calls.

## Screenshots

Add four screenshots of the application below.

### 1. Main Dashboard
<img width="1470" height="806" alt="Screenshot 2026-10-13 at 1 54 03 PM" src="https://github.com/user-attachments/assets/073410c2-5d35-41c9-90d7-9c4e20459cfa" />


### 2. Climate Trend Analysis
<img width="1470" height="806" alt="Screenshot 2026-10-13 at 1 54 10 PM" src="https://github.com/user-attachments/assets/cbf8f43f-f811-46d6-844d-cf8a55979ac8" />


### 3. Hazard Comparison
<img width="1470" height="806" alt="Screenshot 2026-10-13 at 1 54 28 PM" src="https://github.com/user-attachments/assets/9483aa8c-67b6-43c9-8f0b-5e638d66de5a" />

<img width="1470" height="806" alt="Screenshot 2026-10-13 at 1 54 56 PM" src="https://github.com/user-attachments/assets/c1d8010b-7c9e-4d52-9709-30ea70b65fbe" />


## Tech Stack

- **Frontend:** React, Vite, Chart.js, Leaflet
- **Backend:** Python, Flask, NumPy, Pandas
- **Database:** MongoDB Atlas
- **Data APIs:** Open-Meteo Historical Weather API and Geocoding API
- **Deployment:** Vercel and Render

## Data Source

Heatline uses the **Open-Meteo Historical Weather API** for daily maximum temperature and precipitation data, along with the Open-Meteo Geocoding API for location search.

The weather data is based on ERA5 reanalysis. It represents modelled historical weather conditions rather than direct measurements from individual weather stations.

## Methodology

- **Heatwaves:** Detects runs of at least three consecutive days exceeding the calendar-day 95th percentile, using a 1991–2020 baseline.
- **Drought:** Uses the Standardised Precipitation Index over three months (SPI-3) to identify rainfall deficits.
- **Heavy rainfall:** Identifies extreme wet days using the 95th percentile of wet-day precipitation during 1991–2020.
- **Trend analysis:** Uses the Mann-Kendall test and Sen's slope to assess changes over time. Trends with a p-value of 0.05 or higher are reported as not statistically significant.

Data cleaning, missing-value handling, and coverage checks are applied before analysis. Results include relevant limitations and data-quality caveats.

## Architecture

1. The frontend sends location, hazard, and date-range parameters to the Flask API.
2. The backend checks MongoDB for cached weather data and completed analyses.
3. Missing historical data is fetched from Open-Meteo and processed by the relevant hazard module.
4. Results and trend statistics are stored in MongoDB and returned to the frontend.

## Running Locally

**Backend**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

**Frontend** — in a separate terminal:
```bash
cd frontend
npm install
npm run dev
```

Configure `MONGODB_URI` and other required backend environment variables in `backend/.env`. Set `VITE_API_URL` for the deployed frontend when running in production.

## Future Improvements

- Analyze multiple grid cells for regional averages.
- Add evaporation-sensitive drought metrics.
- Introduce background processing for first-time analyses.
- Expand automated testing and compare reanalysis data with station observations.
