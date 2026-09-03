# Angrist Demo Scenario & VHS Recording

Guide for running the real-world payment processor demo scenario and recording terminal animation (GIF) using Charm VHS.

---

## Demo Scenario: Production Payment Settlement Engine

Target File: [`demo/payment_processor.py`](payment_processor.py)
Test File: [`demo/test_payment_processor.py`](test_payment_processor.py)

The module implements a production-grade multi-currency payment settlement engine with:
- `TransactionStatus` enumeration and `Transaction` dataclass.
- Constant-time HMAC-SHA256 signature verification (`verify_webhook_signature`).
- Tier-based processing fee calculation with cross-border surcharges (`calculate_transaction_fee`).
- Multi-currency batch settlement accounting (`settle_batch`).

### The Bug in `PaymentProcessor.settle_batch`:
In `settle_batch`, the settlement logic incorrectly adds transaction fees directly to `total_gross` instead of keeping gross sales separate, and fails to update the transaction status to `TransactionStatus.SETTLED` for processed items.

Running the test suite before repair demonstrates the failure:

```bash
pytest demo/test_payment_processor.py
# FAILED: AssertionError: assert Decimal('326.67') == Decimal('320.00')
```

When Angrist executes:
1. **Tree-sitter AST Guard:** Locks onto `PaymentProcessor.settle_batch`. The signature verification logic, fee tiers, dataclasses, and sibling methods remain mathematically locked down to the exact byte.
2. **Worktree Sandbox:** Executes in an isolated Git worktree outside your working directory.
3. **Delta Test Gate:** Verifies that the patch resolves `test_settle_batch_accounting` while preserving passing status on all other unit tests.
4. **Clean Merge:** Merges the surgical patch back into your working branch.

---

## Running the Demo Manually

### Using Real LLM or Local Model

```bash
# Verify the baseline test failure
pytest demo/test_payment_processor.py

# Run Angrist surgical repair
angrist fix \
  --file demo/payment_processor.py \
  --target PaymentProcessor.settle_batch \
  --instruction "In settle_batch, total_gross must only be the sum of converted_amount (do not add converted_fee to total_gross), and update tx.status to TransactionStatus.SETTLED for processed transactions" \
  --test-cmd "pytest demo/test_payment_processor.py" \
  --auto-merge

# Verify that all tests now pass
pytest demo/test_payment_processor.py
```

---

## Generating Demo GIF

### 1. Primary Method: Python PIL Generator (Recommended)
Reproducible, deterministic, zero external CLI dependencies (no ConPTY, ttyd, or Chrome required).
Note: this draws frames of terminal text rather than capturing a live session; the benchmark
numbers it renders are hardcoded to match the committed `benchmark_results.json`, not
recomputed live, so update both together if the suite's real results change.

```bash
python tools/generate_demo_gif.py
```

Renders the full `fix` and `benchmark` session into `demo/demo.gif` in seconds.

### 2. Optional: Recording Live with Charm VHS
For recording live interactive terminal sessions on Linux or macOS environments:

```bash
# Start local mock server (optional)
python demo/mock_server.py 8765 &

# Record tape
vhs demo/demo.tape
```
