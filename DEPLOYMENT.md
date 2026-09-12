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

## Optional OpenAI Settings

The app works without `OPENAI_API_KEY` by using keyword matching. To enable OpenAI-assisted extraction and reasons, add this secret to the API service environment:

```text
OPENAI_API_KEY=your_api_key
```

Do not commit API keys to the repo.
