# DigiForge Changelog

Developed by Mikal.

## 1.0.9

- Fixed outdated repository and package references to ensure reliable future DigiForge updates.
- Updated official support, submission, icon, and project links.
- Updated GHCR image references while preserving the existing verified immutable image digests.
- No mining configuration, database, wallet, or Stratum behavior changes.
- Bitaxe/ASIC port 3256 and NerdMiner port 3257 remain unchanged.

## 1.0.8

- Changed the headline pool hashrate to a six-hour accepted-work effective hashrate calculated from accepted share difficulty.
- Changed statistical expected block time and pool network share to use the six-hour effective hashrate while retaining Miningcore's shorter-window estimate separately.
- Added a static, read-only Support DigiForge section with public BTC, ETH, DOGE, LTC, and DGB receiving addresses.
- Expanded DigiForge and Developed by Mikal attribution across DigiForge-owned dashboard, backend, wrappers, and integration files.
- Kept Bitaxe/ASIC Stratum port `3256` and NerdMiner V2 port `3257` unchanged.

## 1.0.7

- Added current mining-round effort based on accepted share difficulty versus DigiByte network difficulty.
- Added statistical expected time to block and the pool's current share of DigiByte SHA256 network hashrate.
- Added pool block history with height, timestamp, reward, status, confirmation progress, effort, miner address, and block hash when Miningcore records a block.
- Added pool-performance metrics from Miningcore's PostgreSQL history, including network hashrate, network difficulty, shares per second, chain height, and last network block time.
- Added per-worker `ACTIVE`, `IDLE`, and `STALE` status with total accepted shares, one-hour and 24-hour share counts, shares per second, and last accepted-share age.
- Added short-lived read-only PostgreSQL metric caching so normal dashboard refreshes do not repeatedly rescan Miningcore history.
- Kept Bitaxe/ASIC Stratum port `3256` and NerdMiner V2 port `3257` unchanged.

## 1.0.6

- Added dedicated NerdMiner V2 Stratum port `3257` with fixed difficulty `0.001`, while leaving Bitaxe/ASIC port `3256` unchanged.
- Added automatic migration so existing DigiForge pool configurations gain the NerdMiner port without replacing the configured reward address.
- Added worker-level Miningcore statistics so workers such as `BitaxePro`, `nrd1`, and `nrd2` can be displayed individually once they submit accepted shares.
- Changed the headline pool hashrate to the sum of active worker hashrates while retaining Miningcore's pool estimate separately.
- Removed the repeated TCP Stratum health probe that generated unnecessary connect/disconnect entries in Miningcore logs.
- Added an explicit DigiForge icon URL for the Umbrel home-screen app tile.

## 1.0.5

- Added native DigiByte `dgb1` SegWit reward-address support in Miningcore using `BechSegwit` with the `dgb` Bech32 prefix.
- Moved DigiForge web, DigiByte, Miningcore wrapper, and PostgreSQL wrapper code into versioned container images.
- Replaced shared `APP_SEED` runtime credentials with independent persistent DigiByte RPC and PostgreSQL secrets.
- Added automatic migration of existing Miningcore configuration and PostgreSQL credentials.
- Pinned DigiForge runtime images to immutable GHCR digests.
- Added authenticated PostgreSQL health checks and startup ordering so Miningcore waits for both database and web configuration readiness.

## 1.0.1

- Fixed `web_1` failing during container creation on umbrelOS.
- Removed the nested bind mount of `config/config.default.json` into the read-only `/app` mount.
- Changed the DigiForge web backend to load the default Miningcore configuration from `/data/config.default.json`.
- Kept the 1.0 dashboard, DigiByte node, Miningcore, PostgreSQL, Stratum port, and app-proxy topology unchanged.

## 1.0.0

- Added the production DigiForge dashboard and first-run DGB address setup.
- Added live node, pool and miner status.
- Added automatic Miningcore configuration reload helper.
- Corrected Umbrel app-proxy networking.
- Added DigiForge branding and DigiForge-owned repository/support links.
