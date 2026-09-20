# Devin Remediation Bot

Event-driven automation that remediates GitHub issues in [`namohkwan/superset`](https://github.com/namohkwan/superset) with the [Devin API](https://docs.devin.ai/api-reference/overview).

Two trigger modes share the exact same orchestration logic, so issues can be validated one at a time before any automation is switched on:

| Mode | Entry point | Use |
| --- | --- | --- |
| Manual / simulation | `python -m app.cli run --issue <n>` | Incremental validation of a single issue |
| Webhook | `POST /webhook` | GitHub `issues` event with the `devin-fix` label |

## Architecture

```
                 manual trigger                         webhook trigger
             python -m app.cli run                  POST /webhook (GitHub)
                        │                                     │
                        │                            HMAC X-Hub-Signature-256
                        ▼                                     ▼
                ┌───────────────────────────────────────────────────┐
  presentation  │            app/cli.py      app/api/*.py           │
                └───────────────────────────┬───────────────────────┘
                                            │ run_for_issue(number)
                ┌───────────────────────────▼───────────────────────┐
  core          │  app/core/orchestrator.py  +  app/core/prompts.py │
                └───────┬───────────────────────────────┬───────────┘
                        │                               │
        ┌───────────────▼──────────────┐   ┌────────────▼───────────┐
 adapters│ github_client  devin_client │   │ store/ (SQLite behind  │
        │ (HTTP only, no logic)        │   │ RemediationStore ABC)  │
        └───────────────┬──────────────┘   └────────────────────────┘
                        │
              GitHub REST   Devin API
```

Flow: a trigger passes an issue number to the orchestrator → the GitHub adapter fetches the issue → a prompt is rendered → the Devin adapter creates a session → the run is persisted → `app/services/poller.py` polls the session until `structured_output` reports `pr_url` and `result`, which the dashboard renders at `/status`.

### Dependency rules

Dependencies flow in one direction: **presentation → core → adapters / store**.

- `app/api/` and `app/cli.py` call only `app/core/orchestrator.py`. They never touch adapters or the store directly.
- `app/core/orchestrator.py` receives the GitHub adapter, the Devin adapter, and the store through constructor injection, so both trigger modes execute identical logic and tests can inject fakes.
- `app/adapters/` performs external HTTP calls only. A change to the Devin or GitHub API surface is absorbed here alone.
- `app/store/` persists data behind the `RemediationStore` interface; the SQLite backend can be swapped without changes elsewhere.
- `app/config.py` is the only module that reads environment variables.

### Folder structure

```
app/
├── config.py            # central env/secrets loading + fail-fast validation
├── main.py              # FastAPI entrypoint; registers routers only
├── cli.py               # manual/simulation trigger mode
├── api/
│   ├── webhook.py       # POST /webhook — issues events, HMAC verification
│   └── dashboard.py     # GET /status (HTML), GET /poll (JSON), GET /healthz
├── adapters/
│   ├── github_client.py # get_issue(number)
│   └── devin_client.py  # create_session(prompt), get_session(session_id)
├── core/
│   ├── prompts.py       # remediation prompt template
│   └── orchestrator.py  # shared orchestration, constructor injection
├── store/
│   ├── models.py        # RemediationRun, RunStatus
│   └── sqlite_store.py  # RemediationStore interface + SQLite implementation
├── services/
│   ├── poller.py        # background refresh of in-flight sessions
│   └── reporting.py     # serialization for dashboard/CLI output
└── templates/status.html
tests/                   # mirrors app/, adapters mocked
samples/labeled_event.json
```

## Security notice

- **Never commit real keys.** All secrets are injected through environment variables and read exclusively in `app/config.py`. No other module reads the environment or contains a credential.
- The root `.gitignore` excludes `.env`, `*.env`, `.env.local`, `*.db`, and `__pycache__/`. `.env.example` contains placeholders only.
- Secrets are never logged. `Settings.describe()` returns a redacted view (`***configured***`) and is what startup logging and the dashboard use.
- `/webhook` verifies the `X-Hub-Signature-256` HMAC with `GITHUB_WEBHOOK_SECRET` and rejects unsigned or forged deliveries with `401`.
- Do not display real keys on screen during demos or recordings. If a key is ever exposed, revoke and reissue it immediately: Devin API keys at https://app.devin.ai/settings/api-keys, GitHub tokens at https://github.com/settings/tokens, and regenerate the webhook secret in the repository webhook settings.

## How to obtain keys

| Variable | Where to get it |
| --- | --- |
| `DEVIN_API_KEY` | https://app.devin.ai/settings/api-keys → **Create new API key**. Copy it once; it is not shown again. |
| `GITHUB_TOKEN` | https://github.com/settings/personal-access-tokens → fine-grained token scoped to `namohkwan/superset` with **Issues: Read** (add **Pull requests: Read** to inspect resulting PRs). A classic token needs `repo`. |
| `GITHUB_WEBHOOK_SECRET` | Generate locally, e.g. `python -c "import secrets; print(secrets.token_hex(32))"`, and paste the same value into the GitHub webhook configuration. |
| `TARGET_REPO` | `namohkwan/superset` |

## Setup

```bash
git clone https://github.com/namohkwan/devin-remediation-bot.git
cd devin-remediation-bot
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # then fill in real values; .env is git-ignored
```

Missing or blank required variables abort startup with an explicit message:

```
Configuration error: Missing required environment variable(s): DEVIN_API_KEY, ...
```

## Manual mode — validating issues one at a time

```bash
# Remediate a single issue end to end
python -m app.cli run --issue 101

# Replay a stored GitHub event payload without exposing a public endpoint
python -m app.cli simulate --event samples/labeled_event.json

# Inspect all recorded runs as JSON
python -m app.cli status
```

`run` prints the persisted run, including the Devin `session_id` and session URL. Re-run `status` (or open `/status`) to watch the session progress to `succeeded`/`failed` with its `pr_url`.

## Webhook mode

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Register the webhook in `namohkwan/superset` → **Settings → Webhooks → Add webhook**:

- **Payload URL**: `https://<your-host>/webhook` (for local testing, expose port 8000 with a tunnel such as `cloudflared tunnel --url http://localhost:8000`)
- **Content type**: `application/json`
- **Secret**: the same value as `GITHUB_WEBHOOK_SECRET`
- **Events**: *Let me select individual events* → **Issues**

Adding the `devin-fix` label to an issue sends an `issues`/`labeled` event; the bot verifies the signature and starts a Devin session. Every other action, label, and event type is ignored.

## Docker

```bash
cp .env.example .env    # fill in real values
docker compose up --build
```

`docker-compose.yml` reads secrets from the local `.env` and stores the SQLite database in a named volume, so no credentials or database files enter the image or the repository.

## Dashboard

- `GET /status` — HTML dashboard listing every run with its issue, trigger, status, Devin session link, and pull request URL (auto-refreshes every 30 seconds).
- `GET /poll` — refreshes in-flight sessions and returns the same report as JSON.
- `GET /healthz` — liveness probe.

## Devin API contract

- `create_session(prompt)` → `POST https://api.devin.ai/v1/sessions` with `Authorization: Bearer $DEVIN_API_KEY` and body `{"prompt": ..., "idempotent": true}`.
- `get_session(session_id)` → `GET https://api.devin.ai/v1/session/{session_id}`, reading `status_enum` and `structured_output`.

The prompt instructs Devin to work in `namohkwan/superset`, implement the fix, run the relevant tests and lint checks, open a pull request titled `Fix #<issue_number>`, and write `{"pr_url": ..., "result": "pass|fail"}` into `structured_output`. A terminal session with `result == "pass"` marks the run succeeded; anything else marks it failed.

## Tests

```bash
pytest
```

The suite mirrors `app/` and mocks both external APIs: orchestration call order and persistence (`test_orchestrator.py`), adapter request shape and response parsing (`test_devin_client.py`, `test_github_client.py`), store CRUD (`test_store.py`), fail-fast configuration (`test_config.py`), webhook HMAC and label filtering plus dashboard rendering (`test_webhook.py`), and the CLI trigger mode (`test_cli.py`).
