#!/usr/bin/env python3
# DigiForge — DigiByte multi-algorithm mining hub
# Developed by Mikal
import base64
import json
import os
import re
import urllib.request
import urllib.parse
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
SHA_POOL_ID = "dgb-sha256"
SCRYPT_POOL_ID = "dgb-scrypt"
POOL_ID = SHA_POOL_ID
SCRYPT_STRATUM_PORT = "3258"

DB_METRICS_CACHE = {}
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

    pools = cfg.setdefault("pools", [])
    sha_pool = next(
        (pool for pool in pools if pool.get("id") == SHA_POOL_ID),
        None
    )
    sha_address = (
        str(sha_pool.get("address", "")).strip()
        if isinstance(sha_pool, dict)
        else ""
    )

    for pool in pools:
        pool_id = pool.get("id")
        if pool_id not in (SHA_POOL_ID, SCRYPT_POOL_ID):
            continue

        for daemon in pool.get("daemons") or []:
            if daemon.get("password") != RPC_PASSWORD:
                daemon["password"] = RPC_PASSWORD
                changed = True

        if pool_id == SCRYPT_POOL_ID and sha_address:
            if pool.get("address") != sha_address:
                pool["address"] = sha_address
                changed = True

        for key, value in miningcore_address_fields(
            pool.get("address", "")
        ).items():
            if pool.get(key) != value:
                pool[key] = value
                changed = True

        ports = pool.setdefault("ports", {})
        if pool_id == SHA_POOL_ID and "3257" not in ports:
            ports["3257"] = nerdminer_port_config()
            changed = True

        if (
            pool_id == SCRYPT_POOL_ID
            and SCRYPT_STRATUM_PORT not in ports
        ):
            ports[SCRYPT_STRATUM_PORT] = scrypt_lg07_port_config()
            changed = True

    scrypt_pool = next(
        (pool for pool in pools if pool.get("id") == SCRYPT_POOL_ID),
        None
    )
    if sha_address and scrypt_pool is None:
        pools.append(scrypt_pool_config(sha_address))
        changed = True

    if changed:
        atomic_write(CONFIG, json.dumps(cfg, indent=2) + "\n")

def load_config():
    ensure_config()
    return json.loads(CONFIG.read_text(encoding="utf-8"))

def current_address():
    pools = load_config().get("pools") or []
    sha_pool = next(
        (pool for pool in pools if pool.get("id") == SHA_POOL_ID),
        None
    )
    return str(sha_pool.get("address", "")) if sha_pool else ""

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

def scrypt_lg07_port_config():
    return {
        "name": "DigiForge Scrypt · Lucky Miner LG07",
        "listenAddress": "0.0.0.0",
        "difficulty": 2048,
        "varDiff": {
            "minDiff": 512,
            "maxDiff": 16384,
            "targetTime": 15,
            "retargetTime": 90,
            "variancePercent": 30
        }
    }

def pool_config(pool_id, coin, address, ports):
    return {
        "id": pool_id,
        "enabled": True,
        "coin": coin,
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
        "ports": ports,
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
    }

def sha256_pool_config(address):
    return pool_config(
        SHA_POOL_ID,
        "digibyte-sha256",
        address,
        {
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
        }
    )

def scrypt_pool_config(address):
    return pool_config(
        SCRYPT_POOL_ID,
        "digibyte-scrypt",
        address,
        {
            SCRYPT_STRATUM_PORT: scrypt_lg07_port_config()
        }
    )

def write_pool(address):
    cfg = load_config()
    cfg["pools"] = [
        sha256_pool_config(address),
        scrypt_pool_config(address),
    ]
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

def digibyte_algorithm_stats():
    info = rpc("getmininginfo")
    difficulties = info.get("difficulties") or {}
    network_hashrates = info.get("networkhashesps") or {}

    return {
        "sha256d": {
            "algorithm": "sha256d",
            "networkDifficulty": difficulties.get("sha256d", 0),
            "networkHashrate": network_hashrates.get("sha256d", 0),
        },
        "scrypt": {
            "algorithm": "scrypt",
            "networkDifficulty": difficulties.get("scrypt", 0),
            "networkHashrate": network_hashrates.get("scrypt", 0),
        },
    }

def get_json(url):
    with urllib.request.urlopen(url, timeout=4) as response:
        return json.loads(response.read().decode())

def miningcore_pool(pool_id=POOL_ID):
    body = get_json(MC_API + "/pools")
    pools = body.get("pools", body) if isinstance(body, dict) else body
    if not isinstance(pools, list):
        return {}
    for pool in pools:
        if pool.get("id") == pool_id:
            return pool
    return {}

def miningcore_miners(pool_id=POOL_ID):
    urls = [
        f"{MC_API}/pools/{pool_id}/miners?page=0&pageSize=50",
        f"{MC_API}/pools/{pool_id}/miners"
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

def miningcore_workers(pool_id=POOL_ID):
    workers = []

    for miner in miningcore_miners(pool_id):
        miner_id = str(miner.get("miner") or "").strip()
        if not miner_id:
            continue

        try:
            detail = get_json(f"{MC_API}/pools/{pool_id}/miners/{miner_id}")
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

def miningcore_db_metrics(pool_id=POOL_ID):
    now = time.monotonic()
    cache_entry = DB_METRICS_CACHE.get(pool_id) or {}
    cached = cache_entry.get("value")
    if cached is not None and now < cache_entry.get("expires", 0):
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
        """, (pool_id,))
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
        """, (pool_id,))

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
        """, (pool_id,))

        effective_hashrate_rows = db_fetch(cursor, """
            SELECT
                COALESCE(SUM(difficulty), 0)
                    * 4294967296.0 / 21600.0 AS effectivehashrate6h,
                COUNT(*) AS shares6h,
                MIN(created) AS windowstart,
                MAX(created) AS windowend,
                COALESCE(
                    (
                        SELECT MIN(all_shares.created)
                            <= NOW() - INTERVAL '6 hours'
                        FROM shares AS all_shares
                        WHERE all_shares.poolid = %s
                    ),
                    FALSE
                ) AS hasfullwindow
            FROM shares
            WHERE poolid = %s
              AND created > NOW() - INTERVAL '6 hours'
        """, (pool_id, pool_id))
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
        """, (pool_id,))

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
        """, (pool_id,))
        block_summary = block_summary_rows[0] if block_summary_rows else {}

        cursor.execute("""
            SELECT created
            FROM blocks
            WHERE poolid = %s
            ORDER BY created DESC
            LIMIT 1
        """, (pool_id,))
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
            """, (pool_id,))
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
            """, (pool_id, round_start))

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
        DB_METRICS_CACHE[pool_id] = {
            "value": result,
            "expires": time.monotonic() + DB_METRICS_TTL_SECONDS,
        }
        return result
    finally:
        conn.close()

def miningcore_db_history(pool_id, hours):
    ranges = {
        1: 60,
        6: 180,
        24: 600,
        168: 3600,
    }
    if hours not in ranges:
        raise ValueError("Unsupported history range")

    bucket_seconds = ranges[hours]

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
        cursor.execute("SET TRANSACTION READ ONLY")

        return db_fetch(cursor, """
            SELECT
                to_timestamp(
                    floor(extract(epoch FROM created) / %s) * %s
                ) AS created,
                AVG(poolhashrate) AS poolhashrate,
                AVG(sharespersecond) AS sharespersecond,
                AVG(networkhashrate) AS networkhashrate,
                AVG(networkdifficulty) AS networkdifficulty,
                AVG(connectedminers) AS connectedminers
            FROM poolstats
            WHERE poolid = %s
              AND created > NOW() - (%s * INTERVAL '1 hour')
            GROUP BY 1
            ORDER BY created ASC
        """, (
            bucket_seconds,
            bucket_seconds,
            pool_id,
            hours,
        ))
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

def pool_status_snapshot(pool_id, stratum_port, network_stats=None):
    result = {
        "pool": {
            "online": False,
            "stratum": False,
            "id": pool_id,
        },
        "miners": [],
        "performance": {},
        "round": {},
        "blocks": [],
        "blockSummary": {},
    }

    try:
        pool = miningcore_pool(pool_id)
        stats = pool.get("poolStats") or {}
        network = pool.get("networkStats") or {}
        ports = pool.get("ports") or {}

        result["pool"].update({
            "online": bool(pool),
            "stratum": bool(pool) and str(stratum_port) in ports,
            "id": pool.get("id") or pool_id,
            "connectedMiners": stats.get("connectedMiners", 0),
            "poolHashrate": stats.get("poolHashrate", 0),
            "poolEstimateHashrate": stats.get("poolHashrate", 0),
            "sharesPerSecond": stats.get("sharesPerSecond", 0),
            "networkHashrate": network.get("networkHashrate", 0),
            "networkDifficulty": network.get("networkDifficulty", 0),
            "blockHeight": network.get("blockHeight", 0),
        })

        try:
            live_workers = miningcore_workers(pool_id)
        except Exception as exc:
            live_workers = []
            result["minersError"] = str(exc)

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
            db_metrics = miningcore_db_metrics(pool_id)
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
            use_effective_hashrate = (
                effective_hashrate > 0
                and (
                    pool_id != SCRYPT_POOL_ID
                    or bool(effective.get("hasfullwindow"))
                )
            )
            if use_effective_hashrate:
                result["pool"]["poolHashrate"] = effective_hashrate
                result["pool"]["effectiveHashrate6h"] = effective_hashrate
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

        network_stats = network_stats or {}
        if network_stats.get("networkHashrate"):
            result["pool"]["networkHashrate"] = (
                network_stats["networkHashrate"]
            )
        if network_stats.get("networkDifficulty"):
            result["pool"]["networkDifficulty"] = (
                network_stats["networkDifficulty"]
            )
        if network_stats.get("algorithm"):
            result["pool"]["algorithm"] = network_stats["algorithm"]

        pool_hashrate = float(result["pool"].get("poolHashrate") or 0)
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

    return result

class Handler(BaseHTTPRequestHandler):
    server_version = "DigiForge/1.1.0"

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

        support_images = {
            "/support/btc.png": "support/btc.png",
            "/support/eth.png": "support/eth.png",
            "/support/doge.png": "support/doge.png",
            "/support/ltc.png": "support/ltc.png",
            "/support/dgb.png": "support/dgb.png",
        }
        if path in support_images:
            return self.send_file(
                support_images[path],
                "image/png"
            )

        if path == "/api/health":
            return self.send_json({"ok": True, "version": "1.1.0"})

        if path == "/api/history":
            query = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query
            )
            algorithm = str(
                (query.get("algorithm") or ["sha256d"])[0]
            ).lower()
            range_name = str(
                (query.get("range") or ["24h"])[0]
            ).lower()

            algorithms = {
                "sha256d": SHA_POOL_ID,
                "scrypt": SCRYPT_POOL_ID,
            }
            ranges = {
                "1h": 1,
                "6h": 6,
                "24h": 24,
                "7d": 168,
            }

            if algorithm not in algorithms:
                return self.send_json(
                    {"error": "Unsupported algorithm"},
                    400
                )
            if range_name not in ranges:
                return self.send_json(
                    {"error": "Unsupported history range"},
                    400
                )

            try:
                points = miningcore_db_history(
                    algorithms[algorithm],
                    ranges[range_name],
                )

                network_hashrate_source = "miningcore"
                if algorithm == "scrypt":
                    authoritative = digibyte_algorithm_stats()["scrypt"]
                    current_difficulty = float(
                        authoritative.get("networkDifficulty") or 0
                    )
                    current_hashrate = float(
                        authoritative.get("networkHashrate") or 0
                    )

                    if current_difficulty > 0 and current_hashrate > 0:
                        hashes_per_difficulty = (
                            current_hashrate / current_difficulty
                        )
                        for point in points:
                            difficulty = float(
                                point.get("networkdifficulty") or 0
                            )
                            point["networkhashrate"] = (
                                difficulty * hashes_per_difficulty
                            )
                        network_hashrate_source = (
                            "digibyte-scrypt-difficulty-estimate"
                        )

                return self.send_json({
                    "algorithm": algorithm,
                    "range": range_name,
                    "networkHashrateSource": network_hashrate_source,
                    "points": points,
                })
            except Exception as exc:
                return self.send_json(
                    {"error": str(exc)},
                    500
                )

        if path == "/api/status":
            result = {
                "version": "1.1.0",
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

            algorithm_stats = {}
            try:
                algorithm_stats = digibyte_algorithm_stats()
            except Exception as exc:
                result["algorithmStatsError"] = str(exc)

            sha256 = pool_status_snapshot(
                SHA_POOL_ID,
                "3256",
                algorithm_stats.get("sha256d"),
            )
            scrypt = pool_status_snapshot(
                SCRYPT_POOL_ID,
                SCRYPT_STRATUM_PORT,
                algorithm_stats.get("scrypt"),
            )

            # Preserve the original SHA256 top-level API for compatibility.
            result.update(sha256)

            # DigiForge 1.1.0 multi-algorithm API.
            result["algorithms"] = {
                "sha256d": sha256,
                "scrypt": scrypt,
            }

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
                "message": "Saved. DigiForge is starting the SHA256 and Scrypt pools automatically."
            })
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)

if __name__ == "__main__":
    ensure_config()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
