# API Monitor

A full-stack API monitoring dashboard built with **Django** and **Django REST Framework** that continuously checks configured APIs, tracks availability and response time, detects downtime, creates incidents, stores monitoring logs, and sends alerts.

## Overview

API Monitor helps developers and teams monitor the health of their APIs from a single dashboard.

The monitoring system periodically sends requests to configured APIs and records:

- API availability
- HTTP status
- Response time
- Failed requests
- Slow responses
- Downtime incidents
- Recovery events
- Uptime and performance analytics

When an API fails repeatedly, the system can confirm the failure, create an incident, and send notifications.

---

## Dashboard

The dashboard provides an overview of monitored APIs and their current health.

### Dashboard metrics

- Total APIs
- Healthy APIs
- Down APIs
- Slow APIs
- Availability percentage
- Last response time
- Last checked time
- Last error

---

## Features

### API Monitoring

- Monitor multiple APIs
- Configurable HTTP methods
- Expected HTTP status validation
- Response-time threshold monitoring
- Automatic periodic health checks
- API availability tracking
- Slow-response detection

### Downtime Detection

The system does not immediately mark an API as DOWN after a single failed request.

A monitor must experience **three consecutive failed checks** before downtime is confirmed.

This helps prevent temporary network errors from creating unnecessary incidents.

### Incident Management

When downtime is confirmed:

1. The failure is recorded.
2. An incident is created.
3. The API is marked as DOWN.
4. Monitoring continues.
5. When a successful request is detected, the incident is automatically resolved.
6. Recovery information is recorded.

The Incidents page provides:

- Total incidents
- Open incidents
- Resolved incidents
- Affected APIs
- Incident history
- Start time
- Resolution time
- Duration
- Incident status

### Analytics

The application tracks API performance metrics including:

- Uptime percentage
- Error rate
- Average latency
- P95 latency
- Request statistics

Analytics can be viewed for:

- 24 hours
- 7 days
- 30 days

### Logs

Monitoring results are stored as API logs containing information such as:

- HTTP status
- Response time
- Request time
- Error information
- API health result

### Authentication

The project includes:

- User registration
- User login
- Email/mobile login support
- JWT authentication
- Access tokens
- Refresh tokens
- Per-user monitor ownership
- User-generated API keys

### API Authentication

Monitored APIs can use authentication mechanisms including:

- Bearer authentication
- API key authentication

The application also provides its own API authentication using API keys.

API keys are stored securely using hashes rather than storing the raw key.

### Notifications

The monitoring system supports:

- Email alerts
- Twilio SMS support
- Down alerts
- Recovery alerts
- Slow-response alerts
- User notification preferences

### Background Monitoring

Monitoring is handled using:

- Celery
- Redis
- Celery Beat

Celery Beat schedules health checks while Celery workers execute the monitoring tasks.

### Docker

The project includes Docker configuration for running the application with:

- Django
- PostgreSQL
- Redis
- Celery
- Celery Beat

---

# Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Django | Web framework |
| Django REST Framework | REST API |
| Simple JWT | JWT authentication |
| Celery | Background tasks |
| Celery Beat | Scheduled monitoring |
| Redis | Celery broker |
| SQLite | Local development database |
| PostgreSQL | Production database |
| HTML | Dashboard structure |
| CSS | Dashboard styling |
| JavaScript | Frontend interactions |
| Docker | Containerization |
| Twilio | SMS notifications |

---

# Project Structure

```text
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