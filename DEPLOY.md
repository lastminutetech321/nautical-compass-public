# Deployment Notes — Nautical Compass

## DigitalOcean App Platform

### Source
- Repo: lastminutetech321/nautical-compass-public
- Branch: main
- Auto-deploy: should be enabled

### Build
- Runtime: Python 3.11+
- Install: pip install -r requirements.txt
- Run: uvicorn main:app --host 0.0.0.0 --port 8080

### Critical: Clear Build Cache
If DigitalOcean says "previous build reused" or deploys stale code:
1. Go to App Platform → Settings → Components
2. Click "Force Rebuild and Deploy"
3. Check "Clear build cache" before confirming

This ensures fresh pip install with correct FastAPI/Starlette versions.

### Verification
After deploy, check:
- GET /health → should return current commit hash
- GET /command-deck → footer should show build stamp
- If commit hash is old → cache was not cleared

### Version Requirements
- fastapi>=0.136.0 (ships with Starlette 1.0+)
- TemplateResponse signature: TemplateResponse(request, name, context=ctx)
- Old signature TemplateResponse(name, ctx) will cause 500 errors
