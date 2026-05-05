/* ═══════════════════════════════════════════════════════════════════
   Nautical Compass — Live Command Deck  ·  Main Controller v2
   Enhanced: easing dials, needle vibration, glow pulses, color-coded
   ranges, star field, whitecaps, improved weather integration
   ═══════════════════════════════════════════════════════════════════ */

/* ── PLACEHOLDER DATA (fallback if API unavailable) ────────────── */
const weatherData = {
  condition:      "clear",   // clear | cloudy | rain | fog | storm | snow
  temperature:    72,        // °F
  wind_speed:     12,        // mph
  wind_direction: "NE",
  humidity:       45,        // %
  visibility:     10,        // miles
  source:         "mock"     // mock | live
};

const systemState = {
  standing:   85,
  capacity:   72,
  jurisdiction: 90,
  evidence:   68,
  compliance: 94,
  deployment: 77
};

/* ── INTAKE STATE — single source for all intake-driven reactions ─ */
const intakeState = {
  score:            null,
  missing:          [],
  status:           null,
  type:             null,
  totalSubmissions: 0,
  lastId:           null,
};

/* ── API DATA FETCH + GEOLOCATION ────────────────────────────────── */
let dataSource = "mock";
let userLat = null;
let userLon = null;
let locationStatus = "pending"; // pending | granted | denied | unavailable

function initGeolocation() {
  if (!navigator.geolocation) {
    locationStatus = "unavailable";
    updateLocationStatusUI();
    return;
  }
  navigator.geolocation.getCurrentPosition(
    function(pos) {
      userLat = pos.coords.latitude;
      userLon = pos.coords.longitude;
      locationStatus = "granted";
      updateLocationStatusUI();
      fetchAllDeckData(); // re-fetch with coords immediately
    },
    function(err) {
      locationStatus = "denied";
      updateLocationStatusUI();
    },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
  );
}

function updateLocationStatusUI() {
  const el = document.getElementById("locationStatus");
  if (!el) return;
  if (locationStatus === "granted" && dataSource === "live") {
    el.textContent = "Using local weather";
    el.className = "location-status status-live";
  } else if (locationStatus === "denied") {
    el.textContent = "Location unavailable";
    el.className = "location-status status-denied";
  } else if (locationStatus === "unavailable") {
    el.textContent = "Location unavailable";
    el.className = "location-status status-denied";
  } else {
    el.textContent = "Using mock weather";
    el.className = "location-status status-mock";
  }
}

async function fetchDeckStatus() {
  try {
    const resp = await fetch("/api/command-deck/status/intake");
    if (!resp.ok) return;
    const data = await resp.json();
    const keys = ["standing", "capacity", "jurisdiction", "evidence", "compliance", "deployment"];
    keys.forEach(k => { if (data[k] !== undefined) systemState[k] = data[k]; });

    if (data.intake_engine) {
      const ie = data.intake_engine;
      const newId = ie.latest_id || null;
      checkForNewIntake(newId);
      intakeState.score            = ie.latest_score  != null ? ie.latest_score  : intakeState.score;
      intakeState.missing          = ie.latest_missing  || [];
      intakeState.status           = ie.latest_status   || intakeState.status;
      intakeState.type             = ie.latest_type     || intakeState.type;
      intakeState.totalSubmissions = ie.total_submissions != null ? ie.total_submissions : intakeState.totalSubmissions;
      intakeState.lastId           = newId;
      updateIntakePanelFromState(ie);
      syncIntakeToSystemState();
      applyDerivedWeather();
      updateOperatorRailPanel(ie.operator_rail || null, ie);
      updateLaborRailPanel(ie.labor_rail || null, ie);
      updateLegalRailPanel(ie.legal_rail || null, ie);
      updateRailAuditBadges(ie, data.recent_intakes || []);
    }
    if (data.recent_intakes) {
      updateRecentFeed(data.recent_intakes);
    }
  } catch (e) { /* keep existing mock data on failure */ }
}

/* ── RAIL AUDIT BADGES ─────────────────────────────────────────── */
function auditStatusFromScore(score) {
  if (score == null) return { label: 'NEEDS REVIEW', cls: 'audit-needs-review' };
  if (score >= 80)   return { label: 'READY',        cls: 'audit-ready'        };
  if (score >= 40)   return { label: 'PARTIAL',      cls: 'audit-partial'      };
  return                    { label: 'LOW',           cls: 'audit-low'          };
}

function applyAuditBadge(type, score, id, meta) {
  var badgeEl  = document.getElementById('auditBadge'  + type);
  var statusEl = document.getElementById('auditStatus' + type);
  var metaEl   = document.getElementById('auditMeta'   + type);
  if (!badgeEl || !statusEl || !metaEl) return;

  var s = auditStatusFromScore(score);

  badgeEl.classList.remove(
    'audit-badge-ready', 'audit-badge-partial',
    'audit-badge-low',   'audit-badge-needs-review'
  );
  badgeEl.classList.add('audit-badge-' + s.cls.replace('audit-', ''));

  statusEl.textContent = s.label;
  statusEl.className   = 'audit-badge-status ' + s.cls;

  metaEl.textContent = meta || 'no data';
}

function updateRailAuditBadges(ie, recentIntakes) {
  // ── Operator Rail ────────────────────────────────────────────────
  var orScore = null, orId = null, orType = null;
  if (ie.operator_rail) {
    orScore = ie.operator_rail.readiness_score != null ? ie.operator_rail.readiness_score : null;
    orId    = ie.latest_id;
    orType  = ie.latest_type;
  } else {
    for (var i = 0; i < recentIntakes.length; i++) {
      if (recentIntakes[i].rail_type === 'operator') {
        orScore = recentIntakes[i].readiness;
        orId    = recentIntakes[i].intake_id;
        orType  = recentIntakes[i].intake_type;
        break;
      }
    }
  }
  var orMeta = orId ? orId + (orType ? ' · ' + orType : '') : 'no data';
  applyAuditBadge('Operator', orScore, orId, orMeta);

  // ── Labor Rail ───────────────────────────────────────────────────
  var lrScore = null, lrId = null, lrType = null;
  if (ie.labor_rail) {
    lrScore = ie.labor_rail.readiness_score != null ? ie.labor_rail.readiness_score : null;
    lrId    = ie.latest_id;
    lrType  = ie.latest_type;
  } else {
    for (var j = 0; j < recentIntakes.length; j++) {
      if (recentIntakes[j].rail_type === 'labor') {
        lrScore = recentIntakes[j].readiness;
        lrId    = recentIntakes[j].intake_id;
        lrType  = recentIntakes[j].intake_type;
        break;
      }
    }
  }
  var lrMeta = lrId ? lrId + (lrType ? ' · ' + lrType : '') : 'no data';
  applyAuditBadge('Labor', lrScore, lrId, lrMeta);

  // ── Legal Rail ───────────────────────────────────────────────────
  var lgScore = null, lgId = null, lgType = null;
  if (ie.legal_rail) {
    var lgStanding = ie.legal_rail.standing;
    lgScore = lgStanding === true ? 92 : lgStanding === false ? 22 : null;
    lgId    = ie.latest_id;
    lgType  = ie.latest_type;
  } else {
    for (var k = 0; k < recentIntakes.length; k++) {
      if (recentIntakes[k].rail_type === 'legal') {
        lgScore = recentIntakes[k].readiness;
        lgId    = recentIntakes[k].intake_id;
        lgType  = recentIntakes[k].intake_type;
        break;
      }
    }
  }
  var lgMeta = lgId ? lgId + (lgType ? ' · ' + lgType : '') : 'no data';
  applyAuditBadge('Legal', lgScore, lgId, lgMeta);

  // ── Recent Feed ──────────────────────────────────────────────────
  var feedScore = null, feedMeta = '—';
  if (recentIntakes && recentIntakes.length > 0) {
    var complete = recentIntakes.filter(function(r) { return r.status === 'complete'; }).length;
    feedScore = Math.round((complete / recentIntakes.length) * 100);
    feedMeta  = recentIntakes.length + ' record' + (recentIntakes.length !== 1 ? 's' : '') +
                ' · ' + complete + ' complete';
  }
  applyAuditBadge('Feed', feedScore, null, feedMeta);
}

/* ── RECENT RAIL ACTIVITY FEED ─────────────────────────────────── */
function updateRecentFeed(items) {
  var container = document.getElementById('recentFeedList');
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = '<div class="feed-empty">No recent intake activity</div>';
    return;
  }

  var TYPE_LABELS = {
    partner:    'Partner',
    labor:      'Labor',
    production: 'Prod',
    legal:      'Legal',
    payment:    'Payment',
    general:    'General'
  };

  var RAIL_LABELS = { operator: 'Operator Rail', labor: 'Labor Rail', legal: 'Legal Rail' };

  container.innerHTML = items.map(function(item) {
    var type       = item.intake_type || 'general';
    var typeLabel  = TYPE_LABELS[type] || type;
    var railLabel  = RAIL_LABELS[item.rail_type] || '';
    var readiness  = item.readiness != null ? item.readiness + '%' : '';
    var statusCls  = item.status === 'complete' ? 'feed-status-complete' : 'feed-status-partial';
    var date       = item.created_at
      ? new Date(item.created_at * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : '';
    var railStr    = railLabel ? (railLabel + (readiness ? ' · ' + readiness : '')) : '—';

    return '<div class="feed-item">' +
      '<span class="feed-type-badge feed-type-' + type + '">' + typeLabel + '</span>' +
      '<span class="feed-rail-label">' + railStr + '</span>' +
      '<span class="feed-subject">' + (item.subject || '—') + '</span>' +
      '<span class="feed-meta">' +
        '<span class="feed-status ' + statusCls + '">' + (item.status || '—') + '</span>' +
        (date ? '<span class="feed-date">' + date + '</span>' : '') +
      '</span>' +
    '</div>';
  }).join('');
}

async function fetchDeckWeather() {
  try {
    let url = "/api/command-deck/weather";
    if (userLat !== null && userLon !== null) {
      url += "?lat=" + userLat.toFixed(4) + "&lon=" + userLon.toFixed(4);
    }
    const resp = await fetch(url);
    if (!resp.ok) return;
    const data = await resp.json();
    weatherData.condition      = data.condition || weatherData.condition;
    weatherData.temperature    = data.temperature ?? weatherData.temperature;
    weatherData.wind_speed     = data.wind_speed ?? weatherData.wind_speed;
    weatherData.wind_direction = data.wind_direction || weatherData.wind_direction;
    weatherData.humidity       = data.humidity ?? weatherData.humidity;
    weatherData.visibility     = data.visibility ?? weatherData.visibility;
    weatherData.source         = data.source || "mock";
    dataSource = data.source || "mock";
    updateDataSourceIndicator();
    updateLocationStatusUI();
  } catch (e) { /* keep existing mock data on failure */ }
}

function updateDataSourceIndicator() {
  const el = document.getElementById("dataSourceBadge");
  if (!el) return;
  el.textContent = dataSource === "live" ? "LIVE" : "MOCK";
  el.className = "data-source-badge " + (dataSource === "live" ? "source-live" : "source-mock");
}

async function fetchAllDeckData() {
  await Promise.all([fetchDeckStatus(), fetchDeckWeather()]);
}

/* ── WEATHER STATE MACHINE ─────────────────────────────────────── */
const WEATHER_CYCLE = ["clear", "cloudy", "rain", "fog", "storm", "snow"];
let weatherIndex = 0;

const WEATHER_PROFILES = {
  clear:  { temperature: 72, wind_speed: 8,  wind_direction: "NE", humidity: 40, visibility: 12 },
  cloudy: { temperature: 65, wind_speed: 14, wind_direction: "E",  humidity: 58, visibility: 8 },
  rain:   { temperature: 58, wind_speed: 20, wind_direction: "SE", humidity: 78, visibility: 4 },
  fog:    { temperature: 54, wind_speed: 5,  wind_direction: "S",  humidity: 92, visibility: 1 },
  storm:  { temperature: 50, wind_speed: 45, wind_direction: "SW", humidity: 88, visibility: 2 },
  snow:   { temperature: 28, wind_speed: 18, wind_direction: "NW", humidity: 70, visibility: 3 }
};

const DIRECTION_DEGREES = {
  N: 0, NNE: 22.5, NE: 45, ENE: 67.5, E: 90, ESE: 112.5, SE: 135, SSE: 157.5,
  S: 180, SSW: 202.5, SW: 225, WSW: 247.5, W: 270, WNW: 292.5, NW: 315, NNW: 337.5
};

/* ── OPERATIONAL DATA RANDOMIZER ───────────────────────────────── */
function randomizeSystemState() {
  const keys = ["standing", "capacity", "jurisdiction", "evidence", "compliance", "deployment"];
  keys.forEach(k => {
    const current = systemState[k];
    const delta = Math.floor(Math.random() * 11) - 5;
    systemState[k] = Math.max(10, Math.min(100, current + delta));
  });
}

/* ── DOM REFERENCES ────────────────────────────────────────────── */
const $body            = document.getElementById("commandDeck");
const $compassNeedle   = document.getElementById("compassNeedle");
const $compassReadout  = document.getElementById("compassReadout");
const $compassPanel    = document.getElementById("compassPanel");
const $windNeedle      = document.getElementById("windNeedle");
const $windReadout     = document.getElementById("windReadout");
const $windPanel       = document.getElementById("windPanel");
const $statusNeedle    = document.getElementById("statusNeedle");
const $statusReadout   = document.getElementById("statusReadout");
const $statusPanel     = document.getElementById("statusPanel");
const $caseFlowArc     = document.getElementById("caseFlowArc");
const $caseFlowPercent = document.getElementById("caseFlowPercent");
const $caseFlowReadout = document.getElementById("caseFlowReadout");
const $caseflowPanel   = document.getElementById("caseflowPanel");
const $complianceNeedle = document.getElementById("complianceNeedle");
const $complianceReadout = document.getElementById("complianceReadout");
const $compliancePanel = document.getElementById("compliancePanel");
const $tempValue       = document.getElementById("tempValue");
const $humidityValue   = document.getElementById("humidityValue");
const $visibilityValue = document.getElementById("visibilityValue");
const $conditionValue  = document.getElementById("conditionValue");
const $weatherBadge    = document.getElementById("weatherBadge");
const $clockDisplay    = document.getElementById("clockDisplay");
const $refreshTimer    = document.getElementById("refreshTimer");
const $rainContainer   = document.getElementById("rainContainer");
const $snowContainer   = document.getElementById("snowContainer");
const $starField       = document.getElementById("starField");
const $whitecapContainer = document.getElementById("whitecapContainer");

/* Audio UI elements */
const $audioToggle     = document.getElementById("audioToggle");
const $toggleIcon      = document.getElementById("toggleIcon");
const $toggleText      = document.getElementById("toggleText");
const $volumeSlider    = document.getElementById("volumeSlider");
const $volumeValue     = document.getElementById("volumeValue");
const $soundModeValue  = document.getElementById("soundModeValue");

/* Navigation indicator DOM refs */
const $navWeatherDot   = document.getElementById("navWeatherDot");
const $navWeatherLabel = document.getElementById("navWeatherLabel");
const $navHealthDot    = document.getElementById("navHealthDot");
const $navHealthLabel  = document.getElementById("navHealthLabel");

/* ═══════════════════════════════════════════════════════════════════
   STAR FIELD GENERATION
   ═══════════════════════════════════════════════════════════════════ */
function generateStars() {
  if (!$starField) return;
  $starField.innerHTML = "";
  const count = 80;
  for (let i = 0; i < count; i++) {
    const star = document.createElement("div");
    star.className = "star";
    star.style.left = Math.random() * 100 + "%";
    star.style.top = Math.random() * 55 + "%"; // upper portion of sky
    const size = 1 + Math.random() * 2;
    star.style.width = size + "px";
    star.style.height = size + "px";
    star.style.animationDelay = (Math.random() * 5) + "s";
    star.style.animationDuration = (2 + Math.random() * 3) + "s";
    $starField.appendChild(star);
  }
}

/* ═══════════════════════════════════════════════════════════════════
   WHITECAP GENERATION
   ═══════════════════════════════════════════════════════════════════ */
function generateWhitecaps(count) {
  if (!$whitecapContainer) return;
  $whitecapContainer.innerHTML = "";
  for (let i = 0; i < count; i++) {
    const cap = document.createElement("div");
    cap.className = "whitecap";
    cap.style.left = Math.random() * 90 + "%";
    cap.style.bottom = (10 + Math.random() * 60) + "%";
    cap.style.animationDuration = (2 + Math.random() * 2) + "s";
    cap.style.animationDelay = Math.random() * 3 + "s";
    cap.style.width = (20 + Math.random() * 20) + "px";
    $whitecapContainer.appendChild(cap);
  }
}

/* ═══════════════════════════════════════════════════════════════════
   WEATHER VISUAL UPDATES
   ═══════════════════════════════════════════════════════════════════ */
function setWeatherClass(condition) {
  WEATHER_CYCLE.forEach(c => $body.classList.remove("weather-" + c));
  $body.classList.add("weather-" + condition);
}

function generateRainDrops(count) {
  $rainContainer.innerHTML = "";
  for (let i = 0; i < count; i++) {
    const drop = document.createElement("div");
    drop.className = "rain-drop";
    drop.style.left = Math.random() * 100 + "%";
    drop.style.animationDuration = (0.4 + Math.random() * 0.6) + "s";
    drop.style.animationDelay = Math.random() * 2 + "s";
    drop.style.opacity = 0.3 + Math.random() * 0.5;
    $rainContainer.appendChild(drop);
  }
}

function generateSnowFlakes(count) {
  $snowContainer.innerHTML = "";
  for (let i = 0; i < count; i++) {
    const flake = document.createElement("div");
    flake.className = "snow-flake";
    flake.style.left = Math.random() * 100 + "%";
    flake.style.width = flake.style.height = (3 + Math.random() * 5) + "px";
    flake.style.animationDuration = (3 + Math.random() * 4) + "s";
    flake.style.animationDelay = Math.random() * 5 + "s";
    flake.style.opacity = 0.4 + Math.random() * 0.5;
    $snowContainer.appendChild(flake);
  }
}

function triggerLightning() {
  const flash = document.createElement("div");
  flash.className = "lightning-flash";
  document.body.appendChild(flash);
  setTimeout(() => flash.remove(), 350);
}

let lightningInterval = null;

function updateWeatherVisuals(condition) {
  setWeatherClass(condition);

  // Rain particles
  if (condition === "rain") {
    generateRainDrops(90);
  } else if (condition === "storm") {
    generateRainDrops(180);
  } else {
    $rainContainer.innerHTML = "";
  }

  // Snow particles
  if (condition === "snow") {
    generateSnowFlakes(120);
  } else {
    $snowContainer.innerHTML = "";
  }

  // Whitecaps
  if (condition === "storm") {
    generateWhitecaps(25);
  } else if (condition === "rain") {
    generateWhitecaps(10);
  } else {
    if ($whitecapContainer) $whitecapContainer.innerHTML = "";
  }

  // Lightning for storms
  if (lightningInterval) { clearInterval(lightningInterval); lightningInterval = null; }
  if (condition === "storm") {
    lightningInterval = setInterval(() => {
      if (Math.random() > 0.4) triggerLightning();
    }, 2500 + Math.random() * 3000);
  }

  // Update vessel motion based on weather
  updateVesselMotion();
}

/* ═══════════════════════════════════════════════════════════════════
   VESSEL MOTION — Weather-driven sea-state animation
   ═══════════════════════════════════════════════════════════════════ */

function updateVesselMotion() {
  const vessel = document.getElementById('vessel');
  if (!vessel) return;

  const condition = weatherData.condition || 'clear';
  const wind = weatherData.wind_speed || 0;

  // Determine motion class from weather condition
  let motionClass = 'motion-calm';
  if (condition === 'storm' || condition === 'thunderstorm') {
    motionClass = 'motion-rough';
  } else if (condition === 'rain' || condition === 'drizzle' || condition === 'snow') {
    motionClass = 'motion-moderate';
  } else if (condition === 'fog') {
    motionClass = 'motion-calm';
  }

  // Wind speed override: stronger wind = rougher motion
  if (wind > 25) {
    motionClass = 'motion-rough';
  } else if (wind > 10 && motionClass === 'motion-calm') {
    motionClass = 'motion-moderate';
  }

  // Apply motion class (remove old ones first)
  vessel.classList.remove('motion-calm', 'motion-moderate', 'motion-rough');
  vessel.classList.add(motionClass);
}

/* ═══════════════════════════════════════════════════════════════════
   DIAL UPDATE FUNCTIONS — with spring easing & glow
   ═══════════════════════════════════════════════════════════════════ */

/** Smooth needle rotation with CSS transition (spring easing in CSS) */
function animateNeedleRotation(element, targetDeg, cx, cy) {
  cx = cx || 100;
  cy = cy || 100;
  // Use CSS transition defined by .dial-needle class
  element.setAttribute("transform", `rotate(${targetDeg}, ${cx}, ${cy})`);
}

/** Trigger glow pulse on a panel */
function pulsePanel(panel) {
  if (!panel) return;
  panel.classList.remove("dial-pulse");
  // Force reflow
  void panel.offsetWidth;
  panel.classList.add("dial-pulse");
  setTimeout(() => panel.classList.remove("dial-pulse"), 900);
}

/* Compass */
let lastCompassDeg = 45;
function updateCompass(direction) {
  const targetDeg = DIRECTION_DEGREES[direction] || 0;
  // Calculate shortest rotation path
  let diff = targetDeg - lastCompassDeg;
  if (diff > 180) diff -= 360;
  if (diff < -180) diff += 360;
  lastCompassDeg += diff;
  animateNeedleRotation($compassNeedle, lastCompassDeg, 100, 100);
  $compassReadout.textContent = `${direction} ${targetDeg}°`;
  pulsePanel($compassPanel);
}

/* Wind dial — 0-60 mph maps to -120° to +120° arc */
function updateWindDial(speed, direction) {
  const clampedSpeed = Math.min(60, Math.max(0, speed));
  const deg = -120 + (clampedSpeed / 60) * 240;
  animateNeedleRotation($windNeedle, deg, 100, 100);
  $windReadout.textContent = `${speed} mph ${direction}`;
  pulsePanel($windPanel);
}

/* System status — average of all ops values → needle position */
function updateStatusDial() {
  const vals = Object.values(systemState);
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  const deg = -120 + (avg / 100) * 240;
  animateNeedleRotation($statusNeedle, deg, 100, 100);
  if (avg >= 75) {
    $statusReadout.textContent = "Operational";
    $statusReadout.style.color = "#2ecc71";
  } else if (avg >= 50) {
    $statusReadout.textContent = "Degraded";
    $statusReadout.style.color = "#f1c40f";
  } else {
    $statusReadout.textContent = "Critical";
    $statusReadout.style.color = "#e74c3c";
  }
  pulsePanel($statusPanel);
}

/* Case-flow progress */
let caseFlowProgress = 70;
function updateCaseFlow() {
  caseFlowProgress = Math.max(10, Math.min(100, caseFlowProgress + (Math.random() * 6 - 3)));
  const circumference = 2 * Math.PI * 70;
  const offset = circumference * (1 - caseFlowProgress / 100);
  $caseFlowArc.style.transition = "stroke-dashoffset 1.8s cubic-bezier(0.34,1.56,0.64,1)";
  $caseFlowArc.setAttribute("stroke-dashoffset", offset.toFixed(1));
  $caseFlowPercent.textContent = Math.round(caseFlowProgress) + "%";
  $caseFlowReadout.textContent = `Active Cases: ${Math.round(8 + caseFlowProgress / 10)}`;
  pulsePanel($caseflowPanel);
}

/* Compliance readiness dial */
function updateComplianceDial(value) {
  const deg = -120 + (value / 100) * 240;
  animateNeedleRotation($complianceNeedle, deg, 100, 100);
  $complianceReadout.textContent = value + "%";
  pulsePanel($compliancePanel);
}

/* Environment panel */
function updateEnvironmentPanel(data) {
  $tempValue.textContent       = data.temperature + "°F";
  $humidityValue.textContent   = data.humidity + "%";
  $visibilityValue.textContent = data.visibility + " mi";
  $conditionValue.textContent  = data.condition.charAt(0).toUpperCase() + data.condition.slice(1);
  $weatherBadge.textContent    = data.condition.toUpperCase();
}

/* ── COLOR-CODED RANGES ────────────────────────────────────────── */
function getColorForValue(value) {
  if (value >= 75) return "#2ecc71";      // green — good
  if (value >= 50) return "#f1c40f";      // yellow — caution
  return "#e74c3c";                        // red — critical
}

/* Operational dials (the 6 ring gauges) — with color coding & pulse */
function updateOpsDials() {
  Object.keys(systemState).forEach(key => {
    const dial = document.querySelector(`.ops-dial[data-key="${key}"]`);
    if (!dial) return;
    const value = systemState[key];
    const arc = dial.querySelector(".ops-arc");
    const valText = dial.querySelector(".ops-val");
    const circumference = 2 * Math.PI * 45;
    const offset = circumference * (1 - value / 100);
    arc.setAttribute("stroke-dashoffset", offset.toFixed(1));

    // Color-coded stroke based on value
    const color = getColorForValue(value);
    arc.setAttribute("stroke", color);
    valText.setAttribute("fill", color);
    valText.textContent = value;

    // Pulse effect
    dial.classList.remove("ops-pulse");
    void dial.offsetWidth;
    dial.classList.add("ops-pulse");
    setTimeout(() => dial.classList.remove("ops-pulse"), 900);
  });
}

/* ═══════════════════════════════════════════════════════════════════
   NEEDLE VIBRATION — subtle micro-movement at rest
   ═══════════════════════════════════════════════════════════════════ */
let vibrationFrame = null;
const needleElements = [];

function startNeedleVibration() {
  // Collect all needle elements
  needleElements.length = 0;
  document.querySelectorAll(".dial-needle").forEach(el => needleElements.push(el));

  function vibrate() {
    needleElements.forEach(el => {
      // Add tiny random jitter via a wrapper transform
      const jitter = (Math.random() - 0.5) * 0.4; // ±0.2 degrees
      el.style.filter = `drop-shadow(0 0 1px rgba(201,168,76,0.3))`;
      // We apply jitter as a very subtle additional rotation via CSS custom property
      el.style.setProperty("--jitter", jitter + "deg");
    });
    vibrationFrame = requestAnimationFrame(vibrate);
  }
  // Run at low frequency to avoid performance issues
  function slowVibrate() {
    needleElements.forEach(el => {
      const jitter = (Math.random() - 0.5) * 0.5;
      const currentTransform = el.getAttribute("transform") || "";
      // Don't override main rotation, just add visual micro-movement via filter
      el.style.filter = `drop-shadow(${jitter}px 0 1px rgba(201,168,76,0.2))`;
    });
    vibrationFrame = setTimeout(slowVibrate, 150);
  }
  slowVibrate();
}

function stopNeedleVibration() {
  if (vibrationFrame) {
    clearTimeout(vibrationFrame);
    cancelAnimationFrame(vibrationFrame);
    vibrationFrame = null;
  }
}

/* ═══════════════════════════════════════════════════════════════════
   CLOCK
   ═══════════════════════════════════════════════════════════════════ */
function updateClock() {
  const now = new Date();
  $clockDisplay.textContent = now.toTimeString().slice(0, 8);
}

/* ═══════════════════════════════════════════════════════════════════
   AUDIO INTEGRATION
   ═══════════════════════════════════════════════════════════════════ */
let audioEnabled = false;

function initAudioUI() {
  $audioToggle.addEventListener("click", () => {
    if (!audioEnabled) {
      if (typeof NauticalAudio !== "undefined") {
        NauticalAudio.init();
        NauticalAudio.setVolume(parseInt($volumeSlider.value, 10) / 100);
        NauticalAudio.setWeather(weatherData.condition);
      }
      audioEnabled = true;
      $audioToggle.classList.add("active");
      $toggleIcon.innerHTML = "&#9724;";
      $toggleText.textContent = "Disable Ambient Sound";
      $volumeSlider.disabled = false;
      $soundModeValue.textContent = weatherData.condition.charAt(0).toUpperCase() + weatherData.condition.slice(1);
    } else {
      if (typeof NauticalAudio !== "undefined") {
        NauticalAudio.stop();
      }
      audioEnabled = false;
      $audioToggle.classList.remove("active");
      $toggleIcon.innerHTML = "&#9654;";
      $toggleText.textContent = "Enable Ambient Sound";
      $volumeSlider.disabled = true;
      $soundModeValue.textContent = "Off";
    }
  });

  $volumeSlider.addEventListener("input", () => {
    const vol = parseInt($volumeSlider.value, 10);
    $volumeValue.textContent = vol + "%";
    if (audioEnabled && typeof NauticalAudio !== "undefined") {
      NauticalAudio.setVolume(vol / 100);
    }
  });
}

function syncAudioToWeather(condition) {
  if (audioEnabled && typeof NauticalAudio !== "undefined") {
    NauticalAudio.setWeather(condition);
    $soundModeValue.textContent = condition.charAt(0).toUpperCase() + condition.slice(1);
  }
}

/* ═══════════════════════════════════════════════════════════════════
   VESSEL REACTION LAYER — intake state → weather → vessel/gauges
   ═══════════════════════════════════════════════════════════════════ */

function updateIntakePanelFromState(ie) {
  const score = ie.latest_score;
  const scoreValEl  = document.getElementById('intakeScoreVal');
  const scoreRingEl = document.getElementById('intakeScoreRing');
  const statusEl    = document.getElementById('intakeStatus');
  const totalEl     = document.getElementById('intakeTotal');
  const typeEl      = document.getElementById('intakeLastType');
  const idEl        = document.getElementById('intakeLatestId');
  const missingEl   = document.getElementById('intakeMissing');

  if (scoreValEl) scoreValEl.textContent = score != null ? score : '—';
  if (scoreRingEl && score != null) {
    const pct = Math.max(0, Math.min(score, 100));
    scoreRingEl.style.background =
      'conic-gradient(#2ecc71 0% ' + pct + '%, #1a2a3c ' + pct + '% 100%)';
  }
  if (statusEl)  statusEl.textContent  = ie.status        || '—';
  if (totalEl)   totalEl.textContent   = ie.total_submissions != null ? ie.total_submissions : '—';
  if (typeEl)    typeEl.textContent    = ie.latest_type    || '—';
  if (idEl)      idEl.textContent      = ie.latest_id      || '—';
  if (missingEl) {
    const missing = ie.latest_missing || [];
    missingEl.textContent = missing.length === 0 ? 'None' : missing.length + ' field(s)';
  }
}

/* ── RAIL READINESS COLOR ──────────────────────────────────────── */
function railReadinessColor(score) {
  if (score >= 80) return '#2ecc71';   // green — ready
  if (score >= 40) return '#f1c40f';   // gold  — partial
  return '#e74c3c';                    // red   — low
}

/* ── OPERATOR RAIL PANEL ───────────────────────────────────────── */
function updateOperatorRailPanel(rail, ie) {
  const panel = document.getElementById('operatorRailPanel');
  if (!panel) return;
  if (!rail) { panel.style.display = 'none'; return; }

  panel.style.display = '';
  const score = rail.readiness_score != null ? rail.readiness_score : 0;
  const color = railReadinessColor(score);
  panel.style.borderColor = color;

  const ringEl = document.getElementById('orReadiness');
  if (ringEl) { ringEl.textContent = score + '%'; ringEl.style.borderColor = color; ringEl.style.color = color; }

  const set = function(id, val) { const el = document.getElementById(id); if (el) el.textContent = val || '—'; };
  set('orEntityType',  rail.entity_type_label);
  set('orServiceType', rail.operator_type_label);
  set('orServiceArea', rail.service_area);
  if (ie) set('orLatestId', ie.latest_id);

  const compEl = document.getElementById('orCompliance');
  if (compEl) {
    compEl.textContent = rail.compliance_complete ? 'Complete' : 'Partial';
    compEl.style.color = rail.compliance_complete ? '#2ecc71' : '#f1c40f';
  }

  const missingEl = document.getElementById('orMissing');
  if (missingEl) {
    const m = rail.missing_compliance || [];
    missingEl.textContent = m.length === 0 ? 'None' : m.join(', ');
    missingEl.style.color = m.length === 0 ? '#2ecc71' : '#f1c40f';
  }
}

/* ── LABOR RAIL PANEL ──────────────────────────────────────────── */
function updateLaborRailPanel(lrail, ie) {
  const panel = document.getElementById('laborRailPanel');
  if (!panel) return;
  if (!lrail) { panel.style.display = 'none'; return; }

  panel.style.display = '';
  const score = lrail.readiness_score != null ? lrail.readiness_score : 0;
  const color = railReadinessColor(score);
  panel.style.borderColor = color;

  const ringEl = document.getElementById('lrReadiness');
  if (ringEl) { ringEl.textContent = score + '%'; ringEl.style.borderColor = color; ringEl.style.color = color; }

  const set = function(id, val) { const el = document.getElementById(id); if (el) el.textContent = val || '—'; };
  set('lrRole',         lrail.role_type_label);
  set('lrAvailability', lrail.availability_label);
  set('lrLocation',     lrail.labor_location);
  if (ie) set('lrLatestId', ie.latest_id);

  const crewEl = document.getElementById('lrCrewReady');
  if (crewEl) {
    crewEl.textContent = lrail.crew_ready ? 'Crew Ready' : 'Incomplete';
    crewEl.style.color = lrail.crew_ready ? '#2ecc71' : '#f1c40f';
  }

  const missingEl = document.getElementById('lrMissing');
  if (missingEl) {
    const m = lrail.missing_readiness || [];
    missingEl.textContent = m.length === 0 ? 'None' : m.join(', ');
    missingEl.style.color = m.length === 0 ? '#2ecc71' : '#f1c40f';
  }
}

/* ── LEGAL RAIL PANEL ──────────────────────────────────────────── */
function updateLegalRailPanel(lrail, ie) {
  const panel = document.getElementById('legalRailPanel');
  if (!panel) return;
  if (!lrail) { panel.style.display = 'none'; return; }

  panel.style.display = '';
  const standing = lrail.standing;
  const color = standing ? '#c9a84c' : '#e74c3c';
  panel.style.borderColor = color;

  const ringEl = document.getElementById('lgStanding');
  if (ringEl) {
    ringEl.textContent = standing ? 'PASS' : 'FAIL';
    ringEl.style.borderColor = color;
    ringEl.style.color = color;
  }

  const set = function(id, val) { const el = document.getElementById(id); if (el) el.textContent = val || '—'; };
  set('lgTarget',       lrail.target_name);
  set('lgTargetType',   lrail.target_type ? lrail.target_type.charAt(0).toUpperCase() + lrail.target_type.slice(1) : null);
  set('lgImmunityRisk', lrail.immunity_risk);
  if (ie) set('lgLatestId', ie.latest_id);

  const elLabel = document.getElementById('lgStandingLabel');
  if (elLabel) {
    const sl = (lrail.standing_label || '').replace(/_/g, ' ');
    elLabel.textContent = sl || '—';
    elLabel.style.color = standing ? '#2ecc71' : '#f1c40f';
  }
}

function syncIntakeToSystemState() {
  if (intakeState.score === null) return;
  systemState.evidence = intakeState.score;
  const penalty = Math.min(intakeState.missing.length * 8, 60);
  systemState.compliance = Math.max(25, 94 - penalty);
}

function deriveWeatherFromIntake() {
  if (intakeState.score === null) return null;
  const score        = intakeState.score;
  const missingCount = intakeState.missing.length;
  const isComplete   = intakeState.status === 'complete' && missingCount === 0;
  const highActivity = intakeState.totalSubmissions > 3;

  if (highActivity && missingCount > 2) return 'storm';   // high activity + incomplete = storm
  if (missingCount > 0 && score < 50)   return 'fog';    // missing evidence / weak score = fog
  if (missingCount > 0)                  return 'rain';   // partial intake = rain
  if (isComplete && score >= 90)         return 'clear';  // strong complete = clear
  if (isComplete && score >= 60)         return 'cloudy'; // moderate complete = cloudy calm
  return 'cloudy';
}

function applyDerivedWeather() {
  if (window._deckManualWeatherMode) return;
  const derived = deriveWeatherFromIntake();
  if (!derived || derived === weatherData.condition) return;
  const profile = WEATHER_PROFILES[derived] || WEATHER_PROFILES['clear'];
  weatherData.condition      = derived;
  weatherData.wind_speed     = profile.wind_speed;
  weatherData.wind_direction = profile.wind_direction;
  weatherData.humidity       = profile.humidity;
  weatherData.visibility     = profile.visibility;
  weatherData.temperature    = profile.temperature;
  updateWeatherVisuals(derived);
  updateVesselMotion();
  updateNavIndicators();
  updateEnvironmentPanel(weatherData);
  syncAudioToWeather(derived);
  if ($weatherBadge) $weatherBadge.textContent = derived.toUpperCase();
}

function checkForNewIntake(newId) {
  if (intakeState.lastId !== null && newId !== null && intakeState.lastId !== newId) {
    onNewIntakeDetected();
  }
}

function onNewIntakeDetected() {
  // Pulse all ops dials
  Object.keys(systemState).forEach(key => {
    const dial = document.querySelector('.ops-dial[data-key="' + key + '"]');
    if (!dial) return;
    dial.classList.remove('gauge-updated');
    void dial.offsetWidth;
    dial.classList.add('gauge-updated');
    setTimeout(() => dial.classList.remove('gauge-updated'), 900);
  });

  // Water surge
  const waterLayer = document.getElementById('waterLayer');
  if (waterLayer) {
    waterLayer.classList.remove('water-surge');
    void waterLayer.offsetWidth;
    waterLayer.classList.add('water-surge');
    setTimeout(() => waterLayer.classList.remove('water-surge'), 1800);
  }

  // Vessel surge
  const vessel = document.getElementById('vessel');
  if (vessel) {
    vessel.classList.add('motion-surge');
    setTimeout(() => vessel.classList.remove('motion-surge'), 2200);
  }

  // Derived weather + visuals
  applyDerivedWeather();
  updateOpsDials();
  updateStatusDial();

  // Flash weather badge
  if ($weatherBadge) {
    $weatherBadge.classList.remove('badge-flash');
    void $weatherBadge.offsetWidth;
    $weatherBadge.classList.add('badge-flash');
    setTimeout(() => $weatherBadge.classList.remove('badge-flash'), 1400);
  }

  // Activity banner
  const banner = document.getElementById('activityBanner');
  if (banner) {
    banner.textContent = 'Recent system activity detected';
    banner.classList.remove('active');
    void banner.offsetWidth;
    banner.classList.add('active');
    setTimeout(() => banner.classList.remove('active'), 9000);
  }
}

/* ═══════════════════════════════════════════════════════════════════
   MASTER UPDATE — called every refresh cycle
   ═══════════════════════════════════════════════════════════════════ */
/* ═══════════════════════════════════════════════════════════════════
   NAVIGATION INDICATORS — update weather & health dots in nav bar
   ═══════════════════════════════════════════════════════════════════ */
function updateNavIndicators() {
  // Weather indicator
  if ($navWeatherDot && $navWeatherLabel) {
    // Remove all weather-* classes, add current
    $navWeatherDot.className = "indicator-dot weather-dot weather-" + weatherData.condition;
    $navWeatherLabel.textContent = weatherData.condition.charAt(0).toUpperCase() + weatherData.condition.slice(1);
  }

  // Health indicator — average of all systemState values
  if ($navHealthDot && $navHealthLabel) {
    const keys = Object.keys(systemState);
    const avg = keys.reduce((sum, k) => sum + systemState[k], 0) / keys.length;
    let healthClass, healthText;
    if (avg >= 75) {
      healthClass = "health-green";
      healthText = "Nominal";
    } else if (avg >= 50) {
      healthClass = "health-yellow";
      healthText = "Caution";
    } else {
      healthClass = "health-red";
      healthText = "Critical";
    }
    $navHealthDot.className = "indicator-dot health-dot " + healthClass;
    $navHealthLabel.textContent = healthText;
  }
}

function masterUpdate() {
  // Advance weather state machine
  weatherIndex = (weatherIndex + 1) % WEATHER_CYCLE.length;
  const newCondition = WEATHER_CYCLE[weatherIndex];
  const profile = WEATHER_PROFILES[newCondition];

  // Update weather data object
  weatherData.condition      = newCondition;
  weatherData.temperature    = profile.temperature + Math.floor(Math.random() * 5 - 2);
  weatherData.wind_speed     = profile.wind_speed + Math.floor(Math.random() * 5 - 2);
  weatherData.wind_direction = profile.wind_direction;
  weatherData.humidity       = profile.humidity + Math.floor(Math.random() * 5 - 2);
  weatherData.visibility     = profile.visibility;

  // Randomize operational data
  randomizeSystemState();

  // Push updates to all visuals
  updateWeatherVisuals(weatherData.condition);
  updateCompass(weatherData.wind_direction);
  updateWindDial(weatherData.wind_speed, weatherData.wind_direction);
  updateEnvironmentPanel(weatherData);
  updateStatusDial();
  updateCaseFlow();
  updateComplianceDial(systemState.compliance);
  updateOpsDials();
  updateNavIndicators();

  // Sync audio (crossfade handled inside audio engine)
  syncAudioToWeather(weatherData.condition);
}

/* ═══════════════════════════════════════════════════════════════════
   REFRESH TIMER
   ═══════════════════════════════════════════════════════════════════ */
const REFRESH_INTERVAL = 30;
let countdown = REFRESH_INTERVAL;

function tickCountdown() {
  countdown--;
  if (countdown <= 0) {
    masterUpdate();
    countdown = REFRESH_INTERVAL;
  }
  $refreshTimer.textContent = `Next update in ${countdown}s`;
}

/* ═══════════════════════════════════════════════════════════════════
   COMPASS TICK MARKS
   ═══════════════════════════════════════════════════════════════════ */
function drawCompassTicks() {
  const g = document.getElementById("compassTicks");
  if (!g) return;
  let html = "";
  for (let deg = 0; deg < 360; deg += 10) {
    const rad = (deg - 90) * Math.PI / 180;
    const inner = deg % 30 === 0 ? 75 : 82;
    const outer = 88;
    const x1 = 100 + inner * Math.cos(rad);
    const y1 = 100 + inner * Math.sin(rad);
    const x2 = 100 + outer * Math.cos(rad);
    const y2 = 100 + outer * Math.sin(rad);
    const sw = deg % 30 === 0 ? 1.2 : 0.5;
    html += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke-width="${sw}"/>`;
  }
  g.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════
   CYCLE 4 — TOOLTIP SYSTEM
   ═══════════════════════════════════════════════════════════════════ */
const GAUGE_TOOLTIPS = {
  "standing":     { title: "Standing",     desc: "Legal standing readiness score",           unit: "%", source: "system" },
  "capacity":     { title: "Capacity",     desc: "Operational capacity utilization",         unit: "%", source: "system" },
  "jurisdiction": { title: "Jurisdiction", desc: "Jurisdictional coverage confidence",       unit: "%", source: "system" },
  "evidence":     { title: "Evidence",     desc: "Evidence documentation completeness",     unit: "%", source: "system" },
  "compliance":   { title: "Compliance",   desc: "Regulatory compliance score",             unit: "%", source: "system" },
  "deployment":   { title: "Deployment",   desc: "Workforce deployment readiness",          unit: "%", source: "system" },
  "wind":         { title: "Wind",         desc: "Current wind speed and direction",        unit: "mph", source: "weather" },
  "temperature":  { title: "Temperature",  desc: "Ambient temperature",                     unit: "°F", source: "weather" },
  "humidity":     { title: "Humidity",     desc: "Relative humidity level",                 unit: "%", source: "weather" },
  "visibility":   { title: "Visibility",   desc: "Atmospheric visibility range",            unit: "mi", source: "weather" }
};

let tooltipEl = null;
let tooltipTimeout = null;

function createTooltipElement() {
  tooltipEl = document.createElement("div");
  tooltipEl.className = "deck-tooltip";
  tooltipEl.innerHTML = '<div class="deck-tooltip-inner">' +
    '<div class="tooltip-title"></div>' +
    '<div class="tooltip-desc"></div>' +
    '<div class="tooltip-value"></div>' +
    '<div class="tooltip-source"></div>' +
    '</div>' +
    '<div class="deck-tooltip-arrow"></div>';
  document.body.appendChild(tooltipEl);
}

function getGaugeValue(key) {
  if (key in systemState) return systemState[key];
  if (key === "wind") return weatherData.wind_speed + " " + weatherData.wind_direction;
  if (key === "temperature") return weatherData.temperature;
  if (key === "humidity") return weatherData.humidity;
  if (key === "visibility") return weatherData.visibility;
  return "--";
}

function getGaugeSource(key) {
  if (key in systemState) return "system";
  return dataSource === "live" ? "live" : "mock";
}

function showTooltip(el, key) {
  if (!tooltipEl) createTooltipElement();
  const info = GAUGE_TOOLTIPS[key];
  if (!info) return;

  const titleEl = tooltipEl.querySelector(".tooltip-title");
  const descEl = tooltipEl.querySelector(".tooltip-desc");
  const valueEl = tooltipEl.querySelector(".tooltip-value");
  const sourceEl = tooltipEl.querySelector(".tooltip-source");

  titleEl.textContent = info.title;
  descEl.textContent = info.desc;
  const val = getGaugeValue(key);
  valueEl.textContent = val + (typeof val === "number" ? info.unit : "");
  sourceEl.textContent = "Source: " + getGaugeSource(key);

  // Position
  const rect = el.getBoundingClientRect();
  const tooltipH = 100; // approximate
  const spaceAbove = rect.top;
  const above = spaceAbove > tooltipH + 10;

  tooltipEl.classList.remove("tooltip-above", "tooltip-below");
  tooltipEl.classList.add(above ? "tooltip-above" : "tooltip-below");

  let left = rect.left + rect.width / 2 - 110;
  if (left < 8) left = 8;
  if (left + 220 > window.innerWidth) left = window.innerWidth - 228;

  let top;
  if (above) {
    top = rect.top - tooltipH - 8;
  } else {
    top = rect.bottom + 8;
  }

  tooltipEl.style.left = left + "px";
  tooltipEl.style.top = top + "px";
  tooltipEl.classList.add("visible");
}

function hideTooltip() {
  if (tooltipEl) tooltipEl.classList.remove("visible");
}

function initTooltips() {
  // Ops dials (6 system gauges)
  document.querySelectorAll(".ops-dial[data-key]").forEach(dial => {
    const key = dial.getAttribute("data-key");
    dial.addEventListener("mouseenter", () => showTooltip(dial, key));
    dial.addEventListener("mouseleave", () => hideTooltip());
    dial.addEventListener("touchstart", (e) => {
      e.preventDefault();
      showTooltip(dial, key);
      clearTimeout(tooltipTimeout);
      tooltipTimeout = setTimeout(hideTooltip, 3000);
    }, { passive: false });
  });

  // Instrument panels — wind (windPanel), compass is not a data gauge
  const windPanel = document.getElementById("windPanel");
  if (windPanel) {
    windPanel.addEventListener("mouseenter", () => showTooltip(windPanel, "wind"));
    windPanel.addEventListener("mouseleave", () => hideTooltip());
    windPanel.addEventListener("touchstart", (e) => {
      e.preventDefault();
      showTooltip(windPanel, "wind");
      clearTimeout(tooltipTimeout);
      tooltipTimeout = setTimeout(hideTooltip, 3000);
    }, { passive: false });
  }

  // Environment strip items
  const envMap = [
    { id: "tempValue", key: "temperature" },
    { id: "humidityValue", key: "humidity" },
    { id: "visibilityValue", key: "visibility" }
  ];
  envMap.forEach(({ id, key }) => {
    const el = document.getElementById(id);
    if (!el) return;
    const parent = el.closest(".env-item");
    if (!parent) return;
    parent.addEventListener("mouseenter", () => showTooltip(parent, key));
    parent.addEventListener("mouseleave", () => hideTooltip());
    parent.addEventListener("touchstart", (e) => {
      e.preventDefault();
      showTooltip(parent, key);
      clearTimeout(tooltipTimeout);
      tooltipTimeout = setTimeout(hideTooltip, 3000);
    }, { passive: false });
  });

  // Tap-away to dismiss on mobile
  document.addEventListener("touchstart", (e) => {
    if (tooltipEl && !e.target.closest(".ops-dial, .instrument-panel, .env-item")) {
      hideTooltip();
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════
   CYCLE 4 — VALUE UPDATE ANIMATION
   ═══════════════════════════════════════════════════════════════════ */
let prevSystemState = {};
let prevWeatherData = {};

function detectAndAnimateChanges() {
  // Check system state changes
  Object.keys(systemState).forEach(key => {
    if (prevSystemState[key] !== undefined && prevSystemState[key] !== systemState[key]) {
      const dial = document.querySelector('.ops-dial[data-key="' + key + '"]');
      if (dial) {
        dial.classList.remove("gauge-updated");
        void dial.offsetWidth;
        dial.classList.add("gauge-updated");
        setTimeout(() => dial.classList.remove("gauge-updated"), 600);
      }
    }
    prevSystemState[key] = systemState[key];
  });

  // Check weather changes
  ["temperature", "humidity", "visibility", "wind_speed"].forEach(key => {
    if (prevWeatherData[key] !== undefined && prevWeatherData[key] !== weatherData[key]) {
      const idMap = { temperature: "tempValue", humidity: "humidityValue", visibility: "visibilityValue", wind_speed: "windReadout" };
      const el = document.getElementById(idMap[key]);
      if (el) {
        const parent = el.closest(".env-item") || el.closest(".instrument-panel");
        if (parent) {
          parent.classList.remove("gauge-updated");
          void parent.offsetWidth;
          parent.classList.add("gauge-updated");
          setTimeout(() => parent.classList.remove("gauge-updated"), 600);
        }
      }
    }
    prevWeatherData[key] = weatherData[key];
  });
}

// Wrap fetchAllDeckData to detect changes after fetch
const _originalFetchAllDeckData = fetchAllDeckData;
async function fetchAllDeckDataWithAnimation() {
  await _originalFetchAllDeckData();
  detectAndAnimateChanges();
}

/* ═══════════════════════════════════════════════════════════════════
   INITIALIZATION
   ═══════════════════════════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  drawCompassTicks();
  generateStars();

  // Initial state
  updateWeatherVisuals(weatherData.condition);
  updateCompass(weatherData.wind_direction);
  updateWindDial(weatherData.wind_speed, weatherData.wind_direction);
  updateEnvironmentPanel(weatherData);
  updateStatusDial();
  updateCaseFlow();
  updateComplianceDial(systemState.compliance);
  updateOpsDials();
  updateNavIndicators();

  // Audio UI
  initAudioUI();

  // Clock
  updateClock();
  setInterval(updateClock, 1000);

  // Tooltips
  initTooltips();

  // Snapshot initial state for change detection
  Object.keys(systemState).forEach(k => { prevSystemState[k] = systemState[k]; });
  ["temperature", "humidity", "visibility", "wind_speed"].forEach(k => { prevWeatherData[k] = weatherData[k]; });

  // Geolocation + API data fetch
  initGeolocation();
  fetchAllDeckDataWithAnimation();
  setInterval(fetchAllDeckDataWithAnimation, 30000);

  // Data source and location indicators
  updateDataSourceIndicator();
  updateLocationStatusUI();

  // Refresh cycle
  setInterval(tickCountdown, 1000);

  // Needle vibration
  setTimeout(startNeedleVibration, 2000);

  // Initialize vessel motion
  updateVesselMotion();
});
/* === CABIN LIGHT SWITCH === */
(function () {
  const btn = document.getElementById("cabinLightToggle");
  const label = document.getElementById("cabinLightState");

  if (!btn || !label) return;

  const states = ["on", "dim", "off"];

  function apply(state) {
    document.body.classList.remove(
      "cabin-light-on",
      "cabin-light-dim",
      "cabin-light-off"
    );

    document.body.classList.add("cabin-light-" + state);
    label.textContent = state.charAt(0).toUpperCase() + state.slice(1);
    localStorage.setItem("cabinLight", state);
  }

  const saved = localStorage.getItem("cabinLight") || "on";
  apply(saved);

  btn.addEventListener("click", () => {
    const current = localStorage.getItem("cabinLight") || "on";
    const next = states[(states.indexOf(current) + 1) % states.length];
    apply(next);
  });
})();

/* === CERTIFICATION STRICTNESS CONTROL === */
(function () {
  const buttons = document.querySelectorAll("#certStrictnessButtons .ops-ctrl-btn");
  if (!buttons.length) return;

  function applyStrictness(level) {
    buttons.forEach(b => b.classList.toggle("active", b.dataset.level === level));
    localStorage.setItem("certStrictness", level);
    fetch("/api/command-deck/operator-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cert_strictness: level }),
    }).catch(() => {});
  }

  const saved = localStorage.getItem("certStrictness") || "normal";
  applyStrictness(saved);

  buttons.forEach(btn => {
    btn.addEventListener("click", () => applyStrictness(btn.dataset.level));
  });
})();

/* === MANUAL WEATHER OVERRIDE === */
(function () {
  window._deckManualWeatherMode = false;

  const wxButtons     = document.querySelectorAll("#weatherConditionButtons .wx-btn");
  const resetBtn      = document.getElementById("weatherResetBtn");
  const modeIndicator = document.getElementById("weatherModeIndicator");

  if (!wxButtons.length) return;

  function setManualWeather(condition) {
    window._deckManualWeatherMode = true;
    if (modeIndicator) {
      modeIndicator.textContent = "MANUAL";
      modeIndicator.classList.add("manual");
    }
    wxButtons.forEach(b => b.classList.toggle("active", b.dataset.condition === condition));
    weatherData.condition      = condition;
    const profile = WEATHER_PROFILES[condition] || WEATHER_PROFILES["clear"];
    weatherData.wind_speed     = profile.wind_speed;
    weatherData.wind_direction = profile.wind_direction;
    weatherData.humidity       = profile.humidity;
    weatherData.visibility     = profile.visibility;
    weatherData.temperature    = profile.temperature;
    updateWeatherVisuals(condition);
    updateVesselMotion();
    updateNavIndicators();
    updateEnvironmentPanel(weatherData);
    if (typeof syncAudioToWeather === "function") syncAudioToWeather(condition);
    if ($weatherBadge) $weatherBadge.textContent = condition.toUpperCase();
  }

  function resetToAuto() {
    window._deckManualWeatherMode = false;
    if (modeIndicator) {
      modeIndicator.textContent = "AUTO";
      modeIndicator.classList.remove("manual");
    }
    wxButtons.forEach(b => b.classList.remove("active"));
  }

  wxButtons.forEach(btn => {
    btn.addEventListener("click", () => setManualWeather(btn.dataset.condition));
  });

  if (resetBtn) resetBtn.addEventListener("click", resetToAuto);
})();
