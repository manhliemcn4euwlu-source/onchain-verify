# onchain-verify

Verify a BSC transaction against two independent RPC providers before you credit it.

A single provider can return `null` for a receipt it does not index, or an empty log array
for a block that does contain transfers. Both look like "this transaction does not exist"
and both are wrong. This tool reads the same transaction from two providers and only
returns `pass` when they agree on block number, status and every Transfer log.

## Install

No dependencies. Python 3.9 or newer, standard library only.

```bash
git clone <this repo>
cd onchain-verify
python3 -m unittest test_onchain_verify -v
```

## Use

```bash
# Did this transaction pay 25,000 FJ to this address?
python3 cli.py verify 0x<tx_hash> \
  --to 0x<recipient> \
  --value 25000000000000000000000 \
  --token 0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df

# Just read a FJ balance from two providers and compare
python3 cli.py treasury --holder 0x<address>
```

Exit codes: `0` pass, `1` mismatch, `2` unverifiable, `3` bad usage.

Behind an egress-restricted network, set the proxy explicitly:

```bash
export ONCHAIN_VERIFY_PROXY=http://127.0.0.1:7890
```

## Output

```json
{
  "verdict": "pass",
  "tx": "0x…",
  "block": 130896987,
  "status": "0x1",
  "transfers": [{"token": "0x…", "from": "0x…", "to": "0x…", "value": "…"}],
  "checks": [{"field": "value", "expected": "…", "actual": "…", "ok": true}],
  "sources": {"blastapi": {"ok": true, "block": 130896987},
              "blxrbdn": {"ok": true, "block": 130896987}},
  "cross_checked": true
}
```

`cross_checked` is the field to read first. When only one provider answered, it is
`false` and the verdict is a single read, not a cross-check.

## What the verdicts mean

| verdict | meaning |
|---|---|
| `pass` | at least one provider returned the receipt, both agreed when two answered, and every requested assertion matched |
| `mismatch` | the receipt was read and an assertion did not match; `checks` names which |
| `unverifiable` | no provider returned the receipt, or two providers disagreed. This is **not** evidence the transaction does not exist |

The distinction matters: `unverifiable` on a free public endpoint usually means the
provider does not index that block, not that the transaction is fake.

## Tests

```
python3 -m unittest test_onchain_verify -v
```

Nine tests, no network: bad hash, two sources agreeing, one source failing (must report
`cross_checked=false`), both failing, providers disagreeing, wrong recipient, wrong value,
wrong token, and the no-assertion case (two agreeing sources is a pass).

## License

MIT. See LICENSE.
