from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    DECLINED = "DECLINED"
    REFUNDED = "REFUNDED"


@dataclass
class Transaction:
    tx_id: str
    amount: Decimal
    currency: str
    status: TransactionStatus = TransactionStatus.PENDING
    is_cross_border: bool = False
    fee: Decimal = Decimal("0.00")
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SettlementSummary:
    total_gross: Decimal
    total_net: Decimal
    total_fees: Decimal
    settled_count: int
    declined_count: int


class PaymentProcessor:
    """Production payment settlement engine with multi-currency fee reconciliation."""

    TIER_FEES = {
        "STANDARD": Decimal("0.029"),   # 2.9%
        "PREMIUM": Decimal("0.019"),    # 1.9%
        "ENTERPRISE": Decimal("0.012"), # 1.2%
    }
    CROSS_BORDER_SURCHARGE = Decimal("0.010")  # +1.0%
    FIXED_TRANSACTION_FEE = Decimal("0.30")   # $0.30

    def __init__(self, merchant_id: str, secret_key: str, tier: str = "STANDARD"):
        self.merchant_id = merchant_id
        self._secret_key = secret_key.encode("utf-8")
        self.tier = tier

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        """Verify webhook signature using constant-time comparison."""
        expected_sig = hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature_header)

    def calculate_transaction_fee(self, amount: Decimal, is_cross_border: bool = False) -> Decimal:
        """Calculate processing fee rounded to 2 decimal places using bankers rounding."""
        base_rate = self.TIER_FEES.get(self.tier, self.TIER_FEES["STANDARD"])
        rate = base_rate + (self.CROSS_BORDER_SURCHARGE if is_cross_border else Decimal("0"))
        variable_fee = amount * rate
        total_fee = variable_fee + self.FIXED_TRANSACTION_FEE
        return total_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def settle_batch(
        self,
        transactions: list[Transaction],
        exchange_rates: dict[str, Decimal],
        base_currency: str = "USD",
    ) -> SettlementSummary:
        """Settle a batch of transactions into base currency.

        Converts each eligible transaction to base currency, deducts transaction fees,
        and aggregates settlement accounting.
        """
        total_gross = Decimal("0.00")
        total_fees = Decimal("0.00")
        settled_count = 0
        declined_count = 0

        for tx in transactions:
            if tx.status == TransactionStatus.DECLINED:
                declined_count += 1
                continue

            rate = exchange_rates.get(tx.currency, Decimal("1.00"))

            # INTENTIONAL BUG: Fee calculation applied after currency conversion using
            # raw unrounded rates, causing floating Decimal precision drift and
            # incorrect cross-border surcharge attribution.
            # Fixed version: Calculate fee in transaction currency first,
            # then convert both amount and fee to base currency cleanly.
            fee = self.calculate_transaction_fee(tx.amount, is_cross_border=tx.is_cross_border)
            converted_amount = (tx.amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            converted_fee = (fee * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Faulty logic: incorrectly adds fee to gross and fails to update tx.status
            total_gross += converted_amount + converted_fee
            total_fees += converted_fee
            tx.fee = fee
            settled_count += 1

        total_net = total_gross - total_fees
        return SettlementSummary(
            total_gross=total_gross,
            total_net=total_net,
            total_fees=total_fees,
            settled_count=settled_count,
            declined_count=declined_count,
        )
