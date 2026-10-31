"""Eval fixtures: a small vet-clinic booking project (brief and nine short documents) and a tiny source snapshot.

The documents come from the specs-stage live check (spec 05 T4): short, realistic, and with the gaps that run found
(no move API, a receptionist without accounts, no time-off table, email undefined), so a good wizi asks before
writing specs.
"""

import io
import zipfile

BRIEF = {
    "vertical": "Local veterinary clinics",
    "service": "Online appointment booking for pet owners",
    "purpose": "Cut phone bookings so front-desk staff can focus on patients in the clinic",
    "users": "Pet owners booking visits; clinic receptionists managing the calendar",
    "workflows": "Owner picks a service and slot, gets an email confirmation; receptionist can move or cancel",
    "scope": "Single clinic, web only, one location; no payments in v1",
    "permissions": "Owners see only their own bookings; receptionists see all bookings of their clinic",
    "data_lifecycle": "Bookings kept 2 years then deleted; owners can delete their account",
    "constraints": "Budget under $50 per month hosting; launch in 6 weeks; one developer",
    "success_criteria": "40% of bookings online within 3 months",
}

DOCS = {
    "prd": """# PRD: Vet clinic online booking

## Purpose
Pet owners of a two-vet clinic in Lyon book appointments online instead of phoning.

## Functional requirements
- FR-1: An owner books a consultation (20 min) or vaccination (15 min) with a vet or the first available slot.
- FR-2: An owner cancels or moves a booking online up to 24 hours before it.
- FR-3: The receptionist sets each vet's weekly hours and blocks time off.
- FR-4: Owners book as guests (name, phone, email, pet name); no accounts.

## Non-functional requirements
- NFR-1: Booking page loads in under 2 seconds on 4G.
- NFR-2: Hosting under 50 EUR per month.

## Acceptance criteria
- AC-1: Two owners cannot book the same slot.
- AC-2: A cancellation less than 24 hours before is refused online.
""",
    "technical-spike": "# Technical spike\n\n## Experiments\n1. Prevent double booking with a unique constraint on (vet, start).\n",
    "sad-architecture": """# Architecture

## Components
- Web app: FastAPI (Python 3.12) serving Jinja2 pages and a JSON API.
- Database: PostgreSQL 16.
- Email: transactional email provider via SMTP.

## Module layout
- `app/main.py`, `app/routes/`, `app/models.py`, `app/db.py`, `tests/`.

## Design rules
- Server-rendered pages; no SPA.
""",
    "api-specification": """# API specification

## Conventions
JSON, UTC timestamps, errors as `{detail}`.

## Bookings
- API-1: `POST /api/bookings` {vet_id or null, service, start, owner{name, phone, email}, pet_name} → 201 booking; 409 slot taken.
- API-2: `DELETE /api/bookings/{id}?token=` → 204; 422 within 24 hours.

## Availability
- API-3: `GET /api/slots?date=&service=` → free slots per vet.
""",
    "database-schema": """# Database schema

## Tables
- DB-1 `vets(id, name)`
- DB-2 `working_hours(vet_id, weekday, start_time, end_time)`
- DB-3 `bookings(id, vet_id, service, start, end, owner_name, owner_phone, owner_email, pet_name, cancel_token, created_at)`, unique (vet_id, start)

## Retention
Bookings deleted 2 years after `start`.
""",
    "security-blueprint": """# Security blueprint

## Controls
- SEC-1: Cancellation links carry a random 32-byte token; no other way to change a booking.
- SEC-2: Rate-limit booking creation to 10 per IP per hour.
""",
    "devops-iac-spec": """# DevOps

## Environments
- Local: docker compose (app + postgres).
- Production: one small VM, docker compose.

## CI
- OPS-1: GitHub Actions runs `pytest` and `ruff check` on every push.
""",
    "qa-test-plan": """# QA test plan

## Test cases
- TC-1: Double booking of the same slot returns 409 (AC-1, SEC-—).
- TC-2: Cancelling 23 hours before returns 422 (AC-2).
- TC-3: Cancel with a wrong token returns 404 (SEC-1).
- TC-4: The 11th booking from one IP in an hour returns 429 (SEC-2).
""",
    "runbook": "# Runbook\n\n## Triage\n- Booking errors: check the app logs and the database connection.\n",
}


SOURCE = {
    "README.md": "# Salon bookings\n\nFlask app. Run `flask --app app run`. Tests: `pytest -q`.\n",
    "app/__init__.py": "from flask import Flask\n\n\ndef create_app():\n    app = Flask(__name__)\n    from . import routes\n\n    app.register_blueprint(routes.bp)\n    return app\n",
    "app/routes.py": (
        'from flask import Blueprint, request\n\nfrom .models import Booking, save\n\nbp = Blueprint("bookings", __name__)\n\n\n'
        '@bp.post("/bookings")\ndef book():\n    data = request.get_json()\n    booking = Booking(data["name"], data["phone"], data["start"])\n'
        '    save(booking)\n    return {"id": booking.id}, 201\n'
    ),
    "app/models.py": (
        'import sqlite3\nfrom dataclasses import dataclass, field\nfrom uuid import uuid4\n\nDB = "salon.db"\n\n\n@dataclass\nclass Booking:\n'
        "    name: str\n    phone: str\n    start: str\n    id: str = field(default_factory=lambda: uuid4().hex)\n\n\n"
        'def save(booking):\n    with sqlite3.connect(DB) as db:\n        db.execute("INSERT INTO bookings VALUES (?, ?, ?, ?)", '
        "(booking.id, booking.name, booking.phone, booking.start))\n"
    ),
    "tests/test_routes.py": 'def test_book(client):\n    assert client.post("/bookings", json={"name": "A", "phone": "1", "start": "2026-01-01T10:00"}).status_code == 201\n',
    "requirements.txt": "flask==3.0.3\npytest==8.3.3\n",
}


def source_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in SOURCE.items():
            archive.writestr(f"salon/{name}", text)
    return buffer.getvalue()
