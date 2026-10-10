"""Domain errors. The outer layers translate these (e.g. to HTTP 400/404)."""


class DomainError(Exception):
    """Base for every rule violation the domain or application reports."""


class InvalidInput(DomainError):
    """The request breaks a rule (bad slot, empty text, unknown week…)."""


class NotFound(DomainError):
    """The thing asked for does not exist."""
