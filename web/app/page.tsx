"use client";

import { useMemo, useState } from "react";

type Method = "corrected" | "raw_aurora" | "cams_forecast" | "persistence";

type CityForecast = {
  city: string;
  state: string;
  stations: number;
  support: "Higher" | "Moderate" | "Limited";
  note: string;
  series: Record<Method, number[]>;
};

const METHODS: { id: Method; label: string; short: string }[] = [
  { id: "corrected", label: "Locally adjusted", short: "Adjusted" },
  { id: "raw_aurora", label: "Raw Aurora", short: "Aurora" },
  { id: "cams_forecast", label: "Illustrative CAMS forecast", short: "CAMS (illustrative)" },
  { id: "persistence", label: "Persistence", short: "Persistence" },
];

const CITIES: CityForecast[] = [
  {
    city: "Varanasi",
    state: "Uttar Pradesh",
    stations: 4,
    support: "Moderate",
    note: "A held-out city used to test whether the method transfers beyond places it learned from.",
    series: {
      corrected: [108, 126, 142, 119],
      raw_aurora: [72, 83, 96, 81],
      cams_forecast: [68, 74, 79, 76],
      persistence: [104, 104, 104, 104],
    },
  },
  {
    city: "Kanpur",
    state: "Uttar Pradesh",
    stations: 3,
    support: "Limited",
    note: "Sparse monitoring makes forecast freshness and uncertainty especially important here.",
    series: {
      corrected: [132, 154, 171, 146],
      raw_aurora: [88, 101, 113, 98],
      cams_forecast: [84, 89, 94, 91],
      persistence: [128, 128, 128, 128],
    },
  },
  {
    city: "Patna",
    state: "Bihar",
    stations: 7,
    support: "Moderate",
    note: "One of the intended target cities for inexpensive, transparent multi-day forecasts.",
    series: {
      corrected: [118, 136, 149, 131],
      raw_aurora: [78, 91, 104, 89],
      cams_forecast: [73, 81, 87, 82],
      persistence: [112, 112, 112, 112],
    },
  },
  {
    city: "Lucknow",
    state: "Uttar Pradesh",
    stations: 6,
    support: "Moderate",
    note: "Recent station readings would support online local correction when the live feed is connected.",
    series: {
      corrected: [96, 111, 128, 114],
      raw_aurora: [69, 78, 89, 82],
      cams_forecast: [65, 72, 78, 75],
      persistence: [92, 92, 92, 92],
    },
  },
  {
    city: "Kolkata",
    state: "West Bengal",
    stations: 15,
    support: "Higher",
    note: "A fully held-out eastern metro that tests regional transfer rather than local memorisation.",
    series: {
      corrected: [74, 82, 93, 87],
      raw_aurora: [61, 68, 76, 71],
      cams_forecast: [57, 64, 69, 66],
      persistence: [71, 71, 71, 71],
    },
  },
  {
    city: "Bangalore",
    state: "Karnataka",
    stations: 16,
    support: "Higher",
    note: "A southern-city diagnostic for whether corrections remain useful outside the Indo-Gangetic Plain.",
    series: {
      corrected: [46, 52, 57, 49],
      raw_aurora: [51, 56, 60, 54],
      cams_forecast: [48, 51, 55, 53],
      persistence: [47, 47, 47, 47],
    },
  },
  {
    city: "Chennai",
    state: "Tamil Nadu",
    stations: 8,
    support: "Moderate",
    note: "A coastal-city test of whether the system handles a different pollution and weather regime.",
    series: {
      corrected: [51, 58, 63, 55],
      raw_aurora: [54, 61, 67, 60],
      cams_forecast: [50, 56, 61, 58],
      persistence: [49, 49, 49, 49],
    },
  },
  {
    city: "Mumbai",
    state: "Maharashtra",
    stations: 36,
    support: "Higher",
    note: "Dense coverage makes local correction easier to inspect, but it is not the product's headline city.",
    series: {
      corrected: [62, 70, 78, 68],
      raw_aurora: [58, 66, 73, 65],
      cams_forecast: [55, 61, 67, 63],
      persistence: [60, 60, 60, 60],
    },
  },
  {
    city: "Delhi",
    state: "Delhi",
    stations: 64,
    support: "Higher",
    note: "Included as a dense diagnostic environment. Delhi is not the target and already has AQEWS.",
    series: {
      corrected: [178, 206, 231, 194],
      raw_aurora: [92, 108, 121, 104],
      cams_forecast: [86, 94, 102, 97],
      persistence: [172, 172, 172, 172],
    },
  },
];

const DAY_LABELS = ["Tomorrow", "Day 2", "Day 3", "Day 4"];
const LEADS = ["+24 h", "+48 h", "+72 h", "+96 h"];

function category(value: number) {
  if (value <= 30) return { name: "Good", tone: "good" };
  if (value <= 60) return { name: "Satisfactory", tone: "satisfactory" };
  if (value <= 90) return { name: "Moderate", tone: "moderate" };
  if (value <= 120) return { name: "Poor", tone: "poor" };
  if (value <= 250) return { name: "Very Poor", tone: "very-poor" };
  return { name: "Severe", tone: "severe" };
}

export default function Home() {
  const [cityName, setCityName] = useState("Varanasi");
  const [method, setMethod] = useState<Method>("corrected");
  const [selectedDay, setSelectedDay] = useState(1);
  const [cityMenuOpen, setCityMenuOpen] = useState(false);

  const city = useMemo(
    () => CITIES.find((item) => item.city === cityName) ?? CITIES[0],
    [cityName],
  );
  const values = city.series[method];
  const selected = category(values[selectedDay]);
  const rawGap =
    city.series.corrected[selectedDay] - city.series.raw_aurora[selectedDay];
  const methodLabel = METHODS.find((item) => item.id === method)?.label;

  return (
    <main>
      <div className="research-banner">
        <span className="pulse-dot" aria-hidden="true" />
        Product preview · illustrative data only · no live forecast is being issued
      </div>

      <header className="site-header">
        <a className="brand" href="#top" aria-label="IndiaAQBench home">
          <span className="brand-mark">IAQ</span>
          <span>
            <strong>IndiaAQBench</strong>
            <small>Open forecasting research</small>
          </span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#forecast">Forecast</a>
          <a href="#evidence">Evidence</a>
          <a href="#method">How it works</a>
          <a className="nav-cta" href="https://github.com/stafansanthosh/Aurora-for-India">
            View research ↗
          </a>
        </nav>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">A low-compute public experiment</p>
          <h1>
            Four days of air-quality context,
            <span> built for cities forecasts often miss.</span>
          </h1>
          <p className="hero-deck">
            We are testing whether a global atmospheric model, public station
            readings, and modest compute can produce useful PM2.5 forecasts for
            underserved Indian cities—and showing the evidence as we go.
          </p>
          <div className="hero-actions">
            <a className="primary-button" href="#forecast">
              Explore the preview
            </a>
            <a className="text-link" href="#method">
              Read the 90-second explanation <span>→</span>
            </a>
          </div>
        </div>
        <div className="hero-aside" aria-label="Research snapshot">
          <div className="air-orbit orbit-one" />
          <div className="air-orbit orbit-two" />
          <div className="hero-stat main-stat">
            <span>Forecast horizon</span>
            <strong>96 h</strong>
            <small>Eight 12-hour model steps</small>
          </div>
          <div className="hero-stat floating-stat stations-stat">
            <strong>159</strong>
            <span>stations in the benchmark</span>
          </div>
          <div className="hero-stat floating-stat cities-stat">
            <strong>9</strong>
            <span>cities, 3 fully held out</span>
          </div>
          <div className="compute-pill">
            <span className="compute-icon">◌</span>
            Designed for a temporary 48 GB GPU—not a supercomputer
          </div>
        </div>
      </section>

      <section className="principles-strip" aria-label="Project principles">
        <div><strong>Open inputs</strong><span>CAMS + OpenAQ</span></div>
        <div><strong>Events first</strong><span>Missed pollution episodes matter</span></div>
        <div><strong>Honest transfer</strong><span>Unseen stations and cities</span></div>
        <div><strong>Visible evidence</strong><span>Raw, corrected, and baselines</span></div>
      </section>

      <section className="forecast-section" id="forecast">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Interactive product direction</p>
            <h2>One forecast. Every comparison visible.</h2>
          </div>
          <div className="demo-stamp">
            <span>DEMO MODE</span>
            Live pipeline not connected
          </div>
        </div>

        <div className="forecast-shell">
          <div className="forecast-toolbar">
            <div className="city-picker">
              <label htmlFor="city-selector">City</label>
              <button
                id="city-selector"
                className="city-button"
                type="button"
                aria-expanded={cityMenuOpen}
                onClick={() => setCityMenuOpen((open) => !open)}
              >
                <span>
                  <strong>{city.city}</strong>
                  <small>{city.state}</small>
                </span>
                <span aria-hidden="true">⌄</span>
              </button>
              {cityMenuOpen && (
                <div className="city-menu">
                  {CITIES.map((item) => (
                    <button
                      key={item.city}
                      type="button"
                      className={item.city === city.city ? "active" : ""}
                      onClick={() => {
                        setCityName(item.city);
                        setCityMenuOpen(false);
                      }}
                    >
                      <span>{item.city}</span>
                      <small>{item.stations} stations</small>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="method-picker">
              <span className="field-label">Show prediction</span>
              <div className="segmented-control" role="group" aria-label="Forecast method">
                {METHODS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={method === item.id ? "active" : ""}
                    aria-pressed={method === item.id}
                    onClick={() => setMethod(item.id)}
                  >
                    {item.short}
                  </button>
                ))}
              </div>
            </div>

            <div className="freshness">
              <span className="status-ring" aria-hidden="true" />
              <span><strong>Illustrative cycle</strong><small>No operational timestamp</small></span>
            </div>
          </div>

          <div className="forecast-content">
            <div className="forecast-main">
              <div className="city-context">
                <span className={`data-support support-${city.support.toLowerCase()}`}>
                  Illustrative {city.support.toLowerCase()} support
                </span>
                <p>{city.note}</p>
              </div>

              <div className="day-grid">
                {values.map((value, index) => {
                  const cat = category(value);
                  return (
                    <button
                      type="button"
                      key={DAY_LABELS[index]}
                      className={`day-card ${selectedDay === index ? "selected" : ""}`}
                      onClick={() => setSelectedDay(index)}
                      aria-pressed={selectedDay === index}
                    >
                      <span className="day-meta">
                        <strong>{DAY_LABELS[index]}</strong>
                        <small>{LEADS[index]}</small>
                      </span>
                      <span className="forecast-value">
                        {value}<small>µg/m³</small>
                      </span>
                      <span className={`category-pill ${cat.tone}`}>{cat.name}</span>
                      <span className="mini-range" aria-hidden="true">
                        <i style={{ width: `${Math.min(100, 18 + value / 2.7)}%` }} />
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="comparison-panel">
                <div>
                  <span className="field-label">Selected outlook</span>
                  <h3>{DAY_LABELS[selectedDay]} in {city.city}</h3>
                  <p>
                    The <strong>{methodLabel}</strong> preview places the rolling
                    24-hour PM2.5 mean in the <strong>{selected.name}</strong> band.
                  </p>
                </div>
                <div className="comparison-bars">
                  {METHODS.map((item) => {
                    const value = city.series[item.id][selectedDay];
                    return (
                      <button
                        type="button"
                        key={item.id}
                        className={method === item.id ? "active" : ""}
                        onClick={() => setMethod(item.id)}
                      >
                        <span><strong>{item.short}</strong><small>{value} µg/m³</small></span>
                        <i><b style={{ width: `${Math.min(100, value / 2.7)}%` }} /></i>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <aside className="explain-panel">
              <div className="explain-heading">
                <span className="explain-icon">↗</span>
                <div><small>Why the values differ</small><strong>Local surface gap</strong></div>
              </div>
              <p>
                Coarse global fields can miss pollution measured at street-level
                stations. The planned local adjustment uses only observations
                available before the forecast starts.
              </p>
              <div className="gap-number">
                <span>{rawGap >= 0 ? "+" : ""}{rawGap}</span>
                <small>µg/m³ illustrative adjustment on {DAY_LABELS[selectedDay].toLowerCase()}</small>
              </div>
              <div className="signal-list">
                <div><span>Registry coverage</span><strong>{city.stations} benchmark stations</strong></div>
                <div><span>Atmospheric evolution</span><strong>Aurora</strong></div>
                <div><span>Operational global comparison</span><strong>CAMS forecast</strong></div>
                <div><span>Simple reality check</span><strong>Persistence</strong></div>
              </div>
              <div className="explain-note">
                <span aria-hidden="true">i</span>
                <p>For a city without recent observations, the public feed will show a limited-data or method-unavailable state rather than imply local calibration.</p>
              </div>
            </aside>
          </div>
        </div>
      </section>

      <section className="evidence-section" id="evidence">
        <div className="section-heading light-heading">
          <div>
            <p className="eyebrow">Evidence in the open</p>
            <h2>The scorecard will show misses, too.</h2>
          </div>
          <p>
            The current 159-station rollout is pending. These cards show the
            interface and the standards a public result must meet—not model results.
          </p>
        </div>
        <div className="evidence-grid">
          <article className="metric-card waiting">
            <span className="metric-kicker">Very Poor+ events</span>
            <strong>Awaiting full benchmark</strong>
            <p>Every POD, FAR, and CSI score will appear with its event count.</p>
            <div className="empty-meter"><i /></div>
          </article>
          <article className="metric-card">
            <span className="metric-kicker">Scientific coverage</span>
            <strong>56 dates × 9 cities</strong>
            <p>32 fitting dates, 24 later test dates, and three cities excluded from ordinary fitting.</p>
            <div className="coverage-dots" aria-label="32 training and 24 test dates">
              {Array.from({ length: 14 }).map((_, index) => <i key={index} className={index > 7 ? "test" : ""} />)}
            </div>
          </article>
          <article className="metric-card">
            <span className="metric-kicker">Safety gate</span>
            <strong>Events before MAE</strong>
            <p>A correction is rejected if it improves average error by erasing severe pollution episodes.</p>
            <div className="guardrail"><span>Raw event skill</span><b>must not fall</b></div>
          </article>
          <article className="metric-card">
            <span className="metric-kicker">Public record</span>
            <strong>Forecast first, score later</strong>
            <p>Live predictions will be versioned before observations arrive, creating a prospective record.</p>
            <div className="ledger-row"><span>MODEL v0.x</span><span>LOCKED BEFORE OUTCOME</span></div>
          </article>
        </div>
      </section>

      <section className="method-section" id="method">
        <div className="method-intro">
          <p className="eyebrow">The 90-second explanation</p>
          <h2>Global physics.<br />Local evidence.<br />Modest compute.</h2>
          <p>
            IndiaAQBench asks how much practical value can be created before
            resorting to an expensive city-specific chemistry model.
          </p>
          <a href="https://github.com/stafansanthosh/Aurora-for-India">
            Inspect the methods and open code <span>↗</span>
          </a>
        </div>
        <div className="method-steps">
          <article>
            <span>01</span>
            <div><h3>Start from today’s atmosphere</h3><p>CAMS supplies pollution, winds, temperature, pressure, and the global atmospheric state.</p></div>
            <small>CAMS analysis</small>
          </article>
          <article>
            <span>02</span>
            <div><h3>Forecast the next four days</h3><p>Aurora evolves that state at a fraction of the compute used by a full operational chemistry system.</p></div>
            <small>+12 to +96 h</small>
          </article>
          <article>
            <span>03</span>
            <div><h3>Correct carefully at the surface</h3><p>Recent station evidence can anchor local bias, with conservative fallback when observations are thin.</p></div>
            <small>No future data</small>
          </article>
          <article>
            <span>04</span>
            <div><h3>Publish the track record</h3><p>Every method is compared with persistence, climatology, CAMS, and raw Aurora using the same path.</p></div>
            <small>POD · FAR · CSI</small>
          </article>
        </div>
      </section>

      <section className="closing-section">
        <p className="eyebrow">Building in public</p>
        <h2>A useful forecast is more than a number.</h2>
        <p>
          It is a timely prediction, a visible baseline, an honest uncertainty,
          and a track record anyone can inspect.
        </p>
        <div>
          <a className="primary-button" href="https://github.com/stafansanthosh/Aurora-for-India">
            Follow the research on GitHub ↗
          </a>
          <span>Experimental research · not official health guidance</span>
        </div>
      </section>

      <footer>
        <div className="brand footer-brand">
          <span className="brand-mark">IAQ</span>
          <span><strong>IndiaAQBench</strong><small>Aurora · CAMS · OpenAQ</small></span>
        </div>
        <p>
          This preview uses illustrative values to demonstrate the intended
          interface. It is not a forecast, warning, or health advisory.
        </p>
        <div><a href="#top">Back to top ↑</a></div>
      </footer>
    </main>
  );
}
