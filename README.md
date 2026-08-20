# API Monitor

A Django-based API monitoring dashboard that periodically checks configured APIs, records health and latency logs, detects confirmed downtime, creates incidents, and sends recovery/down/slow-response alerts.

## Stack

- Python / Django / Django REST Framework
- JWT authentication
- Celery + Redis for scheduled monitoring
- SQLite for local development
- PostgreSQL for Docker/production
- HTML/CSS/JavaScript dashboard
- Email alerts
- Twilio SMS support

## Main features

- User registration and login
- JWT access/refresh tokens
- Email/mobile login support
- Per-user monitor ownership
- API monitoring with configurable HTTP method
- Expected HTTP status validation
- Bearer and `X-API-Key` authentication
- Response-time threshold and slow-response alerts
- Three consecutive failed checks required before a monitor becomes DOWN
- Incident creation and automatic recovery
- Uptime, error rate, average latency and P95 latency
- Analytics for 24h, 7d and 30d
- Paginated logs
- Incident history
- User notification preferences
- User-generated API keys
- Docker + PostgreSQL + Redis + Celery worker/beat

## Local setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in the values you need.

4. Run migrations:

```bash
python manage.py migrate
```

5. Create an admin:

```bash
python manage.py createsuperuser
```

6. Start Django:

```bash
python manage.py runserver
```

7. Start Redis and Celery in separate terminals:

```bash
celery -A backend worker --loglevel=info
```

```bash
celery -A backend beat --loglevel=info
```

Open:

`http://127.0.0.1:8000/`

## Docker

Copy `.env.production.example` to `.env.production`, set real secrets/passwords, then run:

```bash
docker compose up --build
```

The Django application is available on port `8000`.

## Security notes

- Never commit `.env` or `.env.production`.
- Use a strong production `SECRET_KEY`.
- Use explicit CORS and CSRF origin allow-lists.
- Run production behind HTTPS.
- API monitor API keys are never returned by the serializer.
- User-generated application API keys are stored as hashes.
- Rotate any credentials that were previously exposed outside the local machine.

## Monitoring behavior

A failed request is not immediately marked DOWN. The monitor must reach three consecutive failed checks. A new incident is created only when the third failure confirms downtime. A later successful check resolves the active incident and sends a recovery notification.

The monitor's configured `expected_status` is used as the success condition.
