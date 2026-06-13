"""Unit tests for PII detector — no DB or network required."""

import pytest

from app.services.discovery.pii_detector import assess_column_pii, is_pii_column_name, is_pii_sample_values


@pytest.mark.unit
class TestPIIColumnName:
    def test_email_column(self):
        assert is_pii_column_name("email") is True

    def test_phone_column(self):
        assert is_pii_column_name("phone_number") is True

    def test_ssn_column(self):
        assert is_pii_column_name("ssn") is True

    def test_dob_column(self):
        assert is_pii_column_name("date_of_birth") is True

    def test_salary_column(self):
        assert is_pii_column_name("salary") is True

    def test_safe_column(self):
        assert is_pii_column_name("product_code") is False

    def test_safe_column_id(self):
        assert is_pii_column_name("order_id") is False

    def test_safe_description(self):
        assert is_pii_column_name("description") is False

    def test_case_insensitive(self):
        assert is_pii_column_name("EMAIL") is True
        assert is_pii_column_name("PhoneNumber") is True


@pytest.mark.unit
class TestPIISampleValues:
    def test_email_samples(self):
        samples = ["alice@example.com", "bob@corp.org", "carol@test.io"]
        assert is_pii_sample_values(samples) is True

    def test_ssn_samples(self):
        samples = ["123-45-6789", "987-65-4321", "000-11-2222"]
        assert is_pii_sample_values(samples) is True

    def test_safe_samples(self):
        samples = ["Product A", "Widget B", "Item C", "SKU-001"]
        assert is_pii_sample_values(samples) is False

    def test_empty_samples(self):
        assert is_pii_sample_values([]) is False

    def test_null_samples(self):
        assert is_pii_sample_values(["", None, "  "]) is False  # type: ignore

    def test_mixed_mostly_safe(self):
        # Only 1 of 5 matches — below 60% threshold
        samples = ["123-45-6789", "Product A", "Widget B", "SKU-001", "Item C"]
        assert is_pii_sample_values(samples) is False


@pytest.mark.unit
class TestAssessColumnPII:
    def test_name_takes_priority(self):
        # Even with safe samples, PII name → True
        assert assess_column_pii("email", ["not-an-email"]) is True

    def test_value_based_detection(self):
        # Safe name, but PII values
        assert assess_column_pii("value1", ["alice@example.com", "bob@corp.org"]) is True

    def test_both_safe(self):
        assert assess_column_pii("unit_price", ["10.99", "5.50", "99.00"]) is False
