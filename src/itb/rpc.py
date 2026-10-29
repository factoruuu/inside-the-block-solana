"""Minimal JSON-RPC client over httpx.

We use raw JSON-RPC instead of solana-py's client because the experiment
needs (a) exact control of sendTransaction parameters, (b) the *raw* getBlock
JSON stored byte-for-byte as evidence, and (c) no client-side retries or
caching silently changing what was sent or seen. Transaction construction and
signing are delegated to solders (see txbuild.py).
"""

from __future__ import annotations

import itertools
import os
import time

import httpx


class RpcError(Exception):
    pass


def _http_client(timeout: float) -> httpx.Client:
    """httpx client that honours proxy/CA env vars *selectively*.

    httpx's default trust_env=True parses NO_PROXY as URLs and crashes on
    bracketed IPv6 entries present in some sandboxes. We instead read only
    the two variables we actually need: HTTPS_PROXY (egress proxy, if the
    operator's environment requires one) and SSL_CERT_FILE (its CA bundle).
    In a normal environment neither is set and this is a plain direct client.
    """
    kwargs: dict = {"timeout": timeout, "trust_env": False}
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        kwargs["proxy"] = proxy
    ca_bundle = os.environ.get("SSL_CERT_FILE")
    if ca_bundle and os.path.exists(ca_bundle):
        kwargs["verify"] = ca_bundle
    return httpx.Client(**kwargs)


class RpcClient:
    def __init__(self, url: str, timeout: float = 30.0):
        self.url = url
        self._client = _http_client(timeout)
        self._ids = itertools.count(1)

    # Read-only, idempotent methods: safe to retry verbatim on transient
    # HTTP 429/502/503 (public RPC endpoints rate-limit getBlock and
    # getLeaderSchedule aggressively, and this sandbox's egress IP is
    # shared). Retrying a read with identical params cannot change what
    # was sent or seen. sendTransaction / simulateTransaction /
    # requestAirdrop are NEVER retried here.
    _READ_METHODS = {
        "getSlot", "getBlock", "getLeaderSchedule", "getEpochInfo",
        "getBalance", "getLatestBlockhash", "getVoteAccounts",
        "getClusterNodes", "getSignatureStatuses", "getSignaturesForAddress",
    }

    def call(self, method: str, params: list | None = None) -> object:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or []}
        attempts = 6 if method in self._READ_METHODS else 1
        for attempt in range(attempts):
            try:
                resp = self._client.post(self.url, json=payload)
            except httpx.TransportError:
                if attempt < attempts - 1:
                    time.sleep(min(5 * (2**attempt), 60))
                    continue
                raise
            if resp.status_code in (429, 502, 503) and attempt < attempts - 1:
                time.sleep(min(5 * (2**attempt), 60))
                continue
            resp.raise_for_status()
            body = resp.json()
            if "error" in body:
                raise RpcError(f"{method}: {body['error']}")
            return body.get("result")

    # -- typed helpers -----------------------------------------------------
    def get_slot(self) -> int:
        return int(self.call("getSlot", [{"commitment": "confirmed"}]))

    def get_latest_blockhash(self) -> str:
        res = self.call("getLatestBlockhash", [{"commitment": "confirmed"}])
        return res["value"]["blockhash"]

    def get_vote_accounts(self) -> dict:
        return self.call("getVoteAccounts", [{"commitment": "confirmed", "keepUnstakedDelinquents": False}])

    def get_cluster_nodes(self) -> list[dict]:
        return self.call("getClusterNodes")

    def get_epoch_info(self) -> dict:
        return self.call("getEpochInfo", [{"commitment": "confirmed"}])

    def get_leader_schedule(self, slot: int | None = None) -> dict:
        params: list = []
        if slot is not None:
            params.append(slot)
        params.append({"commitment": "confirmed"})
        return self.call("getLeaderSchedule", params)

    def get_block(self, slot: int) -> dict | None:
        """Full block; None if the slot was skipped / block unavailable."""
        try:
            return self.call(
                "getBlock",
                [
                    slot,
                    {
                        "encoding": "json",
                        "transactionDetails": "full",
                        "rewards": False,
                        # Post-Alpenglow mainnet blocks can contain v1
                        # transactions; requesting max version 0 makes
                        # getBlock fail for any block containing one.
                        "maxSupportedTransactionVersion": 1,
                    },
                ],
            )
        except RpcError as exc:
            if "was skipped" in str(exc) or "not available" in str(exc):
                return None
            raise

    def simulate_transaction(self, encoded_tx: str) -> dict:
        return self.call(
            "simulateTransaction",
            [encoded_tx, {"encoding": "base64", "commitment": "confirmed", "replaceRecentBlockhash": False}],
        )

    def send_transaction(self, encoded_tx: str) -> str:
        """Send with preflight ENABLED (skipPreflight=false) per design."""
        return str(
            self.call(
                "sendTransaction",
                [encoded_tx, {"encoding": "base64", "skipPreflight": False, "commitment": "confirmed"}],
            )
        )

    def request_airdrop(self, pubkey: str, lamports: int) -> str:
        return str(self.call("requestAirdrop", [pubkey, lamports]))

    def get_balance(self, pubkey: str) -> int:
        res = self.call("getBalance", [pubkey, {"commitment": "confirmed"}])
        return int(res["value"])

    def wait_for_block(self, slot: int, timeout_s: float = 30.0, poll_s: float = 1.0) -> dict | None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            block = self.get_block(slot)
            if block is not None:
                return block
            time.sleep(poll_s)
        return None
