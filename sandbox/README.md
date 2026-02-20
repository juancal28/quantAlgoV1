# sandbox/

Manual testing scripts for verifying external service connections.

**These are NOT part of the application.** They exist purely for ad-hoc
verification and debugging. Do not import from these files.

## Scripts

### `test_alpaca_connection.py`

Verifies that your Alpaca API keys work for both data and trading:

```bash
# From the repo root, with venv active:
python sandbox/test_alpaca_connection.py
```

The script will:
1. Check account status (confirms trading API auth)
2. Fetch a latest bar for SPY (confirms data API auth)
3. **Ask you** before placing a 1-share test buy of SPY
4. Show the order result and current positions
