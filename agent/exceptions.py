class LowCreditsError(Exception):
    """Raised when the Anthropic API rejects a request due to insufficient credits."""
