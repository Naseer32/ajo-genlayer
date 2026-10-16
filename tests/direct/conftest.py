"""
Test harness for the Ajo Hub contract (GenLayer direct tests).

All genlayer-test API calls (sender, value, time, expected reverts) live in THIS
file only. If your genlayer-test version names them differently, fix them here
and every test keeps working.
"""
import datetime
import json
import pytest

GEN = 10 ** 18
T0 = 1_800_000_000          # arbitrary fixed start time (unix seconds)
ROUND = 120                 # round length used by the tests (seconds)


def iso(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Harness:
    def __init__(self, vm, contract, alice, bob, carol):
        self.vm, self.c = vm, contract
        self.alice, self.bob, self.carol = alice, bob, carol
        self.at(0)

    def hex(self, who):
        return "0x" + who.hex() if isinstance(who, (bytes, bytearray)) else who.as_hex

    # --- environment -------------------------------------------------
    def at(self, offset: int):
        """Set chain time to T0 + offset seconds."""
        ts = iso(T0 + offset)
        self.vm.warp(ts)
        import sys
        gl = sys.modules.get("genlayer.gl")      # warp() does not refresh message_raw["datetime"]
        if gl is not None and getattr(gl, "message_raw", None) is not None:
            gl.message_raw["datetime"] = ts

    def send(self, who, fn, *args, value=0):
        self.vm.sender = who
        self.vm.value = value
        return getattr(self.c, fn)(*args)

    def reverts(self, message: str):
        return self.vm.expect_revert(message)

    # --- non-deterministic mocks (web page + LLM verdict) ------------------
    def mock_evidence(self, url, page_text, llm_verdict):
        """Mock the evidence page and the LLM answer (assumed genlayer-test API:
        direct_vm.mock_web / direct_vm.mock_llm - adjust here if yours differs)."""
        self.vm.mock_web(url, {"response": {"status": 200, "body": page_text}})
        self.vm.mock_llm(".*", "```json\n" + json.dumps(llm_verdict) + "\n```")

    def proof_code(self, gid, rnd, who):
        return self.c.get_proof_code(gid, rnd, self.hex(who))

    # --- read helpers ------------------------------------------------
    def group(self, gid):
        return json.loads(self.c.get_group(gid))

    def round(self, gid, rnd):
        return json.loads(self.c.get_round(gid, rnd))

    def credit(self, who):
        return int(self.c.get_credit(self.hex(who)))

    def locked(self):
        return int(self.c.get_total_locked())

    # --- scenarios ---------------------------------------------------
    def new_group(self, creator=None, gen=1, secs=ROUND, mult=1, covered=False):
        creator = creator or self.alice
        fn = "create_group_covered" if covered else "create_group"
        self.send(creator, fn, gen, secs, mult, value=gen * mult * GEN)
        return int(self.c.get_group_count())

    def started_group(self, covered=False, hosts=""):
        """alice (owner, member 1), bob (2), carol (3); started at T0.
        `hosts` = comma separated evidence hosts (must be set before start)."""
        gid = self.new_group(covered=covered)
        self.send(self.bob, "join", gid, value=GEN)
        self.send(self.carol, "join", gid, value=GEN)
        if hosts:
            self.send(self.alice, "set_evidence_hosts", gid, hosts)
        self.at(0)
        self.send(self.alice, "start", gid)
        return gid


@pytest.fixture
def h(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy("contracts/ajo.py")
    return Harness(direct_vm, contract, direct_alice, direct_bob, direct_charlie)
