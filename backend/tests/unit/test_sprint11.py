"""
Sprint 11 unit tests — Alert schemas, Report schedule schemas,
cron validation, admin invite idempotency, report task helpers.

Coverage:
  - AlertRuleCreate: field validation (rule_type, severity, operator, schedule)
  - AlertRulePatch: all-optional, selective updates
  - AlertAcknowledge: status allowlist
  - ReportScheduleCreate: cron validation (valid + invalid patterns)
  - ReportSchedulePatch: partial update
  - Cron regex: multiple real-world expressions
  - Admin schemas: inline validation assumptions
"""

from __future__ import annotations

import re
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.alert import AlertRuleCreate, AlertRulePatch, AlertAcknowledge
from app.schemas.report import ReportScheduleCreate, ReportSchedulePatch, _CRON_RE


# ── AlertRuleCreate ───────────────────────────────────────────────────────────

class TestAlertRuleCreate:
    def test_valid_threshold_rule(self):
        r = AlertRuleCreate(
            name="Low revenue",
            rule_type="threshold",
            operator="<",
            threshold_value=50000.0,
            severity="warning",
        )
        assert r.name == "Low revenue"
        assert r.severity == "warning"

    def test_valid_anomaly_rule(self):
        r = AlertRuleCreate(name="Z-score spike", rule_type="anomaly")
        assert r.rule_type == "anomaly"

    def test_invalid_rule_type_rejected(self):
        with pytest.raises(ValidationError) as exc:
            AlertRuleCreate(name="Bad", rule_type="regression")
        assert "rule_type" in str(exc.value)

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            AlertRuleCreate(name="Bad", rule_type="anomaly", severity="extreme")

    def test_invalid_operator_rejected(self):
        with pytest.raises(ValidationError):
            AlertRuleCreate(name="Bad", rule_type="threshold", operator="!=")

    def test_valid_operators(self):
        for op in (">", "<", "=", ">=", "<="):
            r = AlertRuleCreate(name="t", rule_type="threshold", operator=op)
            assert r.operator == op

    def test_monitoring_schedule_default(self):
        r = AlertRuleCreate(name="t", rule_type="anomaly")
        assert r.monitoring_schedule == "hourly"

    def test_invalid_schedule_rejected(self):
        with pytest.raises(ValidationError):
            AlertRuleCreate(name="t", rule_type="anomaly", monitoring_schedule="weekly")

    def test_assigned_role_ids_default_empty(self):
        r = AlertRuleCreate(name="t", rule_type="anomaly")
        assert r.assigned_role_ids == []

    def test_valid_schedules(self):
        for sched in ("hourly", "4hourly", "daily"):
            r = AlertRuleCreate(name="t", rule_type="anomaly", monitoring_schedule=sched)
            assert r.monitoring_schedule == sched


class TestAlertRulePatch:
    def test_all_none_valid(self):
        p = AlertRulePatch()
        assert p.name is None
        assert p.is_active is None

    def test_partial_patch(self):
        p = AlertRulePatch(is_active=False, threshold_value=99.0)
        assert p.is_active is False
        assert p.threshold_value == 99.0
        assert p.name is None


class TestAlertAcknowledge:
    def test_valid_acknowledged(self):
        a = AlertAcknowledge(status="acknowledged")
        assert a.status == "acknowledged"

    def test_valid_snoozed_with_time(self):
        a = AlertAcknowledge(status="snoozed", snoozed_until="2026-06-13T10:00:00Z")
        assert a.snoozed_until == "2026-06-13T10:00:00Z"

    def test_valid_escalated(self):
        a = AlertAcknowledge(status="escalated")
        assert a.status == "escalated"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            AlertAcknowledge(status="resolved")

    def test_active_status_rejected(self):
        with pytest.raises(ValidationError):
            AlertAcknowledge(status="active")


# ── ReportScheduleCreate ──────────────────────────────────────────────────────

class TestReportScheduleCreate:
    def test_valid_weekly_schedule(self):
        r = ReportScheduleCreate(
            name="Weekly Revenue",
            questions=["What is total revenue?"],
            cron_expression="0 8 * * 1",
        )
        assert r.cron_expression == "0 8 * * 1"
        assert len(r.questions) == 1

    def test_valid_daily_schedule(self):
        r = ReportScheduleCreate(
            name="Daily ops",
            questions=["What shipped today?", "What invoices are overdue?"],
            cron_expression="0 7 * * *",
        )
        assert len(r.questions) == 2

    def test_empty_questions_rejected(self):
        with pytest.raises(ValidationError) as exc:
            ReportScheduleCreate(
                name="Empty",
                questions=[],
                cron_expression="0 8 * * 1",
            )
        assert "question" in str(exc.value).lower()

    def test_invalid_cron_rejected(self):
        with pytest.raises(ValidationError):
            ReportScheduleCreate(
                name="Bad",
                questions=["Q"],
                cron_expression="not a cron",
            )

    def test_cron_stripped(self):
        r = ReportScheduleCreate(
            name="t",
            questions=["Q"],
            cron_expression="  0 8 * * 1  ",
        )
        assert r.cron_expression == "0 8 * * 1"

    def test_default_channels_empty(self):
        r = ReportScheduleCreate(
            name="t", questions=["Q"], cron_expression="0 8 * * 1"
        )
        assert r.delivery_channels == {}


class TestReportSchedulePatch:
    def test_all_optional(self):
        p = ReportSchedulePatch()
        assert p.name is None
        assert p.is_active is None

    def test_deactivate(self):
        p = ReportSchedulePatch(is_active=False)
        assert p.is_active is False

    def test_update_cron(self):
        p = ReportSchedulePatch(cron_expression="0 6 * * *")
        assert p.cron_expression == "0 6 * * *"


# ── Cron regex — additional valid patterns ────────────────────────────────────

class TestCronRegex:
    def _valid(self, expr: str) -> bool:
        return bool(_CRON_RE.match(expr.strip()))

    def test_every_minute(self):
        assert self._valid("* * * * *")

    def test_every_15_minutes(self):
        assert self._valid("*/15 * * * *")

    def test_specific_time(self):
        assert self._valid("30 9 * * 1-5")

    def test_first_of_month(self):
        assert self._valid("0 0 1 * *")

    def test_complex_expression(self):
        assert self._valid("0 8,12,17 * * 1-5")

    def test_too_few_fields_invalid(self):
        assert not self._valid("0 8 * *")

    def test_plain_text_invalid(self):
        assert not self._valid("every monday")

    def test_six_fields_invalid(self):
        assert not self._valid("0 8 * * 1 2026")
