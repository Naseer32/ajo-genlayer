# Manual test report (GenLayer Studio, Oct 8-11 2026)

Setup: 3 wallets, contributions of 1 GEN (earlier runs 10 GEN), round length 120-600 s.

## Passed
- create_group, join, start (owner only), pay, claim_payout, withdraw
- Full 3-round cycle; get_total_locked returned to 0 afterwards
- Double payment: second payment refunded as credit, pool unchanged
- claim_payout twice: rejected ("already paid out")
- slash after the deadline; second slash rejected ("already settled")
- leave before start returns collateral; the member can rejoin
- transfer_group_owner; the new owner started the group
- Several groups running at once; pools stay isolated per group
- Covered group: first recipient was credited 2 of 3 GEN (1 GEN held back)
- claim_all and withdraw_collateral

## Issues found and fixed
1. Sending GEN to a wallet with gl.get_contract_at(...).emit_transfer(...) ended in ERROR
   and the funds never arrived. Fixed with the gl.evm.contract_interface "Payee" pattern.
2. A reverted payable call kept the sent value inside the contract (20 GEN trapped in a
   test). Fixed: failed payable calls now refund the sender as withdrawable credit.
3. get_credit returns the wallet's total credit across all groups (by design).
4. Address arguments are passed as strings (the Studio UI had trouble with Address inputs).

## Not yet tested
- submit_grace_proof with a real proof (LLM + web consensus)
- Release of held collateral when a covered group completes
- Direct tests in tests/direct were written but not executed yet
- Every network (the final version was exercised on Studio)
- No independent audit

## On-chain verification of the steward fixes (Studio, Oct 11-12 2026)
Contract 0xfa12E7B2E192869E313Cd629C4244B836E31B537, source sha256 d166a5165ce88aee7491c12d922897a13e3ffdf889bdf7e6ae623214fc025ef8

Fix 1 (settlement): final round with one unpaid member
- claim_payout rejected "round not settled" (tx 0xb2b24b1fc2eb6d91...)
- withdraw_collateral rejected "group not completed" (tx 0xb7327ebacf71b8644...)
- after slash the round paid out, status became 2 and collateral was released

Fix 2 (evidence): all rejected as expected
- page without the member's on-chain code: no grace (has_grace = false)
- host not allowlisted: "host not allowed" (tx 0xb35697af8a0530a0...)
- reused URL: "proof already used" (tx 0xb0bb9e12560b0738...)
- http URL: "https url required" (tx 0x014894df144c0cb2...)
- future round: "round not open yet" (tx 0x972779b90f4aed56...)
- evidence after the extended deadline: "too late"

Not verified on-chain: a valid receipt page containing the member's code, stale evidence (date outside the
window) and self-attributed evidence. These are covered by direct tests (see below).

## Direct tests (Oct 12 2026)
`pytest tests/direct -q`: 29 passed (genlayer-test, direct mode).
Includes the steward-requested cases: a final underfunded round cannot finalize or release collateral until
every obligation is settled; stale, self-attributed, wrong-member and missing-code evidence cannot grant grace.
Note: the evidence tests mock the web page and the LLM verdict, so they verify the contract's decision logic
given a verdict, not the behaviour of real validators.
The harness (tests/direct/conftest.py) refreshes message_raw["datetime"] itself because vm.warp() does not.
