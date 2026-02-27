# --------------------
# Footer pages (Legal + Support)
# --------------------
@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/privacy-notice", response_class=HTMLResponse)
def privacy_notice_page(request: Request):
    return templates.TemplateResponse("privacy_notice.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/consumer-privacy-rights", response_class=HTMLResponse)
def consumer_privacy_rights_page(request: Request):
    return templates.TemplateResponse("consumer_privacy_rights.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/cookie-settings", response_class=HTMLResponse)
def cookie_settings_page(request: Request):
    return templates.TemplateResponse("cookie_settings.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/accessibility", response_class=HTMLResponse)
def accessibility_page(request: Request):
    return templates.TemplateResponse("accessibility.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request):
    return templates.TemplateResponse("support.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/faq", response_class=HTMLResponse)
def faq_page(request: Request):
    return templates.TemplateResponse("faq.html", {"request": request, "year": datetime.utcnow().year})

@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request, "year": datetime.utcnow().year})

# Download placeholders (until you publish real app store links)
@app.get("/download/ios")
def download_ios():
    return RedirectResponse(url="/", status_code=303)

@app.get("/download/android")
def download_android():
    return RedirectResponse(url="/", status_code=303)
