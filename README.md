# Ajo Hub on GenLayer

Ajo (also called Esusu) is a traditional rotating savings circle common in Nigeria and across West Africa:
a group pays the same amount every round, and each round **one member receives the whole pot**, until
everyone has had a turn.

**Ajo Hub** is a single public GenLayer Intelligent Contract that hosts *unlimited* Ajo groups.
Anyone connects a wallet, creates a group with their own contribution (1, 5, 25, 1000 GEN ...) and
others join by group id. Rules, rounds, payouts and balances are enforced by code, not by trust.

> **Status: experimental, unaudited.** Tested by hand on GenLayer Studio and by the direct tests in this
> repo. Do not put real value in it before an independent security review.

## How it works

1. `create_group(contribution_gen, round_duration_secs, collateral_multiplier)` - creator sends the
   collateral and becomes member #1 and the group owner. Contribution is in **whole GEN**.
   `create_group_covered(...)` creates a **covered** group (see Safety features).
2. `join(gid)` - others join with the exact collateral. There is **no member cap**.
3. `start(gid)` - the owner starts once at least 2 members have joined. Joining then closes; the number
   of rounds equals the number of members; payout order is join order.
4. `pay(gid, round)` - each member pays the exact contribution once per round.
5. `claim_payout(gid, round)` - after the round ends (or when everyone paid) the pot is credited to that
   round's recipient. Anyone can trigger it.
6. `withdraw()` / `claim_all(gid)` - members pull their credit (payouts, refunds, collateral) to their wallet.

Group ids and round numbers **start at 1**.

### Safety features

| Risk | Protection |
|---|---|
| Paying a round twice | `paid[group:round:member]` flag - the second payment is refunded as credit |
| Paying out a round twice | `payout_done[group:round]` - second claim reverts |
| Re-entrancy / double withdraw | pull payments; credit is zeroed *before* the transfer |
| Funds trapped by a bad call | payable functions refund wrong calls as withdrawable credit |
| Members who do not pay | collateral is `slash`-ed into the pot once the deadline passes |
| Proof replay | proof URLs are hashed and can be used once |
| Take-and-run (receive payout, then stop paying) | **covered groups**: on payout the contract holds back enough to top the recipient's collateral up to every round they still owe; released at completion |
| Reputation | `get_defaults(gid, member)` exposes how often a member was slashed |
| AI abuse | validators (LLM) are only used for `submit_grace_proof`, which can grant a time extension and **never moves funds** |
| Accounting drift | `total_locked` tracks everything the contract owes and must equal its balance |
| Gas limits with big groups | no unbounded loops in write paths; `get_members` and `release_collateral` are paginated |

### Known limitations

- Native GEN only (no USDC/ERC-20 yet).
- In standard groups, collateral covers `collateral_multiplier` missed rounds, so a member who already
  received a payout and then stops paying can leave the group with a loss. Use a covered group (or a larger
  multiplier) when members do not know each other. Covered groups trade away part of the early-payout
  advantage: early recipients receive less up front because part is held as collateral.
- The owner decides when to `start` and may start with only 2 members; check `member_count` before joining.
- No audit has been done.

## Consensus: evidence check (`submit_grace_proof`)

A member who cannot pay in time can submit a proof URL. Each validator renders the page and asks an LLM for a
strict JSON verdict with four booleans: `amount_ok`, `time_ok`, `payer_ok`, `relevant`. Validators must agree on
**every** field (`gl.eq_principle.prompt_comparative`, with a `strict_eq` fallback on older SDKs), and the grace
is granted only if **all four** are true. Evidence text is treated as untrusted input. The result can only extend
the deadline by half a round; it can never move funds. Each proof URL can be used once.

## Important GenLayer note: paying wallets

Sending GEN from a contract to a normal wallet (EOA) with `gl.get_contract_at(addr).emit_transfer(...)`
produced `ERROR` messages and the funds never arrived in our tests. The working approach is the EVM-layer
interface:

```python
@gl.evm.contract_interface
class Payee:
    class View: pass
    class Write: pass

Payee(address).emit_transfer(value=amount)
```

## Repo layout

```
contracts/ajo.py            the Intelligent Contract
tests/direct/conftest.py    test harness (all genlayer-test API usage lives here)
tests/direct/test_ajo.py    direct tests
```

## Deploy (GenLayer Studio)

1. Load `contracts/ajo.py` in Studio, no constructor arguments, click Deploy.
2. Call `create_group` with e.g. `1`, `600`, `1` and value = collateral (1 GEN).
3. Others call `join(gid)` with the same value; the owner calls `start(gid)`.

Addresses are plain strings in `get_credit`, `has_paid`, `slash` and `transfer_group_owner`.

## Run the tests

```bash
pip install -r requirements.txt
pytest tests/direct -v
```

The tests were written against the genlayer-test direct-test fixtures (`direct_vm`, `direct_deploy`,
`direct_alice`, ...). Check your installed genlayer-test version's docs; if the names for setting the sender,
value or time differ, adjust them in `tests/direct/conftest.py` only.

`submit_grace_proof` (LLM + web) is not covered by direct tests; test it on Studio.

## Test report

See [docs/TESTING.md](docs/TESTING.md) for the manual Studio results, issues found and what is still untested.

## License

Add a license of your choice before publishing (for example MIT).
