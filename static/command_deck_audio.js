/* ═══════════════════════════════════════════════════════════════════
   Nautical Compass — Adaptive Ambient Sound Engine v2
   ═══════════════════════════════════════════════════════════════════
   Enhanced: proper crossfade transitions, richer texture layers,
   smooth volume ramping, additional sound effects per weather state.

   PUBLIC API:
     NauticalAudio.init()                 — create AudioContext (user gesture)
     NauticalAudio.setWeather(condition)  — crossfade to new soundscape
     NauticalAudio.setVolume(0..1)        — master volume (smooth ramp)
     NauticalAudio.stop()                 — silence & suspend
     NauticalAudio.isPlaying()            — boolean
   ═══════════════════════════════════════════════════════════════════ */

const NauticalAudio = (() => {

  /* ── PRIVATE STATE ───────────────────────────────────────────── */
  let ctx            = null;
  let masterGain     = null;
  let currentWeather = null;
  let activeLayers   = [];
  let fadingLayers   = [];   // layers currently fading out
  let isInit         = false;
  let _volume        = 0.30;
  const FADE_IN      = 2.5;  // seconds
  const FADE_OUT     = 3.0;  // seconds — longer for smooth crossfade

  /* ═══════════════════════════════════════════════════════════════
     NOISE GENERATORS
     ═══════════════════════════════════════════════════════════════ */

  function createNoiseBuffer(seconds = 2) {
    const length = ctx.sampleRate * seconds;
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data   = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
    return buffer;
  }

  /** Pink noise approximation (more natural than white) */
  function createPinkNoiseBuffer(seconds = 2) {
    const length = ctx.sampleRate * seconds;
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data   = buffer.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (let i = 0; i < length; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + white * 0.0555179;
      b1 = 0.99332 * b1 + white * 0.0750759;
      b2 = 0.96900 * b2 + white * 0.1538520;
      b3 = 0.86650 * b3 + white * 0.3104856;
      b4 = 0.55000 * b4 + white * 0.5329522;
      b5 = -0.7616 * b5 - white * 0.0168980;
      data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11;
      b6 = white * 0.115926;
    }
    return buffer;
  }

  function makeFilteredNoise(opts) {
    const { type = "lowpass", frequency = 800, Q = 1, gain = 0.15, pink = false } = opts;
    const buf = pink ? createPinkNoiseBuffer(2) : createNoiseBuffer(2);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop   = true;

    const filter = ctx.createBiquadFilter();
    filter.type  = type;
    filter.frequency.value = frequency;
    filter.Q.value = Q;

    const gn = ctx.createGain();
    gn.gain.setValueAtTime(0, ctx.currentTime);
    gn.gain.linearRampToValueAtTime(gain, ctx.currentTime + FADE_IN);

    src.connect(filter).connect(gn).connect(masterGain);
    src.start();

    return { source: src, gain: gn, filter, type: "noise" };
  }

  /* ═══════════════════════════════════════════════════════════════
     OSCILLATOR HELPERS
     ═══════════════════════════════════════════════════════════════ */

  function makeOscillator(opts) {
    const { type = "sine", frequency = 200, gain = 0.05 } = opts;
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.value = frequency;

    const gn = ctx.createGain();
    gn.gain.setValueAtTime(0, ctx.currentTime);
    gn.gain.linearRampToValueAtTime(gain, ctx.currentTime + FADE_IN);

    osc.connect(gn).connect(masterGain);
    osc.start();

    return { source: osc, gain: gn, type: "osc" };
  }

  function makeLFOOscillator(opts) {
    const { type = "sine", frequency = 180, gain = 0.04, lfoRate = 0.15, lfoDepth = 30 } = opts;
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.value = frequency;

    const lfo = ctx.createOscillator();
    lfo.type = "sine";
    lfo.frequency.value = lfoRate;

    const lfoGain = ctx.createGain();
    lfoGain.gain.value = lfoDepth;

    lfo.connect(lfoGain).connect(osc.frequency);
    lfo.start();

    const gn = ctx.createGain();
    gn.gain.setValueAtTime(0, ctx.currentTime);
    gn.gain.linearRampToValueAtTime(gain, ctx.currentTime + FADE_IN);

    osc.connect(gn).connect(masterGain);
    osc.start();

    return { source: osc, gain: gn, lfo, type: "lfo-osc" };
  }

  /* ═══════════════════════════════════════════════════════════════
     ONE-SHOT SOUND GENERATORS
     ═══════════════════════════════════════════════════════════════ */

  /* ── THUNDER ─────────────────────────────────────────────────── */
  let thunderTimer = null;

  function triggerThunder(intensity = 1.0) {
    if (!ctx || ctx.state !== "running") return;
    const buf  = createNoiseBuffer(3);
    const src  = ctx.createBufferSource();
    src.buffer = buf;

    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 120 + intensity * 80;
    lp.Q.value = 0.7;

    const gn = ctx.createGain();
    const now = ctx.currentTime;
    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.3 * intensity * _volume, now + 0.04);
    gn.gain.setValueAtTime(0.3 * intensity * _volume, now + 0.08);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 2.5 + intensity);

    src.connect(lp).connect(gn).connect(masterGain);
    src.start(now);
    src.stop(now + 3.5);
  }

  function startThunderLoop(intensity = 1.0) {
    stopThunderLoop();
    const fire = () => {
      triggerThunder(intensity);
      const interval = intensity > 0.7 ? (2000 + Math.random() * 4000) : (5000 + Math.random() * 8000);
      thunderTimer = setTimeout(fire, interval);
    };
    thunderTimer = setTimeout(fire, 1000 + Math.random() * 2000);
  }

  function stopThunderLoop() {
    if (thunderTimer) { clearTimeout(thunderTimer); thunderTimer = null; }
  }

  /* ── FOGHORN ─────────────────────────────────────────────────── */
  let foghornTimer = null;

  function triggerFoghorn() {
    if (!ctx || ctx.state !== "running") return;
    const osc = ctx.createOscillator();
    osc.type = "sawtooth";
    osc.frequency.value = 82;

    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 180;

    const gn = ctx.createGain();
    const now = ctx.currentTime;
    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.10 * _volume, now + 0.8);
    gn.gain.setValueAtTime(0.10 * _volume, now + 2.2);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 3.8);

    osc.connect(lp).connect(gn).connect(masterGain);
    osc.start(now);
    osc.stop(now + 4.0);
  }

  function startFoghornLoop() {
    stopFoghornLoop();
    const fire = () => {
      triggerFoghorn();
      foghornTimer = setTimeout(fire, 9000 + Math.random() * 7000);
    };
    foghornTimer = setTimeout(fire, 2500);
  }

  function stopFoghornLoop() {
    if (foghornTimer) { clearTimeout(foghornTimer); foghornTimer = null; }
  }

  /* ── DISTANT SHIP HORN (fog response) ────────────────────────── */
  let distantHornTimer = null;

  function triggerDistantHorn() {
    if (!ctx || ctx.state !== "running") return;
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = 140;

    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 250;

    const gn = ctx.createGain();
    const now = ctx.currentTime;
    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.04 * _volume, now + 0.5);
    gn.gain.setValueAtTime(0.04 * _volume, now + 1.5);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 2.8);

    osc.connect(lp).connect(gn).connect(masterGain);
    osc.start(now);
    osc.stop(now + 3.0);
  }

  function startDistantHornLoop() {
    stopDistantHornLoop();
    const fire = () => {
      triggerDistantHorn();
      distantHornTimer = setTimeout(fire, 15000 + Math.random() * 10000);
    };
    distantHornTimer = setTimeout(fire, 6000);
  }

  function stopDistantHornLoop() {
    if (distantHornTimer) { clearTimeout(distantHornTimer); distantHornTimer = null; }
  }

  /* ── SEABIRD CHIRP ───────────────────────────────────────────── */
  let birdTimer = null;

  function triggerBirdCall() {
    if (!ctx || ctx.state !== "running") return;
    const osc = ctx.createOscillator();
    osc.type = "sine";
    const baseFreq = 2200 + Math.random() * 800;
    osc.frequency.value = baseFreq;

    const gn = ctx.createGain();
    const now = ctx.currentTime;

    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.05 * _volume, now + 0.02);
    osc.frequency.linearRampToValueAtTime(baseFreq + 400, now + 0.08);
    gn.gain.linearRampToValueAtTime(0.0, now + 0.12);
    gn.gain.linearRampToValueAtTime(0.04 * _volume, now + 0.2);
    osc.frequency.linearRampToValueAtTime(baseFreq + 300, now + 0.28);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

    osc.connect(gn).connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.4);
  }

  function startBirdLoop() {
    stopBirdLoop();
    const fire = () => {
      triggerBirdCall();
      birdTimer = setTimeout(fire, 3000 + Math.random() * 7000);
    };
    birdTimer = setTimeout(fire, 1500);
  }

  function stopBirdLoop() {
    if (birdTimer) { clearTimeout(birdTimer); birdTimer = null; }
  }

  /* ── BELL BUOY (clear weather — distant bell) ────────────────── */
  let bellTimer = null;

  function triggerBellBuoy() {
    if (!ctx || ctx.state !== "running") return;
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = 1200;

    const osc2 = ctx.createOscillator();
    osc2.type = "sine";
    osc2.frequency.value = 1800;

    const gn = ctx.createGain();
    const now = ctx.currentTime;
    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.025 * _volume, now + 0.005);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 1.5);

    const gn2 = ctx.createGain();
    gn2.gain.setValueAtTime(0, now);
    gn2.gain.linearRampToValueAtTime(0.015 * _volume, now + 0.005);
    gn2.gain.exponentialRampToValueAtTime(0.001, now + 1.0);

    osc.connect(gn).connect(masterGain);
    osc2.connect(gn2).connect(masterGain);
    osc.start(now);
    osc2.start(now);
    osc.stop(now + 1.6);
    osc2.stop(now + 1.1);
  }

  function startBellLoop() {
    stopBellLoop();
    const fire = () => {
      triggerBellBuoy();
      bellTimer = setTimeout(fire, 5000 + Math.random() * 8000);
    };
    bellTimer = setTimeout(fire, 3000);
  }

  function stopBellLoop() {
    if (bellTimer) { clearTimeout(bellTimer); bellTimer = null; }
  }

  /* ── HULL CREAK (clear + snow) ───────────────────────────────── */
  let creakTimer = null;

  function triggerCreak() {
    if (!ctx || ctx.state !== "running") return;
    const osc = ctx.createOscillator();
    osc.type = "sawtooth";
    const baseFreq = 55 + Math.random() * 40;
    osc.frequency.value = baseFreq;

    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = 280 + Math.random() * 200;
    bp.Q.value = 10;

    const gn = ctx.createGain();
    const now = ctx.currentTime;
    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.03 * _volume, now + 0.08);
    osc.frequency.linearRampToValueAtTime(baseFreq + 12, now + 0.4);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 0.7);

    osc.connect(bp).connect(gn).connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.8);
  }

  function startCreakLoop(interval = 5000) {
    stopCreakLoop();
    const fire = () => {
      triggerCreak();
      creakTimer = setTimeout(fire, interval + Math.random() * interval);
    };
    creakTimer = setTimeout(fire, 2000);
  }

  function stopCreakLoop() {
    if (creakTimer) { clearTimeout(creakTimer); creakTimer = null; }
  }

  /* ── METAL STRESS (storm) ────────────────────────────────────── */
  let metalTimer = null;

  function triggerMetalStress() {
    if (!ctx || ctx.state !== "running") return;
    const osc = ctx.createOscillator();
    osc.type = "square";
    osc.frequency.value = 35 + Math.random() * 20;

    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 400;
    hp.Q.value = 12;

    const gn = ctx.createGain();
    const now = ctx.currentTime;
    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.025 * _volume, now + 0.02);
    osc.frequency.linearRampToValueAtTime(osc.frequency.value + 8, now + 0.3);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 0.5);

    osc.connect(hp).connect(gn).connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.6);
  }

  function startMetalLoop() {
    stopMetalLoop();
    const fire = () => {
      triggerMetalStress();
      metalTimer = setTimeout(fire, 3000 + Math.random() * 5000);
    };
    metalTimer = setTimeout(fire, 1500);
  }

  function stopMetalLoop() {
    if (metalTimer) { clearTimeout(metalTimer); metalTimer = null; }
  }

  /* ── DRIPPING (rain — rigging drip) ──────────────────────────── */
  let dripTimer = null;

  function triggerDrip() {
    if (!ctx || ctx.state !== "running") return;
    const osc = ctx.createOscillator();
    osc.type = "sine";
    const freq = 3000 + Math.random() * 2000;
    osc.frequency.value = freq;

    const gn = ctx.createGain();
    const now = ctx.currentTime;
    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.02 * _volume, now + 0.003);
    osc.frequency.exponentialRampToValueAtTime(freq * 0.4, now + 0.06);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 0.08);

    osc.connect(gn).connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.1);
  }

  function startDripLoop() {
    stopDripLoop();
    const fire = () => {
      triggerDrip();
      dripTimer = setTimeout(fire, 400 + Math.random() * 1200);
    };
    dripTimer = setTimeout(fire, 500);
  }

  function stopDripLoop() {
    if (dripTimer) { clearTimeout(dripTimer); dripTimer = null; }
  }

  /* ── WATER LAP (fog — hull lapping) ──────────────────────────── */
  let lapTimer = null;

  function triggerWaterLap() {
    if (!ctx || ctx.state !== "running") return;
    const buf = createPinkNoiseBuffer(1);
    const src = ctx.createBufferSource();
    src.buffer = buf;

    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 300;

    const gn = ctx.createGain();
    const now = ctx.currentTime;
    gn.gain.setValueAtTime(0, now);
    gn.gain.linearRampToValueAtTime(0.06 * _volume, now + 0.2);
    gn.gain.linearRampToValueAtTime(0.04 * _volume, now + 0.5);
    gn.gain.exponentialRampToValueAtTime(0.001, now + 1.2);

    src.connect(lp).connect(gn).connect(masterGain);
    src.start(now);
    src.stop(now + 1.3);
  }

  function startLapLoop() {
    stopLapLoop();
    const fire = () => {
      triggerWaterLap();
      lapTimer = setTimeout(fire, 2000 + Math.random() * 3000);
    };
    lapTimer = setTimeout(fire, 1000);
  }

  function stopLapLoop() {
    if (lapTimer) { clearTimeout(lapTimer); lapTimer = null; }
  }

  /* ═══════════════════════════════════════════════════════════════
     WEATHER SOUNDSCAPE BUILDERS
     ═══════════════════════════════════════════════════════════════ */

  function buildClear() {
    startBirdLoop();
    startBellLoop();
    startCreakLoop(8000); // gentle hull creak
    return [
      // Calm water — pink noise, very gentle
      makeFilteredNoise({ type: "lowpass", frequency: 350, Q: 0.5, gain: 0.07, pink: true }),
      // Soft ambient wind
      makeFilteredNoise({ type: "bandpass", frequency: 220, Q: 0.8, gain: 0.035, pink: true }),
      // Soft engine hum (distant)
      makeLFOOscillator({ type: "sine", frequency: 52, gain: 0.02, lfoRate: 0.06, lfoDepth: 3 }),
    ];
  }

  function buildCloudy() {
    return [
      // Low wind — bandpass pink noise
      makeFilteredNoise({ type: "bandpass", frequency: 380, Q: 1.2, gain: 0.10, pink: true }),
      // Muted water
      makeFilteredNoise({ type: "lowpass", frequency: 280, Q: 0.5, gain: 0.06, pink: true }),
      // Slight wind whistle
      makeLFOOscillator({ type: "sine", frequency: 320, gain: 0.015, lfoRate: 0.2, lfoDepth: 50 }),
    ];
  }

  function buildRain() {
    startDripLoop();
    startThunderLoop(0.4); // distant rumble
    return [
      // Rain on deck — bright noise
      makeFilteredNoise({ type: "highpass", frequency: 2800, Q: 0.3, gain: 0.11 }),
      // Rain body — mid
      makeFilteredNoise({ type: "bandpass", frequency: 1600, Q: 0.5, gain: 0.09, pink: true }),
      // Heavier water
      makeFilteredNoise({ type: "lowpass", frequency: 450, Q: 0.7, gain: 0.09, pink: true }),
      // Wind layer
      makeFilteredNoise({ type: "bandpass", frequency: 400, Q: 1.0, gain: 0.06, pink: true }),
      // Drip resonance (continuous)
      makeFilteredNoise({ type: "highpass", frequency: 4000, Q: 2, gain: 0.02 }),
    ];
  }

  function buildStorm() {
    startThunderLoop(1.0); // loud, frequent
    startMetalLoop();
    return [
      // Heavy rain
      makeFilteredNoise({ type: "highpass", frequency: 2200, Q: 0.3, gain: 0.16 }),
      makeFilteredNoise({ type: "bandpass", frequency: 1800, Q: 0.6, gain: 0.13, pink: true }),
      // Heavy waves — deep rumble
      makeFilteredNoise({ type: "lowpass", frequency: 180, Q: 1.0, gain: 0.15, pink: true }),
      // Strong wind
      makeFilteredNoise({ type: "bandpass", frequency: 550, Q: 1.5, gain: 0.13, pink: true }),
      // Wind howl
      makeLFOOscillator({ type: "sawtooth", frequency: 110, gain: 0.025, lfoRate: 0.35, lfoDepth: 45 }),
      // High wind whistle
      makeLFOOscillator({ type: "sine", frequency: 800, gain: 0.012, lfoRate: 0.5, lfoDepth: 100 }),
    ];
  }

  function buildFog() {
    startFoghornLoop();
    startDistantHornLoop();
    startLapLoop();
    return [
      // Low water — very muted
      makeFilteredNoise({ type: "lowpass", frequency: 220, Q: 0.4, gain: 0.045, pink: true }),
      // Muted wind
      makeFilteredNoise({ type: "bandpass", frequency: 180, Q: 0.6, gain: 0.035, pink: true }),
      // Eerie low drone
      makeOscillator({ type: "sine", frequency: 65, gain: 0.018 }),
      // Very subtle high atmosphere
      makeFilteredNoise({ type: "highpass", frequency: 6000, Q: 0.5, gain: 0.008 }),
    ];
  }

  function buildSnow() {
    startCreakLoop(4000); // more frequent creaking
    return [
      // Cold wind — higher, thinner
      makeFilteredNoise({ type: "bandpass", frequency: 750, Q: 2.0, gain: 0.08, pink: true }),
      // Soft wind undertone
      makeFilteredNoise({ type: "bandpass", frequency: 280, Q: 0.8, gain: 0.05, pink: true }),
      // Muted water
      makeFilteredNoise({ type: "lowpass", frequency: 180, Q: 0.4, gain: 0.035, pink: true }),
      // Ice/cold whistle
      makeLFOOscillator({ type: "sine", frequency: 1200, gain: 0.008, lfoRate: 0.1, lfoDepth: 80 }),
    ];
  }

  const BUILDERS = {
    clear:  buildClear,
    cloudy: buildCloudy,
    rain:   buildRain,
    storm:  buildStorm,
    fog:    buildFog,
    snow:   buildSnow
  };

  /* ═══════════════════════════════════════════════════════════════
     CROSSFADE LAYER MANAGEMENT
     ═══════════════════════════════════════════════════════════════ */

  function fadeOutLayers(layers) {
    const now = ctx.currentTime;
    layers.forEach(layer => {
      try {
        // Smooth exponential fade-out
        layer.gain.gain.cancelScheduledValues(now);
        layer.gain.gain.setValueAtTime(layer.gain.gain.value, now);
        layer.gain.gain.linearRampToValueAtTime(0, now + FADE_OUT);
      } catch (_) {}
    });
    // Schedule cleanup after fade completes
    setTimeout(() => {
      layers.forEach(layer => {
        try { layer.source.stop(); } catch (_) {}
        try { if (layer.lfo) layer.lfo.stop(); } catch (_) {}
      });
    }, (FADE_OUT + 0.5) * 1000);
  }

  function stopAllOneShots() {
    stopThunderLoop();
    stopFoghornLoop();
    stopDistantHornLoop();
    stopBirdLoop();
    stopBellLoop();
    stopCreakLoop();
    stopMetalLoop();
    stopDripLoop();
    stopLapLoop();
  }

  /* ═══════════════════════════════════════════════════════════════
     PUBLIC API
     ═══════════════════════════════════════════════════════════════ */

  function init() {
    if (isInit && ctx && ctx.state !== "closed") {
      if (ctx.state === "suspended") ctx.resume();
      return;
    }
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      masterGain = ctx.createGain();
      masterGain.gain.value = _volume;
      masterGain.connect(ctx.destination);
      isInit = true;
    } catch (e) {
      console.warn("[NauticalAudio] Web Audio API not available:", e);
      isInit = false;
    }
  }

  function setWeather(condition) {
    if (!isInit || !ctx) return;
    if (ctx.state === "suspended") ctx.resume();
    if (condition === currentWeather) return;

    // Stop one-shot loops
    stopAllOneShots();

    // Crossfade: move current layers to fading, build new
    if (activeLayers.length) {
      fadingLayers = activeLayers;
      fadeOutLayers(fadingLayers);
    }

    // Build new layers (they fade in via FADE_IN)
    const builder = BUILDERS[condition] || BUILDERS.clear;
    activeLayers = builder();
    currentWeather = condition;
  }

  function setVolume(v) {
    _volume = Math.max(0, Math.min(1, v));
    if (masterGain && ctx) {
      // Smooth volume ramp
      const now = ctx.currentTime;
      masterGain.gain.cancelScheduledValues(now);
      masterGain.gain.setValueAtTime(masterGain.gain.value, now);
      masterGain.gain.linearRampToValueAtTime(_volume, now + 0.3);
    }
  }

  function stop() {
    stopAllOneShots();
    if (activeLayers.length) {
      fadeOutLayers(activeLayers);
      activeLayers = [];
    }
    currentWeather = null;
    if (ctx && ctx.state === "running") {
      setTimeout(() => { try { ctx.suspend(); } catch (_) {} }, (FADE_OUT + 1) * 1000);
    }
  }

  function isPlaying() {
    return isInit && ctx && ctx.state === "running" && currentWeather !== null;
  }

  return { init, setWeather, setVolume, stop, isPlaying };

})();
