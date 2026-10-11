"""Direct tests for Ajo Hub. No LLM / web calls are exercised (submit_grace_proof is not covered)."""
from conftest import GEN, ROUND


# ---------------- groups & membership ----------------
def test_group_ids_start_at_one(h):
    assert h.new_group() == 1
    assert h.new_group(creator=h.bob, gen=5) == 2


def test_create_group_sets_params(h):
    gid = h.new_group(gen=25, secs=600, mult=2)
    g = h.group(gid)
    assert g["owner"].lower() == h.alice.as_hex.lower()
    assert g["contribution_wei"] == 25 * GEN
    assert g["collateral_wei"] == 50 * GEN
    assert g["member_count"] == 1 and g["status"] == 0
    assert h.locked() == 50 * GEN


def test_wrong_collateral_is_refunded_not_trapped(h):
    h.send(h.alice, "create_group", 1, ROUND, 1, value=2 * GEN)   # should be 1 GEN
    assert h.c.get_group_count() == 0
    assert h.credit(h.alice) == 2 * GEN
    assert h.locked() == 2 * GEN                                   # accounted, withdrawable


def test_duplicate_join_is_refunded(h):
    gid = h.new_group()
    h.send(h.bob, "join", gid, value=GEN)
    h.send(h.bob, "join", gid, value=GEN)
    assert h.group(gid)["member_count"] == 2
    assert h.credit(h.bob) == GEN


def test_leave_returns_collateral_and_owner_cannot_leave(h):
    gid = h.new_group()
    h.send(h.bob, "join", gid, value=GEN)
    h.send(h.bob, "leave", gid)
    assert h.group(gid)["member_count"] == 1
    assert h.credit(h.bob) == GEN
    with h.reverts("owner cannot leave"):
        h.send(h.alice, "leave", gid)


def test_unlimited_members_no_cap(h):
    gid = h.new_group()
    for who in (h.bob, h.carol):
        h.send(who, "join", gid, value=GEN)
    assert h.group(gid)["member_count"] == 3


# ---------------- ownership & start ----------------
def test_only_owner_starts_and_needs_two_members(h):
    gid = h.new_group()
    with h.reverts("need at least 2 members"):
        h.send(h.alice, "start", gid)
    h.send(h.bob, "join", gid, value=GEN)
    with h.reverts("only group owner"):
        h.send(h.bob, "start", gid)
    h.send(h.alice, "start", gid)
    assert h.group(gid)["status"] == 1


def test_transfer_group_owner(h):
    gid = h.new_group()
    h.send(h.bob, "join", gid, value=GEN)
    with h.reverts("new owner must be a member"):
        h.send(h.alice, "transfer_group_owner", gid, h.carol.as_hex)
    h.send(h.alice, "transfer_group_owner", gid, h.bob.as_hex)
    assert h.group(gid)["owner"].lower() == h.bob.as_hex.lower()
    with h.reverts("only group owner"):
        h.send(h.alice, "start", gid)
    h.send(h.bob, "start", gid)


# ---------------- paying ----------------
def test_pay_and_double_pay_refund(h):
    gid = h.started_group()
    h.send(h.alice, "pay", gid, 1, value=GEN)
    h.send(h.alice, "pay", gid, 1, value=GEN)          # second time
    assert h.round(gid, 1)["pool_wei"] == GEN           # pool unchanged
    assert h.credit(h.alice) == GEN                     # extra payment withdrawable


def test_round_zero_and_wrong_amount_refunded(h):
    gid = h.started_group()
    h.send(h.bob, "pay", gid, 0, value=GEN)             # rounds start at 1
    h.send(h.bob, "pay", gid, 1, value=GEN // 2)        # wrong amount
    assert h.round(gid, 1)["pool_wei"] == 0
    assert h.credit(h.bob) == GEN + GEN // 2


def test_future_round_not_payable(h):
    gid = h.started_group()
    h.send(h.bob, "pay", gid, 2, value=GEN)             # round 2 not open yet
    assert h.round(gid, 2)["pool_wei"] == 0
    assert h.credit(h.bob) == GEN


# ---------------- payout ----------------
def test_full_round_payout_and_withdraw(h):
    gid = h.started_group()
    for who in (h.alice, h.bob, h.carol):
        h.send(who, "pay", gid, 1, value=GEN)
    assert h.round(gid, 1)["pool_wei"] == 3 * GEN
    assert h.round(gid, 1)["recipient"].lower() == h.alice.as_hex.lower()
    h.send(h.carol, "claim_payout", gid, 1)             # anyone may trigger
    assert h.round(gid, 1)["paid_out"] is True
    assert h.credit(h.alice) == 3 * GEN
    with h.reverts("already paid out"):
        h.send(h.bob, "claim_payout", gid, 1)           # no double payout
    h.send(h.alice, "withdraw")
    assert h.credit(h.alice) == 0
    with h.reverts("nothing to withdraw"):
        h.send(h.alice, "withdraw")                     # no double withdraw


def test_open_round_cannot_be_claimed_early(h):
    gid = h.started_group()
    h.send(h.alice, "pay", gid, 1, value=GEN)
    with h.reverts("round not settled"):
        h.send(h.alice, "claim_payout", gid, 1)


# ---------------- slash ----------------
def test_slash_flow(h):
    gid = h.started_group()
    h.send(h.alice, "pay", gid, 1, value=GEN)
    h.send(h.bob, "pay", gid, 1, value=GEN)
    h.at(10)
    with h.reverts("deadline not passed"):
        h.send(h.alice, "slash", gid, 1, h.carol.as_hex)
    h.at(ROUND + 1)
    h.send(h.alice, "slash", gid, 1, h.carol.as_hex)
    assert h.c.get_defaults(gid, h.carol.as_hex) == 1   # on-chain reputation
    assert h.round(gid, 1)["pool_wei"] == 3 * GEN       # collateral filled the gap
    with h.reverts("already settled"):
        h.send(h.alice, "slash", gid, 1, h.carol.as_hex)  # no double slash
    h.send(h.bob, "claim_payout", gid, 1)
    assert h.credit(h.alice) == 3 * GEN


def test_cannot_slash_someone_who_paid(h):
    gid = h.started_group()
    h.send(h.bob, "pay", gid, 1, value=GEN)
    h.at(ROUND + 1)
    with h.reverts("already settled"):
        h.send(h.alice, "slash", gid, 1, h.bob.as_hex)


# ---------------- isolation & accounting ----------------
def test_groups_do_not_mix_funds(h):
    g1 = h.started_group()
    h.at(0)
    g2 = h.new_group(creator=h.bob, gen=5)
    h.send(h.alice, "pay", g1, 1, value=GEN)
    assert h.round(g1, 1)["pool_wei"] == GEN
    assert g2 != g1 and h.group(g2)["status"] == 0


def test_total_locked_returns_to_zero_after_full_cycle(h):
    gid = h.started_group()
    for rnd in (1, 2, 3):
        h.at((rnd - 1) * ROUND + 1)
        for who in (h.alice, h.bob, h.carol):
            h.send(who, "pay", gid, rnd, value=GEN)
        h.send(h.alice, "claim_payout", gid, rnd)
    assert h.group(gid)["status"] == 2
    for who in (h.alice, h.bob, h.carol):
        h.send(who, "claim_all", gid)                   # collateral + payouts out
    assert h.locked() == 0


# ---------------- covered groups (anti take-and-run) ----------------
def test_covered_group_holds_back_collateral_top_up(h):
    gid = h.started_group(covered=True)
    assert h.group(gid)["covered"] is True
    for who in (h.alice, h.bob, h.carol):
        h.send(who, "pay", gid, 1, value=GEN)
    h.send(h.bob, "claim_payout", gid, 1)
    # alice still owes 2 rounds (2 GEN) but has 1 GEN collateral -> 1 GEN is held back
    assert h.credit(h.alice) == 2 * GEN
    assert h.locked() == 6 * GEN                         # nothing left the contract


def test_covered_last_recipient_gets_full_pot(h):
    gid = h.started_group(covered=True)
    for rnd in (1, 2, 3):
        h.at((rnd - 1) * ROUND + 1)
        for who in (h.alice, h.bob, h.carol):
            h.send(who, "pay", gid, rnd, value=GEN)
        h.send(h.alice, "claim_payout", gid, rnd)
    assert h.credit(h.carol) == 3 * GEN                  # nothing left to owe, no hold


# ---------------- steward fix 1: settlement can never strand obligations ----------------
def test_underfunded_round_cannot_finalize_before_slash(h):
    gid = h.started_group()
    h.send(h.alice, "pay", gid, 1, value=GEN)            # bob and carol never pay
    h.at(ROUND + 1)
    with h.reverts("round not settled"):
        h.send(h.alice, "claim_payout", gid, 1)          # unpaid + unslashed -> cannot finalize
    h.send(h.alice, "slash", gid, 1, h.bob.as_hex)
    with h.reverts("round not settled"):
        h.send(h.alice, "claim_payout", gid, 1)          # carol still unsettled
    h.send(h.alice, "slash", gid, 1, h.carol.as_hex)
    h.send(h.alice, "claim_payout", gid, 1)              # now every obligation is settled
    assert h.credit(h.alice) == 3 * GEN


def test_final_underfunded_round_cannot_strand_obligations_or_release_collateral(h):
    gid = h.started_group()
    for rnd in (1, 2):
        h.at((rnd - 1) * ROUND + 1)
        for who in (h.alice, h.bob, h.carol):
            h.send(who, "pay", gid, rnd, value=GEN)
        h.send(h.alice, "claim_payout", gid, rnd)
    h.at(2 * ROUND + 1)                                   # final round (3) is open
    h.send(h.alice, "pay", gid, 3, value=GEN)
    h.send(h.bob, "pay", gid, 3, value=GEN)               # carol does not pay
    h.at(3 * ROUND + 1)                                   # final deadline passed
    with h.reverts("round not settled"):
        h.send(h.alice, "claim_payout", gid, 3)           # cannot finalize underfunded final round
    assert h.group(gid)["status"] == 1                    # group NOT completed
    with h.reverts("group not completed"):
        h.send(h.bob, "withdraw_collateral", gid)         # collateral NOT released
    with h.reverts("group not completed"):
        h.send(h.alice, "release_collateral", gid, 0, 50)
    # a safe settlement path remains: anyone can slash the defaulter
    h.send(h.bob, "slash", gid, 3, h.carol.as_hex)
    h.send(h.bob, "claim_payout", gid, 3)
    assert h.group(gid)["status"] == 2
    h.send(h.bob, "withdraw_collateral", gid)             # released only after settlement
    assert h.credit(h.bob) >= GEN


def test_defaulter_with_no_collateral_is_written_off_and_group_completes(h):
    gid = h.started_group()
    h.at(1)
    for who in (h.alice, h.bob, h.carol):
        h.send(who, "pay", gid, 1, value=GEN)
    h.send(h.alice, "claim_payout", gid, 1)
    for rnd in (2, 3):                                    # carol stops paying
        h.at((rnd - 1) * ROUND + 1)
        h.send(h.alice, "pay", gid, rnd, value=GEN)
        h.send(h.bob, "pay", gid, rnd, value=GEN)
        h.at(rnd * ROUND + 1)
        h.send(h.alice, "slash", gid, rnd, h.carol.as_hex)  # round 3: collateral already used -> written off, no revert
        h.send(h.alice, "claim_payout", gid, rnd)
    assert h.group(gid)["status"] == 2
    assert h.credit(h.carol) == 2 * GEN                   # last recipient bears the unrecoverable shortfall
    for who in (h.alice, h.bob, h.carol):
        h.send(who, "claim_all", gid)
    assert h.locked() == 0                                # nothing stranded in the contract


# ---------------- steward fix 2: grace evidence is bounded, bound to the member, third-party ----------------
URL = "https://receipts.example-pay.com/tx/abc123"
GOOD = {"amount_ok": True, "time_ok": True, "third_party": True}


def _evidence_group(h):
    gid = h.started_group(hosts="example-pay.com")
    h.at(ROUND // 2)                                       # round 1 is open
    return gid


def test_valid_evidence_grants_bounded_grace(h):
    gid = _evidence_group(h)
    code = h.proof_code(gid, 1, h.carol)
    h.mock_evidence(URL, f"Receipt. Reference {code}. Amount 1 GEN.", GOOD)
    h.send(h.carol, "submit_grace_proof", gid, 1, URL)
    assert h.c.has_grace(gid, 1, h.carol.as_hex) is True
    h.at(ROUND + 10)                                       # inside the extra half-round only
    with h.reverts("deadline not passed"):
        h.send(h.alice, "slash", gid, 1, h.carol.as_hex)
    h.at(ROUND + ROUND // 2 + 1)                           # extension is bounded
    h.send(h.alice, "slash", gid, 1, h.carol.as_hex)


def test_evidence_without_the_members_code_gets_no_grace(h):
    gid = _evidence_group(h)
    h.mock_evidence(URL, "Receipt. Amount 1 GEN. No reference.", GOOD)
    h.send(h.carol, "submit_grace_proof", gid, 1, URL)
    assert h.c.has_grace(gid, 1, h.carol.as_hex) is False


def test_evidence_bound_to_another_member_cannot_be_reused(h):
    gid = _evidence_group(h)
    bobs_code = h.proof_code(gid, 1, h.bob)
    h.mock_evidence(URL, f"Receipt. Reference {bobs_code}.", GOOD)
    h.send(h.carol, "submit_grace_proof", gid, 1, URL)    # carol submits bob's receipt
    assert h.c.has_grace(gid, 1, h.carol.as_hex) is False


def test_stale_evidence_gets_no_grace(h):
    gid = _evidence_group(h)
    code = h.proof_code(gid, 1, h.carol)
    h.mock_evidence(URL, f"Receipt {code}. Dated long before this round.",
                    {**GOOD, "time_ok": False})
    h.send(h.carol, "submit_grace_proof", gid, 1, URL)
    assert h.c.has_grace(gid, 1, h.carol.as_hex) is False


def test_self_attributed_evidence_gets_no_grace(h):
    gid = _evidence_group(h)
    code = h.proof_code(gid, 1, h.carol)
    h.mock_evidence(URL, f"I, carol, paid. {code}", {**GOOD, "third_party": False})
    h.send(h.carol, "submit_grace_proof", gid, 1, URL)
    assert h.c.has_grace(gid, 1, h.carol.as_hex) is False


def test_evidence_source_rules(h):
    gid = h.started_group()                                # no hosts configured
    h.at(ROUND // 2)
    with h.reverts("evidence not enabled for this group"):
        h.send(h.carol, "submit_grace_proof", gid, 1, URL)
    gid2 = _evidence_group(h)
    with h.reverts("host not allowed"):
        h.send(h.carol, "submit_grace_proof", gid2, 1, "https://evil.example.org/x")
    with h.reverts("https url required"):
        h.send(h.carol, "submit_grace_proof", gid2, 1, "http://receipts.example-pay.com/x")
    with h.reverts("round not open yet"):
        h.send(h.carol, "submit_grace_proof", gid2, 2, URL)


def test_proof_url_can_only_be_used_once(h):
    gid = _evidence_group(h)
    h.mock_evidence(URL, "no code here", GOOD)
    h.send(h.carol, "submit_grace_proof", gid, 1, URL)
    with h.reverts("proof already used"):
        h.send(h.bob, "submit_grace_proof", gid, 1, URL)
