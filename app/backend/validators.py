from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


DATE_INPUT_FORMAT = "%d-%m-%Y"
DATE_STORAGE_FORMAT = "%Y-%m-%d"


@dataclass
class ValidationResult:
    is_valid: bool
    normalized_value: str | None = None
    error_message: str | None = None


def validate_full_name(value: str | None) -> ValidationResult:
    if value is None:
        return ValidationResult(is_valid=False, error_message="Full name is required.")

    normalized = " ".join(value.strip().split())
    if not normalized:
        return ValidationResult(is_valid=False, error_message="Full name is required.")

    if len(normalized.split()) < 2:
        return ValidationResult(
            is_valid=False,
            error_message="Please provide your full name with at least first and last name.",
        )

    return ValidationResult(is_valid=True, normalized_value=normalized)


def validate_ssn_last4(value: str | None) -> ValidationResult:
    if value is None:
        return ValidationResult(is_valid=False, error_message="SSN last 4 is required.")

    normalized = value.strip()
    if len(normalized) != 4 or not normalized.isdigit():
        return ValidationResult(
            is_valid=False,
            error_message="Please provide the last 4 digits of your SSN as exactly 4 numbers.",
        )

    return ValidationResult(is_valid=True, normalized_value=normalized)


def validate_date_of_birth(value: str | None) -> ValidationResult:
    if value is None:
        return ValidationResult(is_valid=False, error_message="Date of birth is required.")

    normalized = value.strip()
    try:
        parsed = datetime.strptime(normalized, DATE_INPUT_FORMAT)
    except ValueError:
        return ValidationResult(
            is_valid=False,
            error_message="Please provide your date of birth in DD-MM-YYYY format.",
        )

    return ValidationResult(is_valid=True, normalized_value=parsed.strftime(DATE_STORAGE_FORMAT))
