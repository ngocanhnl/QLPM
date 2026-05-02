from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentResult:
    ok: bool
    message: str = ""


class PaymentService:
    """
    Mock payment service (no gateway). Used to simulate "pay then book".
    """

    @staticmethod
    def process_card_payment(
        *,
        card_holder: str,
        card_number: str,
        expiry: str,
        cvv: str,
        amount: float,
    ) -> PaymentResult:
        # Basic validation for mock flow.
        digits = "".join(ch for ch in (card_number or "") if ch.isdigit())
        if len(digits) < 12:
            return PaymentResult(False, "Invalid card number")
        if len((cvv or "").strip()) < 3:
            return PaymentResult(False, "Invalid CVV")
        if not expiry or len(expiry.strip()) < 4 or "/" not in expiry:
            return PaymentResult(False, "Invalid expiry (expected MM/YY)")
        # Always "succeeds" if basic shape is ok.
        if not (card_holder or "").strip():
            return PaymentResult(False, "Card holder is required")
        return PaymentResult(True, f"Payment success. Amount: {amount:.0f}")

