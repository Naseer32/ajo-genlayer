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
    with h.reverts("round still open"):
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
