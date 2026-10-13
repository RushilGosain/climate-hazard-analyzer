import { Chart } from "react-chartjs-2";
import {
  BarController, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend,
  LineController, LineElement, LinearScale, PointElement, Tooltip,
} from "chart.js";
import { ramp } from "../utils.js";

ChartJS.register(BarController, BarElement, CategoryScale, Filler, Legend, LineController, LineElement, LinearScale, PointElement, Tooltip);
ChartJS.defaults.color = "#98a0bd";
ChartJS.defaults.font.family = "'Public Sans', system-ui, sans-serif";
ChartJS.defaults.borderColor = "rgba(255,255,255,0.07)";

const tooltip = {
  backgroundColor: "#0c1021", borderColor: "rgba(255,255,255,0.15)", borderWidth: 1, padding: 10,
  titleColor: "#eef0f8", bodyColor: "#cfd4e8", cornerRadius: 8,
};
const legend = { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, padding: 18 } };

export function PrimaryChart({ rows, display }) {
  const key = display.primary.key;
  const max = Math.max(1, ...rows.map((r) => r[key]));
  const data = {
    labels: rows.map((r) => r.year),
    datasets: [
      {
        type: "bar", label: display.primary.label, data: rows.map((r) => r[key]),
        backgroundColor: rows.map((r) => (r.low_coverage ? "rgba(152,160,189,0.35)" : ramp(display.palette, r[key] / max))),
        borderRadius: 3, order: 3,
      },
      { type: "line", label: "5-year average", data: rows.map((r) => r.rolling_5y), borderColor: "#eef0f8", borderWidth: 2.5, pointRadius: 0, tension: 0.35, order: 1 },
      { type: "line", label: "Linear trend", data: rows.map((r) => r.trend_line), borderColor: "#ffb347", borderDash: [6, 5], borderWidth: 2, pointRadius: 0, order: 2 },
    ],
  };
  const options = {
    responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
    plugins: { legend, tooltip },
    scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } }, y: { beginAtZero: true, title: { display: true, text: display.primary.axis } } },
  };
  return <Chart type="bar" data={data} options={options} />;
}

export function MetricChart({ rows, metric, display }) {
  const def = display.metrics.find((m) => m.key === metric) || display.metrics[0];
  const values = rows.map((r) => r[def.key] ?? 0);
  const max = Math.max(1, ...values);
  const data = {
    labels: rows.map((r) => r.year),
    datasets: [{ label: def.label, data: values, backgroundColor: values.map((v) => ramp(display.palette, v / max)), borderRadius: 3 }],
  };
  const options = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip },
    scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } }, y: { beginAtZero: true, title: { display: true, text: def.unit } } },
  };
  return <Chart type="bar" data={data} options={options} />;
}

const MONTH_START = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function ContextChart({ context, display }) {
  if (context.type === "seasonal_line") {
    const data = {
      labels: context.values.map((_, i) => i),
      datasets: [{ label: context.series_label, data: context.values, borderColor: "#ff6a3d", backgroundColor: "rgba(255,106,61,0.14)", fill: true, pointRadius: 0, borderWidth: 2.5, tension: 0.3 }],
    };
    const options = {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { ...tooltip, callbacks: { title: (items) => { const d = items[0].dataIndex; const m = MONTH_START.filter((s) => s <= d).length - 1; return `${MONTHS[m]} ${d - MONTH_START[m] + 1}`; }, label: (c) => `${c.parsed.y} ${context.unit}` } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 0, callback: (_, i) => (MONTH_START.includes(i) ? MONTHS[MONTH_START.indexOf(i)] : "") } },
        y: { title: { display: true, text: context.unit } },
      },
    };
    return <Chart type="line" data={data} options={options} />;
  }

  if (context.type === "timeline_bars") {
    const data = {
      labels: context.labels,
      datasets: [{
        label: context.unit, data: context.values,
        backgroundColor: context.values.map((v) => (v === null ? "transparent" : v <= context.threshold ? ramp(display.palette, 0.75) : "rgba(152,160,189,0.45)")),
        borderWidth: 0, barPercentage: 1, categoryPercentage: 1,
      }],
    };
    const options = {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { ...tooltip, callbacks: { label: (c) => `${context.unit} ${c.parsed.y}` } } },
      scales: {
        x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 0, callback: (_, i) => (context.labels[i].endsWith("-01") && Number(context.labels[i].slice(0, 4)) % 5 === 0 ? context.labels[i].slice(0, 4) : "") } },
        y: { title: { display: true, text: context.unit } },
      },
    };
    return <Chart type="bar" data={data} options={options} />;
  }

  const max = Math.max(1, ...context.values);
  const data = {
    labels: context.labels,
    datasets: [{ label: context.unit, data: context.values, backgroundColor: context.values.map((v) => ramp(display.palette, v / max)), borderRadius: 4 }],
  };
  const options = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip },
    scales: { x: { grid: { display: false } }, y: { beginAtZero: true, title: { display: true, text: context.unit } } },
  };
  return <Chart type="bar" data={data} options={options} />;
}
