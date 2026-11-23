# Deployment

This project has two deployable services:

- `apps/api`: FastAPI backend for concept extraction and doctor recommendations.
- `apps/web`: static-exported Next.js frontend that calls the backend API.

The recommendation UI currently uses the processed CSV files under `data/processed`.
PostgreSQL is not required for the deployed recommendation UI unless you also want to use the database-backed doctor endpoints.

## Recommended Option: Render

Render is the simplest option for this repository because it can deploy both services from the same GitHub repo using `render.yaml`.

1. Push the latest code to GitHub.
2. In Render, create a new Blueprint from the GitHub repository.
3. Render will read `render.yaml` and create:
   - `doctor-matching-agent-api`
   - `doctor-matching-agent-web`
4. After deployment, open the web service URL:

```text
https://doctor-matching-agent-web.onrender.com
```

If Render gives either service a different URL, update these environment variables in Render:

- API service: `FRONTEND_ORIGINS`
- Web service: `NEXT_PUBLIC_API_BASE_URL`

## Updating the Existing Render Deployment

The existing services use the same GitHub repository:

- Website: https://doctor-matching-agent-web.onrender.com
- API: https://doctor-matching-agent-api.onrender.com
- Source: https://github.com/wenxxi/doctor-matching-agent

Push changes to `main`. If both services have **Auto-Deploy → On Commit** enabled and track `main`, Render rebuilds and deploys them automatically. Check each service's **Deploys** page for the deployed commit and result.

If automatic deployment is disabled, open each service in the [Render Dashboard](https://dashboard.render.com/) and select **Manual Deploy → Deploy latest commit**. Update both the API and website for the appointment integration.

After deployment, confirm:

1. The API `/health` returns `{"status":"ok"}`.
2. The API `/docs` includes `GET /api/doctors/{doctor_id}/appointments`.
3. A recommendation card on the website shows the appointment lookup button, and selecting a returned slot opens the official CGMH patient information page. Appointment availability depends on the hospital's live site; a temporary lookup failure should still show the official registration link.

## OpenAI-Generated Reasons

The app works without `OPENAI_API_KEY` by using keyword matching. In that mode, doctor cards show deterministic reasons such as `符合概念`.

To enable generated doctor descriptions, add this secret to the API service environment:

```text
OPENAI_API_KEY=your_api_key
```

Do not commit API keys to the repo.

After adding or changing this value in Render, redeploy the API service.
