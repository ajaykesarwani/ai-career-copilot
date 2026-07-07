import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from routers import profile, jobs, applications, coach, ops

# Load .env from the project root (parent of backend/) regardless of
# which directory uvicorn is launched from.
_here = Path(__file__).resolve().parent          # .../backend/
_dotenv = _here.parent / ".env"                  # .../project-root/.env
if _dotenv.exists():
    load_dotenv(_dotenv)
else:
    load_dotenv()   # fallback: standard search (handles Docker / Cloud Run)

@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    log = logging.getLogger("startup")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    gemini  = "✅" if os.getenv("GEMINI_API_KEY") else "❌ MISSING"
    adzuna  = "✅" if (os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY")) else "⚠️  not set (AI-estimated jobs will be used)"
    github  = "✅" if os.getenv("GITHUB_TOKEN") else "⚠️  not set (60 req/hr, no pinned repos)"
    linkedin = "✅" if (os.getenv("LINKEDIN_EMAIL") and os.getenv("LINKEDIN_PASSWORD")) else "⚠️  not set (paste-text fallback only)"

    log.info("✦ AI Career Copilot starting")
    log.info("  .env loaded from: %s", str(_dotenv) if _dotenv.exists() else "standard search")
    log.info("  GEMINI_API_KEY   : %s", gemini)
    log.info("  ADZUNA keys      : %s", adzuna)
    log.info("  GITHUB_TOKEN     : %s", github)
    log.info("  LINKEDIN creds   : %s", linkedin)
    yield
    log.info("✦ Shutting down")

# app must be created BEFORE using @app.get(...)
app = FastAPI(
    title="AI Career Copilot API",
    description="Multi-agent career assistant powered by Google Gemini (with automatic Groq fallback)",
    version="1.0.0",
    lifespan=lifespan,
)

# NOW you can define routes
@app.get("/")
async def root():
    return {"message": "AI Career Copilot backend is running"}

# CORS
allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(profile.router,      prefix="/api/profile",      tags=["Profile"])
app.include_router(jobs.router,         prefix="/api/jobs",         tags=["Jobs"])
app.include_router(applications.router, prefix="/api/applications", tags=["Applications"])
app.include_router(coach.router,        prefix="/api/coach",        tags=["Coach"])
app.include_router(ops.router,          prefix="/api/ops",          tags=["Ops & Evaluation"])

@app.get("/health")
async def health():
    return {"status": "ok", "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash")}

# Static + favicon (optional)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(Path("static") / "favicon.ico")

# Built frontend
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="spa")