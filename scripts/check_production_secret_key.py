#!/usr/bin/env python3
"""Reject unsafe production keys before uploading deployment configuration."""
import os
import sys


def validate_secret_key(value):
    # Keep Django's security.W009 criteria; never include the value in errors.
    if (not isinstance(value, str) or len(value) < 50 or len(set(value)) < 5
            or value.startswith('django-insecure-') or '\n' in value or '\r' in value):
        raise ValueError(
            'Production SECRET_KEY must be a single-line random value with at least '
            '50 characters and 5 unique characters, without the django-insecure- prefix.'
        )


def main():
    try:
        validate_secret_key(os.environ.get('TIMEWEB_SECRET_KEY'))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
