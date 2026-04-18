from app.backend.validators import validate_date_of_birth, validate_full_name, validate_ssn_last4


def test_validate_full_name_accepts_first_and_last_name() -> None:
    result = validate_full_name("  John   Doe  ")

    assert result.is_valid is True
    assert result.normalized_value == "John Doe"


def test_validate_full_name_rejects_single_token() -> None:
    result = validate_full_name("John")

    assert result.is_valid is False


def test_validate_date_of_birth_accepts_dd_mm_yyyy_and_normalizes() -> None:
    result = validate_date_of_birth("15-06-1990")

    assert result.is_valid is True
    assert result.normalized_value == "1990-06-15"


def test_validate_date_of_birth_rejects_wrong_format() -> None:
    result = validate_date_of_birth("1990-06-15")

    assert result.is_valid is False


def test_validate_ssn_last4_accepts_exactly_four_digits() -> None:
    result = validate_ssn_last4("1234")

    assert result.is_valid is True
    assert result.normalized_value == "1234"


def test_validate_ssn_last4_rejects_non_digit_value() -> None:
    result = validate_ssn_last4("12a4")

    assert result.is_valid is False
