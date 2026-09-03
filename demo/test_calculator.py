import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest
from calculator import BankAccount, calculate_discount


def test_calculate_discount():
    # 100 with 20% discount should be 80.0
    assert calculate_discount(100.0, 0.20) == 80.0


def test_bank_account_deposit():
    account = BankAccount(100.0)
    assert account.deposit(50.0) == 150.0


def test_bank_account_withdraw():
    account = BankAccount(100.0)
    assert account.withdraw(40.0) == 60.0
    with pytest.raises(ValueError):
        account.withdraw(200.0)
