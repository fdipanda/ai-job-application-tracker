# AI Job Application Tracker

AI Job Application Tracker is a full-stack application for managing job applications manually and automatically extracting application activity from Outlook email.

The project started as a personal workflow tool, but it became a stronger portfolio piece because it combines:
- a React/Next.js dashboard
- a FastAPI backend
- Microsoft OAuth + Graph API integration
- AI-assisted parsing with a deterministic regex fallback
- manual auditing of classifier accuracy and follow-up rule improvements

## What It Does

- Track job applications manually from a web dashboard
- Update application stages such as `Applied`, `Interview`, `Offer`, and `Rejected`
- Connect to Outlook and scan inbox messages for job-related activity
- Parse company, role, location, and status from emails
- Deduplicate email-derived records using a normalized `job_key`
- Support both incremental sync and historical backlog processing
- Preserve email provenance for auditing: subject, sender, and received timestamp

## Tech Stack

### Frontend
- Next.js 16
- React 19
- TypeScript
- Tailwind CSS 4

### Backend
- FastAPI
- SQLAlchemy 2
- Pydantic
- Uvicorn
- SQLite
- Requests
- MSAL for Microsoft authentication
- OpenAI API for AI-assisted parsing
- `python-dotenv` for local environment variables

### Testing
- `pytest`
- FastAPI `TestClient`
- focused backend tests around CRUD, ingestion, provenance, and backlog jobs

## Architecture

At a high level, the system is a client/server application with one main persistent store and two ingestion paths.

```text
Next.js frontend
  -> calls REST API
  -> shows dashboard, auth state, sync status, backlog progress

FastAPI backend
  -> CRUD for applications
  -> Outlook OAuth + Microsoft Graph email fetch
  -> incremental sync + backlog processing
  -> AI parsing + regex fallback
  -> application upsert and status progression rules

SQLite
  -> applications
  -> sync_state
  -> auth_state
```

### End-to-End Data Flow

1. The frontend loads the dashboard and requests the current application list.
2. The backend returns persisted application records from SQLite.
3. The user can manually create/update/delete records through REST endpoints.
4. If Outlook is connected, the frontend can trigger:
   - `Scan New Emails` for incremental sync
   - `Process Backlog` for historical scanning
5. The backend fetches messages from Microsoft Graph.
6. Messages are filtered for likely job-related content.
7. The parser tries AI extraction first, then falls back to regex parsing if needed.
8. The application service deduplicates or updates existing rows and only advances status forward.
9. Audit/debug files are written for inspection of ingestion behavior.

### Backend Structure

The backend lives in `backend/app/`.

- `main.py`: FastAPI app bootstrap, auth routes, sync routes, backlog job endpoints
- `routes.py`: CRUD endpoints for applications
- `database.py`: SQLAlchemy engine/session setup and SQLite schema checks
- `models.py`: ORM models for `Application`, `SyncState`, and `AuthState`
- `schemas.py`: request/response DTOs

Key services:
- `services/application_service.py`: normalization, dedupe, status progression, provenance merge
- `services/email_service.py`: Outlook message fetch + email ingestion pipeline
- `services/backlog_job_service.py`: in-memory tracking for long-running backlog jobs
- `services/job_detector.py`: job-email filtering
- `services/email_classifier.py`: status classification
- `services/ai_email_parser.py`: OpenAI-based parsing
- `services/email_parser.py`: regex fallback parsing
- `services/outlook_auth.py`: Microsoft OAuth flow with MSAL
- `services/sync_state_service.py`: incremental sync checkpoints

### Frontend Structure

The frontend lives in `frontend/` and uses the Next.js App Router.

- `src/app/page.tsx`: page-level orchestration for dashboard data, auth state, sync state, and backlog polling
- `src/components/AddApplicationForm.tsx`: manual application creation
- `src/components/ApplicationCard.tsx`: application display, status update, and deletion
- `src/lib/api.ts`: frontend API wrapper
- `src/lib/types.ts`: shared frontend types
- `src/lib/status.ts`: status ordering, filters, and display helpers

## Testing Narrative

This project includes backend tests to validate both standard CRUD behavior and the more interesting email-ingestion logic.

The current test suite covers:
- application CRUD behavior
- not-found/validation cases
- job email classification
- AI parser fallback behavior
- backlog job lifecycle and progress reporting
- provenance persistence for email-derived rows
- sync checkpoint behavior for incremental email scans

One especially important part of the project was manual classifier auditing:
- audited `Rejected`, `Assessment`, and `Recruiter Contact` labels
- found `Rejected` precision was strong
- found `Recruiter Contact` had many false positives
- used those findings to guide tighter classification rules and future test cases

To run the tests:

```bash
./venv/bin/pytest -q backend/tests tests
```

## Local Setup

### Prerequisites

- Node.js 20+
- npm
- Python 3.9+
- a Microsoft app registration for Outlook access if you want email sync
- an OpenAI API key if you want AI-assisted parsing

### Backend setup

Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

Create `backend/app/.env`:

```env
OUTLOOK_CLIENT_ID=your_outlook_client_id
OUTLOOK_TENANT_ID=your_outlook_tenant_id
OUTLOOK_CLIENT_SECRET=your_outlook_client_secret
OUTLOOK_REDIRECT_URI=http://localhost:8000/auth/callback
OPENAI_API_KEY=your_openai_api_key
FRONTEND_URL=http://localhost:3000
```

### Frontend setup

```bash
cd frontend
npm install
cd ..
```

## Running the App

### Option 1: one command launcher

This repo includes a small launcher script that starts both services from one terminal:

```bash
./scripts/start-dev.sh
```

It starts:
- FastAPI on `http://localhost:8000`
- Next.js on `http://localhost:3000`

Press `Ctrl+C` once to stop both.

### Option 2: run each service manually

Backend:

```bash
./venv/bin/uvicorn app.main:app --reload --app-dir backend
```

Frontend:

```bash
cd frontend
npm run dev
```

## Core API Endpoints

### CRUD
- `GET /applications`
- `POST /applications`
- `GET /applications/{id}`
- `PUT /applications/{id}`
- `DELETE /applications/{id}`

### Auth and email sync
- `GET /auth/login`
- `GET /auth/callback`
- `GET /auth/status`
- `POST /emails/sync-new`
- `POST /emails/process-backlog`
- `GET /emails/process-backlog/{job_id}`

## Why This Is More Than CRUD

What makes this project interesting from an engineering perspective is the email-ingestion pipeline:

- not every inbox message should become an application
- parsed rows need deduplication
- status should not move backward
- AI extraction can fail and needs a fallback
- email-derived data should remain auditable
- backlog processing needs progress tracking and safe concurrency

Those concerns drove the service-layer design and the test coverage.

## Current Limitations

This is a strong local/portfolio app, but it is not fully production-ready yet.

- SQLite is convenient for local development, but Postgres would be better for deployment
- Outlook tokens are stored for convenience, not in an encrypted secret store
- backlog jobs are tracked in memory, so job state is not distributed/persistent across server instances
- email parsing still relies on heuristics and can produce false positives/false negatives
- search/filter/sort happen client-side after loading the full application list
- email sync is serialized with an in-process lock
- the project is optimized for local use and demoability rather than cloud-scale deployment

## Repository Structure

```text
backend/
  app/
    main.py
    routes.py
    database.py
    models.py
    schemas.py
    services/
  requirements.txt

frontend/
  src/
    app/
    components/
    lib/
  package.json

tests/
backend/tests/
scripts/
  start-dev.sh
```

## Next Improvements

If this were pushed further toward production, the next steps would be:
- move SQLite to Postgres
- add stronger token/security handling
- add frontend/E2E tests
- deploy frontend/backend separately
- improve observability and structured logging
- continue tightening classifier accuracy based on audit results
.
├── backend
│   ├── app
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── services
│   │       ├── auth_state_service.py
│   │       ├── ai_email_parser.py
│   │       ├── application_service.py
│   │       ├── email_classifier.py
│   │       ├── email_parser.py
│   │       ├── email_service.py
│   │       ├── job_detector.py
│   │       ├── outlook_auth.py
│   │       └── sync_state_service.py
│   ├── applications.db
│   ├── email_debug.json
│   └── requirements.txt
├── tests
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_application_service.py
│   ├── test_classification.py
│   ├── test_email_ingestion.py
│   └── test_parser.py
└── frontend
    ├── src
    │   ├── app
    │   ├── components
    │   └── lib
    └── package.json
```

## Future Improvements

- Move secrets out of tracked files and rotate any exposed credentials.
- Encrypt or externalize persisted auth state instead of storing raw access tokens in SQLite.
- Persist auth state more securely.
- Make the frontend API base URL configurable via environment variables.
- Add pagination, server-side filtering, and richer application notes/history.
