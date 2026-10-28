"""Repository-relative path matching shared by policy consumers."""

from fnmatch import fnmatchcase


def matches(value: str, patterns: tuple[str, ...]) -> bool:
    """Use case-sensitive shell patterns; stars may span path separators."""
    return any(fnmatchcase(value, pattern) for pattern in patterns)
