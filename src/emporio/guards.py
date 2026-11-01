"""Security guards enforced in code (not only in the prompt).

- VerificationGuard: locks order lookups after repeated failed phone checks,
  so the 10,000 possible 4-digit combinations can't be brute-forced.
- mask_args / mask_result: hide personal data (LGPD) in what we display or store
  (debug trace, transcripts, logs, eval reports). Tools still get the real values.
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


# --- PII masking ---------------------------------------------------------------------

MASK = "••••"
SENSITIVE_ARGS = frozenset({"phone_last4"})
SENSITIVE_RESULT_KEYS = frozenset({"customer_first_name", "tracking_code"})


def mask_args(args: dict[str, Any]) -> dict[str, Any]:
    """Copy of tool args with verification data hidden, for display and logs."""
    return {k: (MASK if k in SENSITIVE_ARGS else v) for k, v in args.items()}


def mask_result(result: dict[str, Any]) -> dict[str, Any]:
    """Copy of a tool result with personal fields hidden, for summaries and logs."""
    return {k: (MASK if k in SENSITIVE_RESULT_KEYS and v else v) for k, v in result.items()}


def sensitive_values(args: dict[str, Any], result: dict[str, Any]) -> set[str]:
    """Personal values from one tool call (real args and result) that must be masked in free text."""
    found = {str(args[k]) for k in SENSITIVE_ARGS if args.get(k)}
    found |= {str(result[k]) for k in SENSITIVE_RESULT_KEYS if result.get(k)}
    return {v for v in found if len(v) >= 2}


def mask_text(text: str, secrets: set[str]) -> str:
    """Replace every known personal value in a free text (e.g. a rejected draft) with the mask."""
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, MASK)
    return text
