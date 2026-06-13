"""
PII detector — pattern-based column name and value analysis.
Flags columns that likely contain personally identifiable information.
Requirements: DC-006, GS-004.
"""

import re

# Column-name patterns that strongly indicate PII
_NAME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bemail\b",
        r"\bphone\b",
        r"\bmobile\b",
        r"\bssn\b",
        r"\bnational_?id\b",
        r"\bpassport\b",
        r"\btax_?id\b",
        r"\bvat_?id\b",
        r"\bcredit_?card\b",
        r"\biban\b",
        r"\bdate_?of_?birth\b",
        r"\bdob\b",
        r"\bbirthdate\b",
        r"\baddress\b",
        r"\bstreet\b",
        r"\bzip_?code\b",
        r"\bpostal_?code\b",
        r"\bfull_?name\b",
        r"\bfirst_?name\b",
        r"\blast_?name\b",
        r"\bsurname\b",
        r"\bip_?address\b",
        r"\bgps\b",
        r"\blatitude\b",
        r"\blongitude\b",
        r"\bsalary\b",
        r"\bwage\b",
    ]
]

# Value patterns for sampling-based detection
_VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$")),
    ("phone", re.compile(r"^\+?[\d\s\-().]{7,20}$")),
    ("ssn", re.compile(r"^\d{3}-\d{2}-\d{4}$")),
    ("credit_card", re.compile(r"^\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}$")),
    ("iban", re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{4,30}$")),
    ("ip_address", re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")),
]


def is_pii_column_name(column_name: str) -> bool:
    """Return True if the column name matches a known PII pattern."""
    # `\b` does not break on `_` or camelCase, so also match a normalised form
    # ("phone_number" / "PhoneNumber" → "phone number").
    normalised = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", column_name).replace("_", " ")
    return any(p.search(column_name) or p.search(normalised) for p in _NAME_PATTERNS)


def is_pii_sample_values(samples: list[str]) -> bool:
    """
    Return True if a significant fraction of sample values match a PII pattern.
    Threshold: ≥60% of non-null samples match any pattern.
    """
    non_null = [s for s in samples if s and str(s).strip()]
    if not non_null:
        return False
    hits = 0
    for val in non_null:
        v = str(val).strip()
        if any(pat.match(v) for _, pat in _VALUE_PATTERNS):
            hits += 1
    return hits / len(non_null) >= 0.6


def assess_column_pii(column_name: str, sample_values: list[str] | None = None) -> bool:
    """Combined PII assessment: name-based first, then value sampling."""
    if is_pii_column_name(column_name):
        return True
    if sample_values:
        return is_pii_sample_values(sample_values)
    return False
