# Deployment Guide

## Get your Gemini API key first
Visit **https://aistudio.google.com/app/apikey** → Create API key → copy it.
The free tier is usable for a personal project like this, but Google adjusts
the exact RPM/RPD numbers by model and tier fairly often — check your live
limits at https://aistudio.google.com/rate-limit rather than trusting a
number written down here. If you're testing heavily and start seeing 429s,
either wait a day or set `GROQ_API_KEY` (this app falls back to Groq
automatically on a 429).

---

## Option A — Google Cloud Run (recommended for production)

### Prerequisites
```bash
# Install gcloud CLI
brew install google-cloud-sdk   # macOS
# or: https://cloud.google.com/sdk/docs/install

gcloud auth login
gcloud auth configure-docker
gcloud config set project YOUR_PROJECT_ID
```

### Deploy
```bash
export GCP_PROJECT_ID=your-project-id
export GEMINI_API_KEY=AIza-your-key-here
chmod +x deployment/deploy.sh
./deployment/deploy.sh
```

This script:
1. Builds the React frontend (`npm run build`)
2. Builds a Docker image and pushes to Google Container Registry
3. Deploys to Cloud Run (auto-scales 0→10 instances)
4. Outputs the live URL

### Cost estimate
Cloud Run's free tier covers roughly 2 million requests/month, which is far
more than a personal job-search tool needs.
Gemini's free tier comfortably covers personal usage of this app, though
Google changes the exact per-model RPM/RPD numbers periodically — see
https://aistudio.google.com/rate-limit for your current limits.
Typical personal job-search usage: **$0/month**, with Groq configured as a
free fallback if you ever do hit a Gemini quota limit.

---

## Option B — Render.com (easiest for demos)

1. Push your code to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your repo. This project keeps `render.yaml` inside `deployment/`
   rather than the repo root, so when prompted, set the **Blueprint Path**
   field to `deployment/render.yaml` (Render has supported custom Blueprint
   paths since early 2026 — see [Blueprint docs](https://render.com/docs/infrastructure-as-code))
4. Set the `sync: false` secrets (`GEMINI_API_KEY`, optionally `GROQ_API_KEY`,
   `GITHUB_TOKEN`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`) in each service's
   Environment tab
5. Click Deploy — live in ~3 minutes, free tier available

---

## Option C — Local with ngrok (instant sharing)

```bash
docker-compose up --build
# In another terminal:
brew install ngrok && ngrok http 8000
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Get from [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `GEMINI_MODEL` | Optional | Default `gemini-2.5-flash`. Google retires model IDs periodically — see [deprecations](https://ai.google.dev/gemini-api/docs/deprecations) |
| `GROQ_API_KEY` | Optional | Enables automatic fallback when Gemini returns a 429. Get from [console.groq.com/keys](https://console.groq.com/keys) |
| `GROQ_MODEL` | Optional | Default `openai/gpt-oss-120b`. Groq also retires model IDs periodically — see [console.groq.com/docs/models](https://console.groq.com/docs/models) |
| `GITHUB_TOKEN` | Optional | GitHub PAT → 5,000 req/hr vs 60 unauthenticated, plus pinned-repo access |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | Optional | Real, live job listings from [developer.adzuna.com](https://developer.adzuna.com/) instead of AI-estimated ones |
| `LINKEDIN_EMAIL` + `LINKEDIN_PASSWORD` | Optional | Full LinkedIn profile scrape via linkedin-api instead of paste-text fallback |
| `MAX_UPLOAD_MB` | Optional | Resume upload size limit |
| `ALLOWED_ORIGINS` | Optional | Comma-separated CORS origins (default: localhost) |
| `PORT` | Auto-set by host | Cloud Run / Render inject this; defaults to 8000 for local/docker-compose |
| `GCP_PROJECT_ID` | Cloud Run only | Your GCP project ID |
| `GCP_REGION` | Cloud Run only | Default: `europe-west1` |
| `VITE_API_URL` | Frontend build | Backend API base URL — build-time only (Vite bakes it in) |
