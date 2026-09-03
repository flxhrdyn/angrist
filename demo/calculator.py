"""Simple financial calculator module."""


def calculate_discount(price: float, discount_rate: float) -> float:
    """Calculate the final price after discount."""
    return price - (price * discount_rate)



class BankAccount:
    """A simple bank account."""

    BANK_CODE = "ANG-001"

    def __init__(self, initial_balance: float = 0.0):
        self.balance = initial_balance

    def deposit(self, amount: float) -> float:
        """Deposit funds into account."""
        self.balance += amount
        return self.balance

    def withdraw(self, amount: float) -> float:
        """Withdraw funds from account."""
        # Bug: Inverted condition raises error on valid withdraw!
        if amount < self.balance:
            raise ValueError("Insufficient funds")
        self.balance -= amount
        return self.balance
