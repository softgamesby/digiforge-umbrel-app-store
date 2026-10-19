SET ROLE miningcore;

CREATE TABLE IF NOT EXISTS shares (
    poolid TEXT NOT NULL,
    blockheight BIGINT NOT NULL,
    difficulty DOUBLE PRECISION NOT NULL,
    networkdifficulty DOUBLE PRECISION NOT NULL,
    miner TEXT NOT NULL,
    worker TEXT NULL,
    useragent TEXT NULL,
    ipaddress TEXT NOT NULL,
    source TEXT NULL,
    created TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shares_pool_miner ON shares(poolid, miner);
CREATE INDEX IF NOT EXISTS idx_shares_pool_created ON shares(poolid, created);

CREATE TABLE IF NOT EXISTS blocks (
    id BIGSERIAL PRIMARY KEY,
    poolid TEXT NOT NULL,
    blockheight BIGINT NOT NULL,
    networkdifficulty DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL,
    type TEXT NULL,
    confirmationprogress FLOAT NOT NULL DEFAULT 0,
    effort FLOAT NULL,
    minereffort DOUBLE PRECISION NULL,
    transactionconfirmationdata TEXT NOT NULL,
    miner TEXT NULL,
    reward DECIMAL(28,12) NULL,
    source TEXT NULL,
    hash TEXT NULL,
    created TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocks_pool_height_status
    ON blocks(poolid, blockheight, status);

CREATE TABLE IF NOT EXISTS balances (
    poolid TEXT NOT NULL,
    address TEXT NOT NULL,
    amount DECIMAL(28,12) NOT NULL DEFAULT 0,
    created TIMESTAMPTZ NOT NULL,
    updated TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(poolid, address)
);

CREATE TABLE IF NOT EXISTS balance_changes (
    id BIGSERIAL PRIMARY KEY,
    poolid TEXT NOT NULL,
    address TEXT NOT NULL,
    amount DECIMAL(28,12) NOT NULL DEFAULT 0,
    usage TEXT NULL,
    tags TEXT[] NULL,
    created TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS miner_settings (
    poolid TEXT NOT NULL,
    address TEXT NOT NULL,
    paymentthreshold DECIMAL(28,12) NOT NULL,
    created TIMESTAMPTZ NOT NULL,
    updated TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(poolid, address)
);

CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    poolid TEXT NOT NULL,
    coin TEXT NOT NULL,
    address TEXT NOT NULL,
    amount DECIMAL(28,12) NOT NULL,
    transactionconfirmationdata TEXT NOT NULL,
    created TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS poolstats (
    id BIGSERIAL PRIMARY KEY,
    poolid TEXT NOT NULL,
    connectedminers INT NOT NULL DEFAULT 0,
    poolhashrate DOUBLE PRECISION NOT NULL DEFAULT 0,
    sharespersecond DOUBLE PRECISION NOT NULL DEFAULT 0,
    networkhashrate DOUBLE PRECISION NOT NULL DEFAULT 0,
    networkdifficulty DOUBLE PRECISION NOT NULL DEFAULT 0,
    lastnetworkblocktime TIMESTAMPTZ NULL,
    blockheight BIGINT NOT NULL DEFAULT 0,
    connectedpeers INT NOT NULL DEFAULT 0,
    created TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS minerstats (
    id BIGSERIAL PRIMARY KEY,
    poolid TEXT NOT NULL,
    miner TEXT NOT NULL,
    worker TEXT NOT NULL,
    hashrate DOUBLE PRECISION NOT NULL DEFAULT 0,
    sharespersecond DOUBLE PRECISION NOT NULL DEFAULT 0,
    created TIMESTAMPTZ NOT NULL
);
