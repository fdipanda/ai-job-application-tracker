# AI Job Application Tracker

AI Job Application Tracker is a small full-stack app for managing job applications manually and automatically extracting application activity from Outlook email.

The project has two halves:

- A FastAPI backend that stores applications in SQLite and processes Outlook email.
- A Next.js frontend that lets you view, add, update, filter, and delete applications.

## Architecture

The system is organized as a simple client/server app with one persistent data store.

```text
Next.js frontend
  -> calls REST API

FastAPI backend
  -> CRUD for applications
  -> Outlook OAuth + Microsoft Graph email fetch
  -> incremental email sync + backlog sync
  -> AI + regex parsing of job emails
  -> SQLAlchemy persistence

SQLite
  -> applications table
  -> sync_state table
  -> auth_state table
```

### Backend flow

The backend lives in `backend/app/`.

- `main.py` boots FastAPI, enables CORS for `http://localhost:3000`, creates database tables, and exposes API and auth endpoints.
- `routes.py` contains the core CRUD endpoints for job applications.
- `database.py` configures SQLAlchemy and the SQLite connection.
- `models.py` defines the `Application` database model.
- `schemas.py` defines the Pydantic request and response models.

The backend also includes an email-ingestion pipeline:

- `services/outlook_auth.py` handles Microsoft OAuth using MSAL.
- `services/auth_state_service.py` persists the latest Outlook access token in SQLite.
- `services/email_service.py` fetches messages from Microsoft Graph and processes them.
- `services/job_detector.py` filters likely job-related emails using keywords and blocked senders.
- `services/ai_email_parser.py` uses the OpenAI API to extract company, role, location, and status from email content.
- `services/email_parser.py` provides a regex-based fallback parser.
- `services/email_classifier.py` classifies email stage such as `Applied`, `Interview`, `Offer`, or `Rejected`.
- `services/application_service.py` deduplicates and upserts records using a normalized `job_key`, and only advances status when the new status is further along in the pipeline.
- `services/sync_state_service.py` stores checkpoint state for incremental email scans.

### Frontend flow

The frontend lives in `frontend/` and uses the Next.js App Router.

- `src/app/page.tsx` is the main dashboard page.
- `src/components/AddApplicationForm.tsx` handles manual application creation.
- `src/components/ApplicationCard.tsx` renders individual applications and supports status changes and deletion.
- `src/lib/api.ts` wraps calls to the backend API.
- `src/lib/types.ts` defines the frontend `Application` type.

The frontend loads all applications from the backend, then applies search, filter, sort, and summary counts client-side.

## Technologies Used

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
- OpenAI API for AI-assisted email parsing
- `python-dotenv` for local environment variables

## Data Model

The main persisted entity is an application record with fields such as:

- `company`
- `role`
- `status`
- `job_key`
- `location`
- `application_link`
- `notes`
- `date_applied`
- `last_updated`

The current app uses a single SQLite database file:

- `backend/applications.db`

It currently stores three tables:

- `applications` for tracked job applications
- `sync_state` for incremental email scan checkpoints
- `auth_state` for persisted Outlook auth state

## API Overview

Core CRUD endpoints:

- `GET /applications`
- `POST /applications`
- `GET /applications/{id}`
- `PUT /applications/{id}`
- `DELETE /applications/{id}`

Email and auth endpoints:

- `GET /auth/login`
- `GET /auth/callback`
- `GET /emails`
- `GET /process-backlog`
- `POST /emails/sync-new`

## Setup

### Prerequisites

- Node.js 20+ recommended
- npm
- Python 3.9+
- A Microsoft app registration with Outlook mail access
- An OpenAI API key if you want AI-assisted email parsing

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd ai-job-application-tracker
```

### 2. Set up the backend

Create and activate a virtual environment:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `backend/app/.env` with placeholder values like:

```env
OUTLOOK_CLIENT_ID=your_outlook_client_id
OUTLOOK_TENANT_ID=your_outlook_tenant_id
OUTLOOK_CLIENT_SECRET=your_outlook_client_secret
OUTLOOK_REDIRECT_URI=http://localhost:8000/auth/callback
OPENAI_API_KEY=your_openai_api_key
```

Important:

- Do not commit real secrets to source control.
- If you only want manual application tracking, the email-related credentials are not needed until you use the Outlook endpoints.

Start the backend server:

```bash
uvicorn app.main:app --reload
```

The API will run at `http://localhost:8000`.

### 3. Set up the frontend

Open a new terminal:

```bash
cd frontend
npm install
```

Start the frontend:

```bash
npm run dev
```

The app will run at `http://localhost:3000`.

## Using the App

### Manual tracking

1. Start the backend.
2. Start the frontend.
3. Open `http://localhost:3000`.
4. Add applications with the form.
5. Update statuses or delete entries from the dashboard.

### Outlook email ingestion

1. Configure the backend `.env` with Outlook and OpenAI credentials.
2. Start the backend.
3. Open `http://localhost:8000/auth/login` to sign in with Microsoft.
4. After authentication completes, call:

```text
GET /emails
```

to fetch recent job-related messages, or:

```text
GET /process-backlog
```

to scan more pages of historical mail and upsert detected applications.

You can also call:

```text
POST /emails/sync-new
```

to incrementally scan only messages newer than the last successful sync checkpoint.
The response includes:

- `scanned_count`
- `detected_count`
- `added_count`
- `updated_count`
- `skipped_count`
- `write_failures`
- `checkpoint_at`
- `last_run_status`

## Notes and Limitations

- The backend persists the Outlook access token in SQLite for convenience. This keeps auth across restarts, but it is not an encrypted credential store.
- The frontend API base URL is hardcoded to `http://localhost:8000`.
- Search, filter, and sorting happen in the client after fetching the full application list.
- Email parsing uses heuristics plus AI and may still produce misses or false positives.
- Backlog sync writes a newline-delimited JSON debug log to `backend/email_debug.json` for each run.
- Email sync endpoints are guarded by an in-process lock, so only one sync can run at a time per backend process.
- There are checked-in environment and local artifact files in the repo; those should ideally be cleaned up and ignored.

## Repository Structure

```text
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
