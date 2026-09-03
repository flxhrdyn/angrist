from __future__ import annotations

from decimal import Decimal

import pytest

from demo.payment_processor import (
    PaymentProcessor,
    Transaction,
    TransactionStatus,
)


@pytest.fixture
def processor():
    return PaymentProcessor(
        merchant_id="merch_enterprise_992",
        secret_key="live_sk_9a8b7c6d5e4f3a2b1c",
        tier="ENTERPRISE",
    )


def test_signature_verification(processor):
    payload = b'{"event":"charge.succeeded","amount":5000}'
    import hashlib
    import hmac
    expected_sig = hmac.new(b"live_sk_9a8b7c6d5e4f3a2b1c", payload, hashlib.sha256).hexdigest()
    assert processor.verify_webhook_signature(payload, expected_sig) is True
    assert processor.verify_webhook_signature(payload, "invalid_signature") is False


def test_calculate_fee(processor):
    # Enterprise tier = 1.2% + $0.30
    fee = processor.calculate_transaction_fee(Decimal("100.00"), is_cross_border=False)
    assert fee == Decimal("1.50")

    # Enterprise tier cross-border = 1.2% + 1.0% = 2.2% + $0.30 = $2.50
    fee_cb = processor.calculate_transaction_fee(Decimal("100.00"), is_cross_border=True)
    assert fee_cb == Decimal("2.50")


def test_settle_batch_accounting(processor):
    rates = {
        "USD": Decimal("1.00"),
        "EUR": Decimal("1.10"),
    }
    txs = [
        Transaction(
            tx_id="tx_01",
            amount=Decimal("100.00"),
            currency="USD",
            is_cross_border=False,
        ),
        Transaction(
            tx_id="tx_02",
            amount=Decimal("200.00"),
            currency="EUR",
            is_cross_border=True,
        ),
        Transaction(
            tx_id="tx_03",
            amount=Decimal("50.00"),
            currency="USD",
            status=TransactionStatus.DECLINED,
        ),
    ]

    summary = processor.settle_batch(txs, rates, base_currency="USD")

    # tx_01: USD 100.00 gross -> fee = 100*0.012 + 0.30 = $1.50
    # tx_02: EUR 200.00 -> fee = 200*(0.012 + 0.010) + 0.30 = EUR 4.70.
    # Converted to USD:
    # tx_01 amount = 100.00, fee = 1.50
    # tx_02 amount = 200 * 1.10 = 220.00, fee = 4.70 * 1.10 = 5.17
    # Expected Gross = 100.00 + 220.00 = 320.00 (Gross must NOT include fees added)
    # Expected Fees = 1.50 + 5.17 = 6.67
    # Expected Net = 320.00 - 6.67 = 313.33
    assert summary.total_gross == Decimal("320.00")
    assert summary.total_fees == Decimal("6.67")
    assert summary.total_net == Decimal("313.33")
    assert summary.settled_count == 2
    assert summary.declined_count == 1

    # Settled transactions must have their status updated
    assert txs[0].status == TransactionStatus.SETTLED
    assert txs[1].status == TransactionStatus.SETTLED
    assert txs[2].status == TransactionStatus.DECLINED
