<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{% block title %}Nautical Compass{% endblock %}</title>

  <link rel="icon" href="/static/favicon.ico" />
  <link rel="stylesheet" href="/static/styles.css?v=7" />
  {% block head %}{% endblock %}
</head>
<body>

  <header class="nav glass moist">
    <div class="nav-inner">
      <a class="brand" href="/">
        <span class="brand-badge">NC</span>
        <span class="brand-text">Nautical Compass</span>
      </a>

      <nav class="nav-links">
        <a href="/hall">Hall</a>
        <a href="/services">Services</a>
        <a href="/dashboards">Dashboards</a>
        <a href="/lead">Lead Intake</a>
        <a href="/partner">Partners</a>
        <a href="/sponsor">Sponsors</a>
        <a class="tab-primary" href="/checkout">Get Access</a>
      </nav>
    </div>
  </header>

  <!-- Sound toggle bar (OFF by default) -->
  <div style="max-width:1100px;margin:10px auto 0;padding:0 20px;">
    <div class="glass" style="border-radius:14px;padding:10px 12px;display:flex;align-items:center;gap:10px;justify-content:space-between;">
      <div class="small muted" id="soundStatus">Sound: Off</div>
      <button class="btn" id="soundToggle" type="button">Enable Ocean Ambience</button>
    </div>
  </div>

  <main>
    {% block content %}{% endblock %}
  </main>

  <footer class="footer">
    <div class="footer-row">
      <div>© 2026 Nautical Compass • One system • Many lanes</div>
      <div>
        <a href="/services">Solutions</a> •
        <a href="/lead">General Inquiry</a> •
        <a href="/partner">Partner</a> •
        <a href="/privacy">Privacy</a> •
        <a href="/terms">Terms</a>
      </div>
    </div>
  </footer>

  <!-- Optional ocean audio (upload static/ocean.mp3 if you want it) -->
  <audio id="oceanAudio" preload="none" loop>
    <source src="/static/ocean.mp3" type="audio/mpeg">
  </audio>

  <script>
    (function(){
      const audio = document.getElementById("oceanAudio");
      const btn = document.getElementById("soundToggle");
      const status = document.getElementById("soundStatus");
      let on = false;

      async function setOn(next){
        on = next;
        if(on){
          try{
            await audio.play(); // iOS requires user gesture (button click)
            status.textContent = "Sound: On";
            btn.textContent = "Turn Sound Off";
          }catch(e){
            status.textContent = "Sound: Off (upload /static/ocean.mp3)";
            btn.textContent = "Enable Ocean Ambience";
            on = false;
          }
        }else{
          audio.pause();
          audio.currentTime = 0;
          status.textContent = "Sound: Off";
          btn.textContent = "Enable Ocean Ambience";
        }
      }

      btn.addEventListener("click", function(){
        setOn(!on);
      });
    })();
  </script>

  {% block scripts %}{% endblock %}
</body>
</html>
