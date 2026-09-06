#!/usr/bin/env python3
# DigiForge — DigiByte SHA256 mining hub
# Developed by Mikal
import base64
import json
import os
import re
import urllib.request
import time
from datetime import datetime, timezone
from decimal import Decimal

import pg8000.dbapi as pgdb
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/app")
DATA = Path("/data")
CONFIG = DATA / "config.json"
DEFAULT = ROOT / "config.default.json"

RPC_USER = "digiforge"
SECRETS = Path("/secrets")
RPC_PASSWORD_FILE = Path(os.environ.get(
    "DIGIBYTE_RPC_PASSWORD_FILE",
    str(SECRETS / "digibyte-rpc-password")
))
POSTGRES_PASSWORD_FILE = Path(os.environ.get(
    "POSTGRES_PASSWORD_FILE",
    str(SECRETS / "postgres-password")
))

def read_secret(path, label):
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"{label} secret unavailable: {exc}")
    if not value:
        raise RuntimeError(f"{label} secret is empty")
    return value

RPC_PASSWORD = read_secret(RPC_PASSWORD_FILE, "DigiByte RPC")
POSTGRES_PASSWORD = read_secret(POSTGRES_PASSWORD_FILE, "PostgreSQL")
RPC_URL = "http://digibyted:14022/"
MC_API = "http://miningcore:4000/api"
POOL_ID = "dgb-sha256"

DB_METRICS_CACHE = {
    "expires": 0.0,
    "value": None,
}
DB_METRICS_TTL_SECONDS = 10

def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)

def ensure_config():
    DATA.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)

    if not CONFIG.exists():
        raw = DEFAULT.read_text(encoding="utf-8").replace(
            "__POSTGRES_PASSWORD__",
            POSTGRES_PASSWORD
        )
        atomic_write(CONFIG, raw)
        return

    os.chmod(CONFIG, 0o600)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    changed = False

    postgres_cfg = (cfg.get("persistence") or {}).get("postgres")
    if isinstance(postgres_cfg, dict):
        if postgres_cfg.get("password") != POSTGRES_PASSWORD:
            postgres_cfg["password"] = POSTGRES_PASSWORD
            changed = True

    for pool in cfg.get("pools") or []:
        if pool.get("id") != POOL_ID:
            continue
        for daemon in pool.get("daemons") or []:
            if daemon.get("password") != RPC_PASSWORD:
                daemon["password"] = RPC_PASSWORD
                changed = True

        for key, value in miningcore_address_fields(pool.get("address", "")).items():
            if pool.get(key) != value:
                pool[key] = value
                changed = True

        ports = pool.setdefault("ports", {})
        if "3257" not in ports:
            ports["3257"] = nerdminer_port_config()
            changed = True

    if changed:
        atomic_write(CONFIG, json.dumps(cfg, indent=2) + "\n")

def load_config():
    ensure_config()
    return json.loads(CONFIG.read_text(encoding="utf-8"))

def current_address():
    pools = load_config().get("pools") or []
    return str(pools[0].get("address", "")) if pools else ""

def valid_address_syntax(value):
    # Conservative syntax guard only. DigiByte/Miningcore perform
    # authoritative chain validation when the pool starts.
    return bool(re.fullmatch(r"[A-Za-z0-9]{20,100}", value or ""))

def miningcore_address_fields(address):
    # Miningcore defaults Bitcoin-family SegWit addresses to the Bitcoin
    # human-readable prefix "bc". DigiByte native SegWit uses "dgb".
    if str(address).lower().startswith("dgb1"):
        return {
            "addressType": "BechSegwit",
            "bechPrefix": "dgb",
        }
    return {}

def nerdminer_port_config():
    return {
        "name": "DigiForge NerdMiner",
        "listenAddress": "0.0.0.0",
        "difficulty": 0.001,
    }

def write_pool(address):
    cfg = load_config()
    cfg["pools"] = [{
        "id": POOL_ID,
        "enabled": True,
        "coin": "digibyte-sha256",
        "address": address,
        **miningcore_address_fields(address),
        "blockRefreshInterval": 500,
        "jobRebroadcastTimeout": 10,
        "clientConnectionTimeout": 600,
        "banning": {
            "enabled": True,
            "time": 600,
            "invalidPercent": 50,
            "checkThreshold": 50
        },
        "ports": {
            "3256": {
                "name": "DigiForge SHA256",
                "listenAddress": "0.0.0.0",
                "difficulty": 512,
                "varDiff": {
                    "minDiff": 256,
                    "maxDiff": 8192,
                    "targetTime": 15,
                    "retargetTime": 90,
                    "variancePercent": 30
                }
            },
            "3257": nerdminer_port_config()
        },
        "daemons": [{
            "host": "digibyted",
            "port": 14022,
            "user": RPC_USER,
            "password": RPC_PASSWORD
        }],
        "paymentProcessing": {
            "enabled": False,
            "minimumPayment": 10,
            "payoutScheme": "PPLNS",
            "payoutSchemeConfig": {"factor": 2.0}
        }
    }]
    atomic_write(CONFIG, json.dumps(cfg, indent=2) + "\n")

def rpc(method, params=None):
    auth = base64.b64encode(f"{RPC_USER}:{RPC_PASSWORD}".encode()).decode()
    payload = json.dumps({
        "jsonrpc": "1.0",
        "id": "digiforge",
        "method": method,
        "params": params or []
    }).encode()
    request = urllib.request.Request(
        RPC_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic " + auth
        }
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        body = json.loads(response.read().decode())
    if body.get("error"):
        raise RuntimeError(str(body["error"]))
    return body.get("result")

def get_json(url):
    with urllib.request.urlopen(url, timeout=4) as response:
        return json.loads(response.read().decode())

def miningcore_pool():
    body = get_json(MC_API + "/pools")
    pools = body.get("pools", body) if isinstance(body, dict) else body
    if not isinstance(pools, list):
        return {}
    for pool in pools:
        if pool.get("id") == POOL_ID:
            return pool
    return pools[0] if pools else {}

def miningcore_miners():
    urls = [
        f"{MC_API}/pools/{POOL_ID}/miners?page=0&pageSize=50",
        f"{MC_API}/pools/{POOL_ID}/miners"
    ]
    last_error = None
    for url in urls:
        try:
            body = get_json(url)
            if isinstance(body, dict):
                value = body.get("miners", body.get("results", []))
                return value if isinstance(value, list) else []
            return body if isinstance(body, list) else []
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("miners endpoint unavailable")

def miningcore_workers():
    workers = []

    for miner in miningcore_miners():
        miner_id = str(miner.get("miner") or "").strip()
        if not miner_id:
            continue

        try:
            detail = get_json(f"{MC_API}/pools/{POOL_ID}/miners/{miner_id}")
            performance = (detail.get("performance") or {}).get("workers") or {}

            if isinstance(performance, dict):
                for worker_name, stats in performance.items():
                    stats = stats or {}
                    workers.append({
                        "miner": miner_id,
                        "worker": worker_name or "default",
                        "hashrate": stats.get("hashrate", 0),
                        "sharesPerSecond": stats.get("sharesPerSecond", 0),
                    })
        except Exception:
            continue

    return workers

def db_json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value

def db_fetch(cursor, sql, params=()):
    cursor.execute(sql, params)
    columns = [column[0] for column in cursor.description]
    return [
        dict(zip(columns, (db_json_value(value) for value in row)))
        for row in cursor.fetchall()
    ]

def miningcore_db_metrics():
    now = time.monotonic()
    cached = DB_METRICS_CACHE.get("value")
    if cached is not None and now < DB_METRICS_CACHE.get("expires", 0):
        return cached

    conn = pgdb.connect(
        host="postgres",
        port=5432,
        database="miningcore",
        user="miningcore",
        password=POSTGRES_PASSWORD,
        timeout=3,
    )

    try:
        cursor = conn.cursor()

        # Every dashboard database transaction is explicitly read-only.
        cursor.execute("SET TRANSACTION READ ONLY")

        pool_rows = db_fetch(cursor, """
            SELECT
                blockheight,
                poolhashrate,
                sharespersecond,
                networkhashrate,
                networkdifficulty,
                connectedminers,
                connectedpeers,
                lastnetworkblocktime,
                created
            FROM poolstats
            WHERE poolid = %s
            ORDER BY created DESC
            LIMIT 1
        """, (POOL_ID,))
        pool_stats = pool_rows[0] if pool_rows else {}

        worker_stats = db_fetch(cursor, """
            SELECT DISTINCT ON (worker)
                miner,
                worker,
                hashrate,
                sharespersecond,
                created
            FROM minerstats
            WHERE poolid = %s
              AND worker IS NOT NULL
              AND worker <> ''
            ORDER BY worker, created DESC
        """, (POOL_ID,))

        share_stats = db_fetch(cursor, """
            SELECT
                COALESCE(NULLIF(worker, ''), 'default') AS worker,
                miner,
                COUNT(*) AS acceptedshares,
                COUNT(*) FILTER (
                    WHERE created > NOW() - INTERVAL '1 hour'
                ) AS shareslasthour,
                COUNT(*) FILTER (
                    WHERE created > NOW() - INTERVAL '24 hours'
                ) AS shareslast24h,
                MAX(created) AS lastshare
            FROM shares
            WHERE poolid = %s
            GROUP BY COALESCE(NULLIF(worker, ''), 'default'), miner
            ORDER BY MAX(created) DESC
        """, (POOL_ID,))

        effective_hashrate_rows = db_fetch(cursor, """
            SELECT
                COALESCE(SUM(difficulty), 0)
                    * 4294967296.0 / 21600.0 AS effectivehashrate6h,
                COUNT(*) AS shares6h,
                MIN(created) AS windowstart,
                MAX(created) AS windowend
            FROM shares
            WHERE poolid = %s
              AND created > NOW() - INTERVAL '6 hours'
        """, (POOL_ID,))
        effective_hashrate = (
            effective_hashrate_rows[0]
            if effective_hashrate_rows else {}
        )

        block_rows = db_fetch(cursor, """
            SELECT
                blockheight,
                networkdifficulty,
                status,
                type,
                confirmationprogress,
                effort,
                miner,
                reward,
                hash,
                created
            FROM blocks
            WHERE poolid = %s
            ORDER BY created DESC
            LIMIT 10
        """, (POOL_ID,))

        block_summary_rows = db_fetch(cursor, """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE LOWER(COALESCE(status, '')) = 'confirmed'
                ) AS confirmed,
                COUNT(*) FILTER (
                    WHERE LOWER(COALESCE(status, '')) = 'pending'
                ) AS pending,
                COUNT(*) FILTER (
                    WHERE LOWER(COALESCE(status, '')) IN ('orphaned', 'orphan')
                ) AS orphaned,
                MAX(created) AS lastblock
            FROM blocks
            WHERE poolid = %s
        """, (POOL_ID,))
        block_summary = block_summary_rows[0] if block_summary_rows else {}

        cursor.execute("""
            SELECT created
            FROM blocks
            WHERE poolid = %s
            ORDER BY created DESC
            LIMIT 1
        """, (POOL_ID,))
        last_block = cursor.fetchone()
        round_start = last_block[0] if last_block else None

        if round_start is None:
            round_rows = db_fetch(cursor, """
                SELECT
                    COUNT(*) AS acceptedshares,
                    MIN(created) AS started,
                    MAX(created) AS lastshare,
                    100.0 * COALESCE(
                        SUM(difficulty / NULLIF(networkdifficulty, 0)),
                        0
                    ) AS effortpercent
                FROM shares
                WHERE poolid = %s
            """, (POOL_ID,))
        else:
            round_rows = db_fetch(cursor, """
                SELECT
                    COUNT(*) AS acceptedshares,
                    MIN(created) AS started,
                    MAX(created) AS lastshare,
                    100.0 * COALESCE(
                        SUM(difficulty / NULLIF(networkdifficulty, 0)),
                        0
                    ) AS effortpercent
                FROM shares
                WHERE poolid = %s
                  AND created > %s
            """, (POOL_ID, round_start))

        current_round = round_rows[0] if round_rows else {}

        result = {
            "poolStats": pool_stats,
            "workerStats": worker_stats,
            "shareStats": share_stats,
            "effectiveHashrate": effective_hashrate,
            "blocks": block_rows,
            "blockSummary": block_summary,
            "round": current_round,
        }
        DB_METRICS_CACHE["value"] = result
        DB_METRICS_CACHE["expires"] = (
            time.monotonic() + DB_METRICS_TTL_SECONDS
        )
        return result
    finally:
        conn.close()

def merge_worker_metrics(live_workers, db_metrics):
    live_by_worker = {
        str(worker.get("worker") or "default"): worker
        for worker in live_workers
    }
    stats_by_worker = {
        str(worker.get("worker") or "default"): worker
        for worker in db_metrics.get("workerStats", [])
    }
    shares_by_worker = {
        str(worker.get("worker") or "default"): worker
        for worker in db_metrics.get("shareStats", [])
    }

    names = list(live_by_worker)
    for source in (stats_by_worker, shares_by_worker):
        for name in source:
            if name not in names:
                names.append(name)

    now = datetime.now(timezone.utc)
    merged = []

    for name in names:
        live = live_by_worker.get(name, {})
        stats = stats_by_worker.get(name, {})
        shares = shares_by_worker.get(name, {})

        last_share_text = shares.get("lastshare")
        last_share_age = None
        if last_share_text:
            try:
                last_share = datetime.fromisoformat(last_share_text)
                last_share_age = max(0, (now - last_share).total_seconds())
            except (TypeError, ValueError):
                pass

        if last_share_age is not None and last_share_age <= 300:
            status = "active"
        elif last_share_age is not None and last_share_age <= 1800:
            status = "idle"
        else:
            status = "stale"

        hashrate = live.get("hashrate")
        if hashrate is None:
            hashrate = stats.get("hashrate", 0)

        shares_per_second = live.get("sharesPerSecond")
        if shares_per_second is None:
            shares_per_second = stats.get("sharespersecond", 0)

        merged.append({
            "miner": (
                live.get("miner")
                or shares.get("miner")
                or stats.get("miner")
                or ""
            ),
            "worker": name,
            "status": status,
            "hashrate": hashrate or 0,
            "sharesPerSecond": shares_per_second or 0,
            "acceptedShares": shares.get("acceptedshares", 0),
            "sharesLastHour": shares.get("shareslasthour", 0),
            "sharesLast24h": shares.get("shareslast24h", 0),
            "lastShare": last_share_text,
            "lastShareAgeSeconds": last_share_age,
            "statsUpdated": stats.get("created"),
        })

    status_order = {"active": 0, "idle": 1, "stale": 2}
    merged.sort(key=lambda worker: (
        status_order.get(worker.get("status"), 9),
        str(worker.get("worker") or "").lower(),
    ))
    return merged

class Handler(BaseHTTPRequestHandler):
    server_version = "DigiForge/1.0.8"

    def send_json(self, payload, status=200):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, filename, content_type):
        raw = (ROOT / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            return self.send_file("index.html", "text/html; charset=utf-8")
        if path == "/icon.svg":
            return self.send_file("icon.svg", "image/svg+xml")
        if path == "/api/health":
            return self.send_json({"ok": True, "version": "1.0.8"})

        if path == "/api/status":
            result = {
                "version": "1.0.8",
                "configured": bool(current_address()),
                "address": current_address(),
                "node": {"online": False},
                "pool": {"online": False, "stratum": False},
                "miners": [],
                "performance": {},
                "round": {},
                "blocks": [],
                "blockSummary": {}
            }

            try:
                chain = rpc("getblockchaininfo")
                net = rpc("getnetworkinfo")
                mem = rpc("getmempoolinfo")
                result["node"] = {
                    "online": True,
                    "blocks": chain.get("blocks", 0),
                    "headers": chain.get("headers", 0),
                    "progress": chain.get("verificationprogress", 0),
                    "pruned": chain.get("pruned", False),
                    "disk": chain.get("size_on_disk", 0),
                    "connections": net.get("connections", 0),
                    "mempool": mem.get("size", 0)
                }
            except Exception as exc:
                result["node"]["error"] = str(exc)

            try:
                pool = miningcore_pool()
                stats = pool.get("poolStats") or {}
                network = pool.get("networkStats") or {}
                ports = pool.get("ports") or {}
                result["pool"].update({
                    "online": bool(pool),
                    "stratum": bool(pool) and "3256" in ports,
                    "id": pool.get("id"),
                    "connectedMiners": stats.get("connectedMiners", 0),
                    "poolHashrate": stats.get("poolHashrate", 0),
                    "poolEstimateHashrate": stats.get("poolHashrate", 0),
                    "sharesPerSecond": stats.get("sharesPerSecond", 0),
                    "networkHashrate": network.get("networkHashrate", 0),
                    "networkDifficulty": network.get("networkDifficulty", 0),
                    "blockHeight": network.get("blockHeight", 0)
                })
                try:
                    live_workers = miningcore_workers()
                except Exception as exc:
                    live_workers = []
                    result["minersError"] = str(exc)

                # Preserve live Miningcore worker visibility even if the
                # optional PostgreSQL history/round metrics are unavailable.
                fallback_workers = []
                for worker in live_workers:
                    fallback = dict(worker)
                    fallback["status"] = "active"
                    fallback["historyAvailable"] = False
                    fallback_workers.append(fallback)

                result["miners"] = fallback_workers
                result["pool"]["connectedWorkers"] = len(fallback_workers)

                if fallback_workers:
                    result["pool"]["poolHashrate"] = sum(
                        float(worker.get("hashrate") or 0)
                        for worker in fallback_workers
                    )

                try:
                    db_metrics = miningcore_db_metrics()
                    workers = merge_worker_metrics(live_workers, db_metrics)

                    for worker in workers:
                        worker["historyAvailable"] = True

                    result["miners"] = workers
                    result["performance"] = db_metrics.get("poolStats", {})
                    result["round"] = db_metrics.get("round", {})
                    result["blocks"] = db_metrics.get("blocks", [])
                    result["blockSummary"] = db_metrics.get("blockSummary", {})

                    active_workers = [
                        worker for worker in workers
                        if worker.get("status") == "active"
                    ]
                    result["pool"]["connectedWorkers"] = len(active_workers)

                    effective = db_metrics.get("effectiveHashrate", {})
                    effective_hashrate = float(
                        effective.get("effectivehashrate6h") or 0
                    )
                    if effective_hashrate > 0:
                        result["pool"]["poolHashrate"] = effective_hashrate
                        result["pool"]["effectiveHashrate6h"] = (
                            effective_hashrate
                        )
                        result["pool"]["effectiveHashrateShares6h"] = int(
                            effective.get("shares6h") or 0
                        )

                    perf = result["performance"]
                    if not result["pool"].get("networkHashrate"):
                        result["pool"]["networkHashrate"] = perf.get(
                            "networkhashrate", 0
                        )
                    if not result["pool"].get("networkDifficulty"):
                        result["pool"]["networkDifficulty"] = perf.get(
                            "networkdifficulty", 0
                        )
                except Exception as exc:
                    result["performanceError"] = str(exc)

                pool_hashrate = float(
                    result["pool"].get("poolHashrate") or 0
                )
                network_hashrate = float(
                    result["pool"].get("networkHashrate") or 0
                )
                network_difficulty = float(
                    result["pool"].get("networkDifficulty") or 0
                )

                result["pool"]["networkSharePercent"] = (
                    100.0 * pool_hashrate / network_hashrate
                    if pool_hashrate > 0 and network_hashrate > 0
                    else None
                )
                result["pool"]["expectedBlockTimeSeconds"] = (
                    network_difficulty * (2 ** 32) / pool_hashrate
                    if pool_hashrate > 0 and network_difficulty > 0
                    else None
                )
            except Exception as exc:
                result["pool"]["error"] = str(exc)

            return self.send_json(result)

        return self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/setup":
            return self.send_json({"error": "Not found"}, 404)

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8192:
                return self.send_json({"error": "Invalid request"}, 400)

            body = json.loads(self.rfile.read(length).decode())
            address = str(body.get("address", "")).strip()

            if not valid_address_syntax(address):
                return self.send_json(
                    {"error": "Enter a valid-looking DigiByte address."},
                    400
                )

            write_pool(address)
            return self.send_json({
                "ok": True,
                "address": address,
                "message": "Saved. DigiForge is starting the SHA256 pool automatically."
            })
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)

if __name__ == "__main__":
    ensure_config()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
