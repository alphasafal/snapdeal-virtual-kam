# Putting it on a public link

Locally everything runs on your laptop. A public link needs three hosted pieces:
a database, the agent, and the web app. About 20 minutes the first time.

Before you start, know what a public link means: anyone who has it can start calls, and
each call spends Sarvam credit. `MAX_CALLS_PER_HOUR` (default 60) caps this; lower it.

## 1. Database (Neon, free)

1. Create a project at neon.tech and copy the connection string.
2. Load the mock sellers into it:
   ```bash
   cd agent && source .venv/bin/activate
   DATABASE_URL="<neon connection string>" python -m brain.seed
   ```

## 2. Agent (LiveKit Cloud)

```bash
brew install livekit-cli
cd agent
cp .env.production.example .env.production     # fill in SARVAM_API_KEY and the Neon DATABASE_URL
lk cloud auth                                  # opens the browser; pick the Snapdeal_KAM project
lk agent create --secrets-file=.env.production # builds from the Dockerfile and deploys
lk agent status
lk agent logs
```

LiveKit Cloud supplies its own URL, key and secret to the agent, so they are not in the secrets file.
To ship a change later, see "Deploying new versions" in LiveKit's deployment docs.

## 3. Web app (Vercel)

1. Push this folder to a GitHub repository (the `.gitignore` already keeps keys out).
2. In Vercel, import the repository and set the root directory to `web`.
3. Add environment variables: `DATABASE_URL` (the same Neon string), `LIVEKIT_URL`,
   `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and optionally `MAX_CALLS_PER_HOUR`.
4. Deploy and open the link.

## Laptop and cloud at the same time

Both agents connect to the same LiveKit project, but each one only answers calls that exist
in its own database. Calls from the public link (Neon) go to the cloud agent; calls from
`localhost:3000` (local Postgres) go to the laptop agent.

## Not verified

These steps follow LiveKit's and Vercel's documentation; they have not been run end to end
for this project. Check `lk agent logs` after the first deploy.
