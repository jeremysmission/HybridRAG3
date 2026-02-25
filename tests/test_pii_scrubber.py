# ============================================================================
# Tests for PII Scrubber (tests/test_pii_scrubber.py)
# ============================================================================

import pytest
from src.security.pii_scrubber import scrub_pii


# -- Email --

def test_email_replaced():
    text = "Contact john.doe@example.com for details."
    result, count = scrub_pii(text)
    assert "[EMAIL]" in result
    assert "john.doe@example.com" not in result
    assert count == 1


def test_multiple_emails():
    text = "Send to alice@corp.io and bob@test.org please."
    result, count = scrub_pii(text)
    assert count == 2
    assert "alice@corp.io" not in result
    assert "bob@test.org" not in result


# -- Phone --

def test_phone_dashes():
    text = "Call 555-123-4567 now."
    result, count = scrub_pii(text)
    assert "[PHONE]" in result
    assert "555-123-4567" not in result
    assert count == 1


def test_phone_parens():
    text = "Call (555) 123-4567 now."
    result, count = scrub_pii(text)
    assert "[PHONE]" in result
    assert count == 1


def test_phone_plus1():
    text = "Call +1-555-123-4567 now."
    result, count = scrub_pii(text)
    assert "[PHONE]" in result
    assert count == 1


# -- SSN --

def test_ssn_replaced():
    text = "SSN is 123-45-6789 on file."
    result, count = scrub_pii(text)
    assert "[SSN]" in result
    assert "123-45-6789" not in result
    assert count == 1


# -- Credit Card --

def test_credit_card_spaces():
    text = "Card: 4111 1111 1111 1111 on file."
    result, count = scrub_pii(text)
    assert "[CARD]" in result
    assert "4111" not in result
    assert count >= 1


def test_credit_card_dashes():
    text = "Card: 4111-1111-1111-1111 on file."
    result, count = scrub_pii(text)
    assert "[CARD]" in result
    assert count >= 1


# -- IPv4 --

def test_ipv4_replaced():
    text = "Server at 192.168.1.100 is down."
    result, count = scrub_pii(text)
    assert "[IP]" in result
    assert "192.168.1.100" not in result
    assert count == 1


def test_localhost_preserved():
    text = "Connect to 127.0.0.1:8000 for local API."
    result, count = scrub_pii(text)
    assert "127.0.0.1" in result


# -- Mixed --

def test_mixed_pii():
    text = (
        "Employee Jane (jane@corp.com, 555-867-5309, SSN 321-54-9876) "
        "logged in from 10.0.0.5."
    )
    result, count = scrub_pii(text)
    assert "[EMAIL]" in result
    assert "[PHONE]" in result
    assert "[SSN]" in result
    assert "[IP]" in result
    assert count >= 4


# -- No false positives --

def test_normal_text_unchanged():
    text = "The system uses AES-256 encryption with 2048-bit RSA keys."
    result, count = scrub_pii(text)
    assert result == text
    assert count == 0


def test_version_numbers_unchanged():
    text = "Python 3.12.1 and numpy 1.26.4 are installed."
    result, count = scrub_pii(text)
    assert result == text
    assert count == 0


# -- Edge cases --

def test_empty_string():
    result, count = scrub_pii("")
    assert result == ""
    assert count == 0


def test_none_passthrough():
    result, count = scrub_pii(None)
    assert result is None
    assert count == 0


# -- Toggle off --

def test_scrub_not_called_when_disabled():
    """Verify the scrub function itself always scrubs -- the toggle
    is tested at the integration level (config gating in llm_router)."""
    text = "Email: test@example.com"
    result, count = scrub_pii(text)
    assert "[EMAIL]" in result
    assert count == 1
