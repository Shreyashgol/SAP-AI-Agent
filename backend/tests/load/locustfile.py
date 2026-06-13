"""
Locust load test for the Enterprise AI Platform API.

Run against a live staging environment:
    locust -f tests/load/locustfile.py \
           --host=https://staging.<YOUR_DOMAIN> \
           --users=50 --spawn-rate=5 --run-time=5m \
           --headless

Scenarios:
  - HealthUser     : lightweight liveness probe (excluded from rate limit stats)
  - ConversationUser: realistic chat flow (auth → ask question → export)
  - DashboardUser  : dashboard read-heavy (list → get widgets)
"""

from __future__ import annotations

import json
import os
import random

from locust import HttpUser, between, task


_TEST_EMAIL = os.getenv("LOAD_TEST_EMAIL", "loadtest@example.com")
_TEST_PASSWORD = os.getenv("LOAD_TEST_PASSWORD", "loadtest-password")

_QUESTIONS = [
    "What were the top 10 customers by revenue last quarter?",
    "Show me monthly sales trends for this year",
    "Which products have the highest return rate?",
    "Compare Q1 and Q2 gross margin by product category",
    "What is the average order value by region?",
    "List open purchase orders over 30 days old",
    "Show inventory items below reorder point",
    "What is total payables outstanding by vendor?",
]


# ── Health probe ──────────────────────────────────────────────────────────────

class HealthUser(HttpUser):
    """Minimal liveness check — mimics Kubernetes probe traffic."""
    wait_time = between(5, 10)
    weight = 1

    @task
    def liveness(self):
        self.client.get("/api/v1/health/live", name="/health/live")


# ── Authenticated conversation flow ──────────────────────────────────────────

class ConversationUser(HttpUser):
    wait_time = between(2, 8)
    weight = 10

    def on_start(self):
        self._token: str | None = None
        self._tenant_id: str | None = None
        self._connection_id: str | None = None
        self._conversation_id: str | None = None
        self._turn_id: str | None = None
        self._login()

    def _login(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
            name="/auth/login",
        )
        if resp.status_code == 200:
            body = resp.json()
            self._token = body.get("data", {}).get("access_token")
            self._tenant_id = body.get("data", {}).get("tenant_id")

    def _headers(self) -> dict:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    @task(3)
    def ask_question(self):
        if not self._token or not self._connection_id:
            self._ensure_connection()
            return

        question = random.choice(_QUESTIONS)
        resp = self.client.post(
            "/api/v1/conversations",
            json={
                "connection_id": self._connection_id,
                "message": question,
            },
            headers=self._headers(),
            name="/conversations (ask)",
            timeout=140,
        )
        if resp.status_code == 200:
            body = resp.json().get("data", {})
            self._conversation_id = body.get("conversation_id")
            self._turn_id = body.get("turn_id")

    @task(1)
    def list_conversations(self):
        if not self._token:
            return
        self.client.get(
            "/api/v1/conversations",
            headers=self._headers(),
            name="/conversations (list)",
        )

    @task(1)
    def export_turn(self):
        if not self._token or not self._conversation_id or not self._turn_id:
            return
        self.client.get(
            f"/api/v1/conversations/{self._conversation_id}/turns/{self._turn_id}/export?format=csv",
            headers=self._headers(),
            name="/export (csv)",
        )

    def _ensure_connection(self):
        if not self._token:
            return
        resp = self.client.get(
            "/api/v1/connections",
            headers=self._headers(),
            name="/connections (list)",
        )
        if resp.status_code == 200:
            connections = resp.json().get("data", [])
            if connections:
                self._connection_id = connections[0]["id"]


# ── Dashboard read-heavy user ─────────────────────────────────────────────────

class DashboardUser(HttpUser):
    wait_time = between(1, 4)
    weight = 5

    def on_start(self):
        self._token: str | None = None
        self._dashboard_id: str | None = None
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
            name="/auth/login",
        )
        if resp.status_code == 200:
            self._token = resp.json().get("data", {}).get("access_token")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    @task(4)
    def list_dashboards(self):
        if not self._token:
            return
        resp = self.client.get(
            "/api/v1/dashboards",
            headers=self._headers(),
            name="/dashboards (list)",
        )
        if resp.status_code == 200:
            items = resp.json().get("data", [])
            if items and not self._dashboard_id:
                self._dashboard_id = items[0]["id"]

    @task(2)
    def get_dashboard(self):
        if not self._token or not self._dashboard_id:
            return
        self.client.get(
            f"/api/v1/dashboards/{self._dashboard_id}",
            headers=self._headers(),
            name="/dashboards/:id (get)",
        )

    @task(1)
    def list_alerts(self):
        if not self._token:
            return
        self.client.get(
            "/api/v1/alert-rules",
            headers=self._headers(),
            name="/alert-rules (list)",
        )
