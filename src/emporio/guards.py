"""Security guards enforced in code (not only in the prompt).

- VerificationGuard: locks order lookups after repeated failed phone checks,
  so the 10,000 possible 4-digit combinations can't be brute-forced.
"""

from __future__ import annotations

from typing import Any, Callable

from emporio.tools import ORDER_NOT_FOUND

ToolRunner = Callable[[str, dict[str, Any]], dict[str, Any]]

MAX_VERIFICATION_FAILURES = 3
STORE_CONTACT = "(67) 3341-4444 or contato@emporiodamusica.com.br"
LOCKED_ERROR = (
    "Order lookup is locked for this conversation after too many failed verification "
    f"attempts. Do not ask for more digits. Direct the customer to the store: {STORE_CONTACT}."
)


class VerificationGuard:
    """Wraps a tool runner and locks get_order_status after N failed verifications.

    One guard per conversation (Agent). A failed verification is the generic
    "not found / digits don't match" error. Once locked, the tool is not called
    at all, so nothing more can be learned in this conversation.
    """

    def __init__(self, runner: ToolRunner, max_failures: int = MAX_VERIFICATION_FAILURES) -> None:
        self.runner = runner
        self.max_failures = max_failures
        self.failures = 0

    @property
    def locked(self) -> bool:
        return self.failures >= self.max_failures

    def __call__(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name != "get_order_status":
            return self.runner(name, args)
        if self.locked:
            return {"error": LOCKED_ERROR, "locked": True}
        result = self.runner(name, args)
        if result.get("error") == ORDER_NOT_FOUND:
            self.failures += 1
            if self.locked:
                return {"error": f"{ORDER_NOT_FOUND} {LOCKED_ERROR}", "locked": True}
            return {**result, "attempts_left": self.max_failures - self.failures}
        return result
