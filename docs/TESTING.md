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
