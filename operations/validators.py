"""Reusable validation helpers for user-entered mobile phone numbers."""

import re


def validate_mobile_number(value, *, min_digits=7, max_digits=15):
    """Validate a phone/mobile number and reject obvious fake/sequential values.

    Accepts common display formatting (leading +, spaces, parentheses, hyphens),
    but not alphabetic characters or punctuation outside that set.
    """
    value = (value or '').strip()
    if not value:
        return 'Mobile number is required.'
    if not re.fullmatch(r'[+0-9()\-\s]+', value):
        return 'Enter a valid mobile number using digits and optional +, spaces, hyphens or parentheses.'
    digits = re.sub(r'\D', '', value)
    if not min_digits <= len(digits) <= max_digits:
        return f'Enter a valid mobile number containing {min_digits} to {max_digits} digits.'
    if len(set(digits)) == 1:
        return 'Repeated-digit mobile numbers are not valid.'
    # Reject long ascending/descending runs commonly used as test numbers.
    for start in range(len(digits) - 6):
        chunk = digits[start:start + 7]
        if all(int(chunk[i + 1]) - int(chunk[i]) == 1 for i in range(6)):
            return 'Sequential mobile numbers are not valid.'
        if all(int(chunk[i + 1]) - int(chunk[i]) == -1 for i in range(6)):
            return 'Sequential mobile numbers are not valid.'
    return None
