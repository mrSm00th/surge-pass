# from __future__ import annotations
from typing import Any


# Base class for razorpay exceptions
class RazorpayIntegrationError(Exception):
    def __init__(self, step: str, original: Exception | None = None):

        self.step = step
        self.original = original
        super().__init__(f"Razorpay call failed during '{step}': {original}")


#  Exception class to catch 4xx class problems: we sent malformed data
# This exception we need to convey to client
class RazorpayValidationError(RazorpayIntegrationError):
    @property
    def razorpay_description(self) -> str | None:

        if self.original is None:
            return None

        return str(self.original) or None

    class RazorpayUpstreamError(RazorpayIntegrationError):
        """
        This class indicates that their is either a Razorpay side netwrok issue
        or issue between us and razorpays network.
        Used for the SDK's GatewayError or ServerError.
        """

    # helper function thats helps us log the exception better
    def describe(exc: RazorpayIntegrationError) -> dict[str, Any]:

        return {
            "step": exc.step,
            "error_type": type(exc).__name__,
            "original": str(exc.original),
        }
