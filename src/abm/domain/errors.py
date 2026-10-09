"""Validation failure raised by value-object constructors."""

from __future__ import annotations


class InvalidValue(ValueError):
    """A value failed validation. The application maps it to VALIDATION_ERROR with no effect."""
