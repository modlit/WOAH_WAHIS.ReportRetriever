"""
Build a lightweight standalone HTML animation of WAHIS outbreaks in Europe.

Uses Leaflet.js (OpenStreetMap tiles) with client-side JS animation.
Data is embedded once as JSON; JS filters points per frame -- no flicker.
"""

import base64
import glob
import json
import numpy as np
import pandas as pd

# ── Load & filter ────────────────────────────────────────────────────────────
files = sorted(glob.glob("OUTPUTS/WAHIS_ReportOutbreaks_*.xlsx"))
df = pd.concat([pd.read_excel(f) for f in files], ignore_index=True)
df = df.dropna(subset=["latitude", "longitude"])

df["start"] = pd.to_datetime(df["outbreak_start_date"], utc=True)
df["end"] = pd.to_datetime(df["outbreak_end_date"], utc=True, errors="coerce")

cutoff = pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=6)
df = df[df["start"] >= cutoff].copy()
df = df[df["longitude"].between(-25, 45) & df["latitude"].between(34, 72)].copy()

# Shorten disease names
df["disease_short"] = (
    df["disease"]
    .str.replace(r"\s*\(Inf\..*", "", regex=True)
    .str.replace(r"\s*\(\d{4}-?\d{0,4}\)", "", regex=True)
    .str.strip()
)

# Convert to days since epoch for compact storage
epoch = pd.Timestamp("1970-01-01", tz="UTC")
df["s"] = (df["start"] - epoch).dt.days.astype(int)
end_days = (df["end"] - epoch).dt.days
df["e"] = end_days.fillna(99999).astype(int)

# Build compact JSON records
records = []
for _, r in df.iterrows():
    records.append({
        "lat": round(r["latitude"], 4),
        "lng": round(r["longitude"], 4),
        "s": int(r["s"]),
        "e": int(r["e"]),
        "loc": r["outbreak_location"] if pd.notna(r["outbreak_location"]) else "",
        "country": r["country"] if pd.notna(r["country"]) else "",
        "disease": r["disease_short"],
        "start_str": r["start"].strftime("%d/%m/%Y"),
        "end_str": r["end"].strftime("%d/%m/%Y") if pd.notna(r["end"]) and r["end"].year < 2099 else "Ongoing",
    })

data_json = json.dumps(records, separators=(",", ":"))

date_min = df["start"].min()
date_max = pd.Timestamp.now(tz="UTC").normalize()
day_min = int((date_min - epoch).days)
day_max = int((date_max - epoch).days)

# Assign colours per disease
diseases = sorted(df["disease_short"].unique())
palette = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
]
disease_colors = {d: palette[i % len(palette)] for i, d in enumerate(diseases)}
colors_json = json.dumps(disease_colors)

print(f"Data: {len(records)} outbreaks, {len(data_json)//1024}KB JSON")
print(f"Days: {day_min} to {day_max} ({day_max - day_min} days)")

# Load and base64-encode the modlit logo
with open("modlit_logo.svg", "rb") as f:
    logo_b64 = base64.b64encode(f.read()).decode("ascii")

# ── Build HTML ───────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WAHIS Outbreak Animation - Europe</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#1a1a2e; color:#eee; }}
  #map {{ width:100vw; height:100vh; }}
  #controls {{
    position:fixed; top:12px; left:60px; z-index:1000;
    background:rgba(20,20,40,0.92); border-radius:10px; padding:14px 20px;
    box-shadow:0 4px 20px rgba(0,0,0,0.4); min-width:420px;
  }}
  #controls h2 {{ font-size:15px; margin-bottom:8px; color:#8ecae6; }}
  #date-display {{ font-size:22px; font-weight:700; margin-bottom:6px; }}
  #count-display {{ font-size:13px; color:#aaa; margin-bottom:10px; }}
  #slider-row {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
  #day-slider {{ flex:1; accent-color:#8ecae6; cursor:pointer; }}
  .btn {{
    background:#264653; color:#eee; border:none; border-radius:6px;
    padding:6px 14px; cursor:pointer; font-size:13px; font-weight:600;
  }}
  .btn:hover {{ background:#2a9d8f; }}
  .btn.active {{ background:#e76f51; }}
  #speed-row {{ display:flex; align-items:center; gap:8px; font-size:12px; color:#aaa; }}
  #speed-slider {{ width:100px; accent-color:#8ecae6; }}
  #legend {{
    position:fixed; bottom:20px; left:60px; z-index:1000;
    background:rgba(20,20,40,0.92); border-radius:10px; padding:12px 16px;
    box-shadow:0 4px 20px rgba(0,0,0,0.4); max-height:40vh; overflow-y:auto;
  }}
  #legend h3 {{ font-size:13px; margin-bottom:6px; color:#8ecae6; }}
  .legend-item {{ font-size:12px; margin:3px 0; display:flex; align-items:center; gap:6px; }}
  .legend-dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
  #logo {{
    position:fixed; top:12px; right:60px; z-index:1000;
    opacity:0.55;
    transition: opacity 0.2s;
  }}
  #logo:hover {{ opacity:0.9; }}
  #logo img {{ height:40px; }}
</style>
</head>
<body>
<div id="map"></div>
<a id="logo" href="https://modlit.io" target="_blank" rel="noopener"><img src="data:image/svg+xml;base64,{logo_b64}" alt="modlit"></a>
<div id="controls">
  <h2>Bluetongue Outbreaks in Europe</h2>
  <div id="date-display"></div>
  <div id="count-display"></div>
  <div id="slider-row">
    <button class="btn" id="play-btn" onclick="togglePlay()">&#9654; Play</button>
    <input type="range" id="day-slider" min="{day_min}" max="{day_max}" value="{day_min}">
    <button class="btn" id="reset-btn" onclick="resetAnim()">&#9198; Reset</button>
  </div>
  <div id="speed-row">
    <span>Speed:</span>
    <input type="range" id="speed-slider" min="1" max="50" value="10">
    <span id="speed-label">10 days/sec</span>
  </div>
</div>
<div id="legend">
  <h3>Diseases</h3>
  {"".join(f'<div class="legend-item"><span class="legend-dot" style="background:{c}"></span>{d}</div>' for d, c in disease_colors.items())}
</div>

<script>
const DATA = {data_json};
const COLORS = {colors_json};
const DAY_MIN = {day_min};
const DAY_MAX = {day_max};

// Init map
const map = L.map('map', {{zoomControl:false}}).setView([50, 10], 4);
L.control.zoom({{position:'topright'}}).addTo(map);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}@2x.png', {{
  attribution:'&copy; <a href="https://carto.com">CARTO</a> &copy; <a href="https://osm.org">OSM</a>',
  maxZoom:18,
}}).addTo(map);

// Canvas renderer for performance
const renderer = L.canvas({{padding:0.5}});

// Pre-create circle markers (hidden initially)
const markers = DATA.map(d => {{
  const m = L.circleMarker([d.lat, d.lng], {{
    radius: 5,
    color: '#fff',
    weight: 0.5,
    fillColor: COLORS[d.disease] || '#999',
    fillOpacity: 0.8,
    renderer: renderer,
  }});
  m._data = d;
  m.bindPopup(`<b>${{d.loc}}</b><br>${{d.country}}<br>${{d.disease}}<br>Start: ${{d.start_str}}<br>End: ${{d.end_str}}`);
  return m;
}});

// Layer group for batch add/remove
const activeGroup = L.layerGroup().addTo(map);
let activeSet = new Set();

const slider = document.getElementById('day-slider');
const dateDisplay = document.getElementById('date-display');
const countDisplay = document.getElementById('count-display');
const playBtn = document.getElementById('play-btn');
const speedSlider = document.getElementById('speed-slider');
const speedLabel = document.getElementById('speed-label');

let playing = false;
let animFrame = null;
let lastTime = 0;

function dayToDate(day) {{
  const d = new Date(day * 86400000);
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const yy = d.getUTCFullYear();
  return `${{dd}}/${{mm}}/${{yy}}`;
}}

function updateMap(currentDay) {{
  let count = 0;
  const newActive = new Set();

  for (let i = 0; i < DATA.length; i++) {{
    const d = DATA[i];
    const visible = d.s <= currentDay && d.e > currentDay;
    if (visible) {{
      newActive.add(i);
      count++;
      if (!activeSet.has(i)) {{
        activeGroup.addLayer(markers[i]);
      }}
    }} else {{
      if (activeSet.has(i)) {{
        activeGroup.removeLayer(markers[i]);
      }}
    }}
  }}
  activeSet = newActive;

  dateDisplay.textContent = dayToDate(currentDay);
  countDisplay.textContent = count.toLocaleString() + ' active outbreaks';
}}

function getSpeed() {{
  return parseInt(speedSlider.value);
}}

speedSlider.addEventListener('input', () => {{
  speedLabel.textContent = getSpeed() + ' days/sec';
}});

slider.addEventListener('input', () => {{
  updateMap(parseInt(slider.value));
}});

function animate(ts) {{
  if (!playing) return;
  if (!lastTime) lastTime = ts;
  const elapsed = ts - lastTime;
  const daysPerSec = getSpeed();
  const msPerDay = 1000 / daysPerSec;

  if (elapsed >= msPerDay) {{
    let cur = parseInt(slider.value);
    // Advance by however many days elapsed
    const steps = Math.max(1, Math.floor(elapsed / msPerDay));
    cur = Math.min(cur + steps, DAY_MAX);
    slider.value = cur;
    updateMap(cur);
    lastTime = ts;
    if (cur >= DAY_MAX) {{
      playing = false;
      playBtn.innerHTML = '&#9654; Play';
      playBtn.classList.remove('active');
      return;
    }}
  }}
  animFrame = requestAnimationFrame(animate);
}}

function togglePlay() {{
  playing = !playing;
  if (playing) {{
    playBtn.innerHTML = '&#9724; Pause';
    playBtn.classList.add('active');
    lastTime = 0;
    animFrame = requestAnimationFrame(animate);
  }} else {{
    playBtn.innerHTML = '&#9654; Play';
    playBtn.classList.remove('active');
    if (animFrame) cancelAnimationFrame(animFrame);
  }}
}}

function resetAnim() {{
  playing = false;
  playBtn.innerHTML = '&#9654; Play';
  playBtn.classList.remove('active');
  if (animFrame) cancelAnimationFrame(animFrame);
  slider.value = DAY_MIN;
  updateMap(DAY_MIN);
}}

// Initial render
updateMap(DAY_MIN);
</script>
</body>
</html>"""

output_path = "OUTPUTS/outbreak_animation_europe.html"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Saved to {output_path}")
import os
size_mb = os.path.getsize(output_path) / (1024 * 1024)
print(f"File size: {size_mb:.1f} MB")
