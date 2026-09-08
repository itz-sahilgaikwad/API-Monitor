API Monitor

A full-stack API monitoring platform built with Django and Django
REST Framework for continuously monitoring API health, response times,
failures, downtime incidents, recovery events, and performance
analytics.

The system periodically checks configured APIs in the background and
provides a dashboard for monitoring their current and historical health.

Overview

API Monitor allows users to configure and monitor multiple APIs from a
centralized dashboard.

Each monitoring check records information such as:

API availability

HTTP status code

Response time

Request time

Errors

Slow responses

Consecutive failures

Downtime incidents

Recovery events

Uptime statistics

Performance analytics

The monitoring system runs automatically in the background using
Celery, Celery Beat, and Redis.

Key Features

API Monitoring

Monitor multiple APIs

Configurable HTTP methods

Expected HTTP status validation

Response-time threshold monitoring

Automatic periodic health checks

API availability tracking

Slow-response detection

Manual Check Now functionality

Pause and resume monitoring

Downtime Detection

API Monitor uses consecutive failure detection instead of immediately
marking an API as unavailable after a single failed request.

An API must experience three consecutive failed checks before
downtime is confirmed.

This helps reduce false incidents caused by temporary network problems.

Incident Management

When downtime is confirmed:

The failed check is recorded.

An incident is created.

The API is marked as DOWN.

Monitoring continues.

A successful check triggers recovery.

The incident is automatically resolved.

Recovery information is recorded.

The incident dashboard provides:

Total incidents

Open incidents

Resolved incidents

Affected APIs

Incident history

Start time

Resolution time

Incident duration

Incident status

Analytics

API Monitor provides performance analytics including:

Uptime percentage

Error rate

Average response time

P95 latency

Total checks

Successful checks

Failed checks

Response-time trends

Analytics can be viewed over:

Last 24 hours

Last 7 days

Last 30 days

Monitoring Logs

Every monitoring check is stored as a log containing information such
as:

Status

HTTP status code

Response time

Error information

Check timestamp

API health result

The logs interface also provides filtering and search functionality and
supports exporting monitoring data.

Authentication

The application includes user authentication with:

User registration

User login

Email/mobile login support

JWT authentication

Access tokens

Refresh tokens

Per-user monitor ownership

User-generated API keys

API keys are stored using hashes rather than storing the original raw
key.

Monitored API Authentication

The APIs being monitored can use:

Bearer authentication

API key authentication

This allows API Monitor to monitor both public and authenticated
endpoints.

Notifications

The monitoring system supports:

Email notifications

Twilio SMS support

Downtime alerts

Recovery alerts

Slow-response alerts

User notification preferences

Background Processing

Monitoring tasks are handled asynchronously using:

Celery --- executes background monitoring tasks

Celery Beat --- schedules periodic monitoring checks

Redis --- message broker and task backend

This allows API health checks to run independently from normal web
requests.

Docker Support

The project includes Docker configuration for running:

Django

PostgreSQL

Redis

Celery Worker

Celery Beat

Dashboard

The dashboard provides a real-time overview of monitored APIs.

It displays:

Total APIs

Healthy APIs

Down APIs

Slow APIs

Availability percentage

Response time

Last checked time

Last error

Recent health information

Response-time trends

Analytics

The analytics dashboard provides detailed performance information for
individual monitored APIs.

It includes:

Uptime

Average response time

P95 latency

Total checks

Successful checks

Failed checks

Response-time charts

Availability information

Configurable time periods

Logs

The logs dashboard provides access to historical monitoring checks.

Users can:

View monitoring history

Filter by API

Filter by time period

Filter by status

Search logs

Inspect response times

View HTTP status codes

View monitoring errors

Export monitoring data

Incidents

The incident dashboard tracks confirmed API downtime.

It provides:

Active incidents

Incident history

Incident status

Affected API

Start time

Resolution time

Duration

Recovery information

Technology Stack

Technology              Purpose

Python                  Backend programming
Django                  Web framework
Django REST Framework   REST API
Simple JWT              JWT authentication
Celery                  Background task processing
Celery Beat             Periodic task scheduling
Redis                   Celery broker and task backend
SQLite                  Local development database
PostgreSQL              Production database
HTML                    Frontend structure
CSS                     Frontend styling
JavaScript              Frontend interactions
Docker                  Containerization
Gunicorn                Production WSGI server
Twilio                  SMS notification support

Architecture

                         ┌─────────────────────┐
                         │      Frontend       │
                         │    HTML / CSS / JS  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │       Django        │
                         │   REST Framework    │
                         └──────────┬──────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
         ┌────────────┐      ┌────────────┐      ┌────────────┐
         │ PostgreSQL │      │   Redis    │      │ Monitoring │
         │  Database  │      │   Broker   │      │   System   │
         └────────────┘      └─────┬──────┘      └────────────┘
                                   │
                            ┌──────┴──────┐
                            │             │
                            ▼             ▼
                     ┌────────────┐ ┌────────────┐
                     │   Celery   │ │   Celery   │
                     │   Worker   │ │    Beat    │
                     └─────┬──────┘ └─────┬──────┘
                           │               │
                           └───────┬───────┘
                                   ▼
                          ┌────────────────┐
                          │ Monitored APIs │
                          └────────────────┘

Monitoring Flow

User configures an API
          │
          ▼
Monitor configuration is stored
          │
          ▼
Celery Beat schedules health checks
          │
          ▼
Celery Worker executes the check
          │
          ▼
HTTP request is sent to monitored API
          │
          ▼
Response is evaluated
          │
     ┌────┴───────────────┐
     │                    │
     ▼                    ▼
Successful             Failed / Slow
     │                    │
     ▼                    ▼
Record health          Record failure
     │                    │
     │              Consecutive failures
     │                    │
     │              ┌─────┴─────┐
     │              │           │
     │             < 3          3+
     │              │           │
     │              ▼           ▼
     │         Continue      Confirm DOWN
     │                       Create incident
     │                            │
     └──────────────┬─────────────┘
                    ▼
              Store monitoring log
                    │
                    ▼
             Update dashboard
                    │
                    ▼
          Successful recovery check
                    │
                    ▼
            Resolve open incident
                    │
                    ▼
             Record recovery

Monitoring logic

A user configures an API to monitor.

The monitor configuration is stored for that user.

Celery Beat schedules the monitoring task.

A Celery worker performs the HTTP health check.

The response status, response time, and errors are evaluated.

The monitoring result is stored as a log.

Consecutive failures are tracked.

After three consecutive failures, downtime is confirmed.

A downtime incident is created and the API is marked DOWN.

Monitoring continues while the incident is active.

A successful check triggers recovery.

The incident is resolved and recovery information is recorded.

Dashboard and analytics data reflect the latest monitoring results.

Project Structure

API-Monitor/
│
├── backend/
│   ├── settings.py
│   ├── urls.py
│   ├── celery.py
│   ├── asgi.py
│   └── wsgi.py
│
├── frontend/
│   ├── dashboard.html
│   ├── analytics.html
│   ├── incidents.html
│   ├── logs.html
│   ├── settings.html
│   ├── user_login.html
│   ├── register.html
│   └── ...
│
├── monitoring/
│   ├── models.py
│   ├── serializers.py
│   ├── tasks.py
│   ├── views.py
│   ├── urls.py
│   ├── utils.py
│   ├── sms_utils.py
│   └── migrations/
│
├── users/
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── permissions.py
│   ├── auth_backends.py
│   ├── urls.py
│   └── migrations/
│
├── logs/
│   ├── models.py
│   ├── admin.py
│   └── migrations/
│
├── templates/
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── manage.py
├── .env.example
├── .env.production.example
├── .gitignore
└── README.md

Local Development

1. Clone the repository

git clone https://github.com/itz-sahilgaikwad/API-Monitor.git
cd API-Monitor

2. Create a virtual environment

Windows

python -m venv venv
.\venv\Scripts\activate

macOS / Linux

python3 -m venv venv
source venv/bin/activate

3. Install dependencies

pip install -r requirements.txt

4. Configure environment variables

Copy the example environment file and configure the required values.

For local development, use:

.env.example

For Docker/production-style configuration, use:

.env.production.example

Never commit real passwords, API keys, tokens, or other secrets to Git.

5. Run database migrations

python manage.py migrate

6. Start the Django server

python manage.py runserver

The application will be available at:

http://127.0.0.1:8000/

Background Monitoring

For background monitoring, the project uses Celery, Redis, and Celery
Beat.

Start Redis

Redis must be available as the Celery broker.

Start Celery Worker

celery -A backend worker --loglevel=info

Start Celery Beat

celery -A backend beat --loglevel=info

The worker executes monitoring tasks while Celery Beat schedules them.

Docker

The project includes a Docker Compose configuration for the main
application services.

The Docker setup includes:

Django web server

PostgreSQL

Redis

Celery worker

Celery Beat

Start the full stack

docker compose --env-file .env.production up --build

The Django web service is exposed on:

http://127.0.0.1:8000/

Stop the stack

docker compose --env-file .env.production down

Stop and remove volumes

docker compose --env-file .env.production down -v

Removing volumes also removes the Docker-managed PostgreSQL data volume.

Environment Configuration

The project separates configuration from source code using environment
variables.

Example files are provided for reference:

.env.example
.env.production.example

Typical configuration areas include:

Django secret key

Debug configuration

Allowed hosts

Database configuration

PostgreSQL credentials

Redis/Celery configuration

Email configuration

Twilio configuration

CORS configuration

CSRF trusted origins

Production security settings

Real credentials must only be stored in local or deployment environment
variables.

Database

Local development

SQLite can be used for local development.

Production / Docker

PostgreSQL is supported for production-style deployments.

The Docker Compose configuration provides a PostgreSQL service with
persistent storage.

Security

API Monitor includes several security-oriented features:

JWT authentication

Access and refresh tokens

Per-user monitor ownership

Hashed user-generated API keys

Environment-based secret configuration

Bearer authentication for monitored APIs

API-key authentication for monitored APIs

Production security configuration

Secrets should never be committed to the repository.

Monitoring Reliability

API Monitor is designed to avoid treating every temporary failure as
confirmed downtime.

The monitoring system uses consecutive failure detection:

Failure 1 → Continue monitoring
Failure 2 → Continue monitoring
Failure 3 → Confirm downtime

After downtime is confirmed:

DOWN
 │
 ▼
Incident created
 │
 ▼
Monitoring continues
 │
 ▼
Successful check
 │
 ▼
Recovery detected
 │
 ▼
Incident resolved

This approach helps reduce false-positive downtime incidents caused by
temporary request failures.

Current Capabilities

API Monitor currently provides:

Multi-API monitoring

Configurable HTTP methods

Expected status-code validation

Response-time thresholds

Periodic background health checks

Manual health checks

Pause/resume monitoring

Consecutive failure detection

Automatic incident creation

Automatic incident recovery

Monitoring logs

Log filtering and search

Monitoring data export

Uptime analytics

Average response-time analytics

P95 latency

Response-time trends

JWT authentication

User registration and login

API-key authentication

Bearer authentication

Email notifications

Twilio SMS support

Docker support

PostgreSQL support

Redis/Celery background processing

Future Improvements

Potential future improvements include:

More notification providers

Additional monitoring protocols

Advanced alert rules

More detailed performance reports

Expanded API documentation

More deployment options

Additional monitoring integrations

License

This project is available for learning, development, and portfolio
purposes.