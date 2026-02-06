class MarketReporterError(Exception):
    """Base exception for application-level errors."""


class ProviderNotFoundError(MarketReporterError):
    """Raised when a provider id cannot be resolved."""


class ProviderExecutionError(MarketReporterError):
    """Raised when a provider fails to execute."""


class SecretStorageError(MarketReporterError):
    """Raised when secure key storage cannot be used."""


class ValidationError(MarketReporterError):
    """Raised when request payload fails domain-level validation."""
