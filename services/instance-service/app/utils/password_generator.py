"""
Password generation utility for secure random passwords
"""

import secrets
import string


def generate_secure_password(length: int = 10) -> str:
    """
    Generate a cryptographically secure random password.

    Password will meet Odoo requirements:
    - Minimum 8 characters (default 10)
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character (easy-to-type characters only)

    Args:
        length: Password length (minimum 8, default 10)

    Returns:
        Secure random password string (e.g., "Qw3r$Ty-Mz")

    Raises:
        ValueError: If length is less than 8
    """
    if length < 8:
        raise ValueError("Password length must be at least 8 characters")

    # Define character sets - only easy-to-type, unambiguous characters
    # Removed confusing: I, O (look like 1, 0)
    uppercase = "ABCDEFGHJKLMNPQRSTUVWXYZ"

    # Removed confusing: l, o (look like 1, 0)
    lowercase = "abcdefghijkmnpqrstuvwxyz"

    # Removed confusing: 0, 1 (look like O, l, I)
    digits = "23456789"

    # Only common, easy-to-type special characters
    # Removed problematic: | \ / { } [ ] < > ; : , . % ^ ? ` ' "
    special = "!@#$*-_+="

    # All characters combined
    all_chars = uppercase + lowercase + digits + special

    # Ensure password meets all requirements by guaranteeing at least one of each
    password = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(special)
    ]

    # Fill remaining length with random characters
    password.extend(secrets.choice(all_chars) for _ in range(length - 4))

    # Shuffle to avoid predictable pattern (first 4 chars always being upper, lower, digit, special)
    secrets.SystemRandom().shuffle(password)

    return ''.join(password)


def validate_password_strength(password: str) -> tuple[bool, list[str]]:
    """
    Validate password meets Odoo requirements.

    Args:
        password: Password string to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")

    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")

    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")

    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")

    return (len(errors) == 0, errors)
