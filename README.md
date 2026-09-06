<div align="center">

<img src="digiforge-dgb-pool/icon.svg" width="112" alt="DigiForge">

# DigiForge

### Self-hosted DigiByte SHA256 mining infrastructure for umbrelOS

**Private Pool · Local Infrastructure · Persistent Statistics · Modern Monitoring**

<br>

![Release](https://img.shields.io/badge/DigiForge-1.0.9-2f81f7?style=for-the-badge)
![DigiByte](https://img.shields.io/badge/DigiByte-DGB-0066cc?style=for-the-badge)
![Mining](https://img.shields.io/badge/Mining-SHA256-555555?style=for-the-badge)
![Umbrel](https://img.shields.io/badge/Platform-umbrelOS-7c3aed?style=for-the-badge)

</div>

---

## About DigiForge

DigiForge is a self-hosted DigiByte SHA256 mining hub built for umbrelOS.

It combines:

- a pruned DigiByte Core node
- a private Miningcore SHA256 pool
- PostgreSQL mining statistics and persistent accepted-share history
- worker-level monitoring
- a responsive DigiForge dashboard and setup interface
- dedicated Stratum support for Bitaxe/ASIC and NerdMiner devices

DigiByte RPC, PostgreSQL, and the Miningcore API remain private inside the DigiForge app network.

**Developed by Mikal.**

---

## Current Release

### DigiForge 1.0.9

DigiForge 1.0.9 is a maintenance and bug-fix release that updates official repository, support, icon, and container package references while preserving the verified immutable runtime image digests and existing mining configuration.

| Component | Status |
| --- | --- |
| DigiByte Node | Supported |
| SHA256 Mining Pool | Supported |
| Bitaxe / ASIC | Stratum port `3256` |
| NerdMiner V2 | Stratum port `3257` |
| PostgreSQL Statistics | Enabled |
| Automatic payouts | Disabled |
| Current Umbrel release | `1.0.9` |

---

## Install on Umbrel

Open **Umbrel → App Store → Community App Stores** and add:

```text
https://github.com/softgamesby/digiforge-umbrel-app-store
```

Then install **DigiForge** from the Community App Store.

---

## Mining Connections

Replace `YOUR-UMBREL-IP` and `YOUR_DGB_ADDRESS` with your own values.

### Bitaxe / SHA256 ASIC

```text
Pool:     stratum+tcp://YOUR-UMBREL-IP:3256
User:     YOUR_DGB_ADDRESS.BitaxePro
Password: x
```

### NerdMiner V2

```text
Pool:     stratum+tcp://YOUR-UMBREL-IP:3257
User:     YOUR_DGB_ADDRESS.nrd1
Password: x
```

Additional workers can use their own worker suffix, for example:

```text
YOUR_DGB_ADDRESS.nrd2
```

---

## DigiForge Features

| Feature | Description |
| --- | --- |
| Pool Hashrate | Six-hour accepted-work effective hashrate |
| Worker Monitoring | Individual worker hashrate, shares and activity state |
| Round Effort | Accepted mining work versus statistical expected work |
| Expected Block Time | Statistical estimate using effective pool hashrate |
| Network Share | Pool effective hashrate versus DigiByte SHA256 network |
| Block History | Displays blocks recorded by Miningcore |
| Persistent Data | PostgreSQL-backed mining statistics |
| Private Services | RPC, database and Miningcore API remain internal |

---

## Support DigiForge

<div align="center">

### ☕ Buy Mikal a Tea or Send a Gift

DigiForge is independently developed by **Mikal**.

If DigiForge has been useful to you and you would like to support continued development, you can send a voluntary gift using one of the public receiving addresses below.

</div>

| Network | Public Receiving Address | QR |
| --- | --- | :---: |
| **Bitcoin (BTC)** | `bc1qhaj04fx5rts85ypavgxwgvlg44jhgje7ymsq0u` | <img src="assets/support/btc.png" width="110" alt="Bitcoin support QR"> |
| **Ethereum (ETH)** | `0x0E9f6aeb5537Dcca347c0c858989dd10CDBBB7b2` | <img src="assets/support/eth.png" width="110" alt="Ethereum support QR"> |
| **Dogecoin (DOGE)** | `D7zbwfjWY1KzWgtBtsiuhbdcoGutFH8pkd` | <img src="assets/support/doge.png" width="110" alt="Dogecoin support QR"> |
| **Litecoin (LTC)** | `ltc1q67h4p7durruk8xkjz3yh6v3jrua5jxh9yy3s9q` | <img src="assets/support/ltc.png" width="110" alt="Litecoin support QR"> |
| **DigiByte (DGB)** | `dgb1qy4h02rhasx2f8q7whn4sanfsdhgajhek34dsv5` | <img src="assets/support/dgb.png" width="110" alt="DigiByte support QR"> |

> Support is entirely optional and does not provide additional features, mining advantages, or privileges.

---

## DigiForge-Owned Code

DigiForge-owned components include:

- responsive DigiForge dashboard
- DigiForge icon and branding
- first-run DigiByte address setup
- Python dashboard/backend
- Miningcore configuration generator
- automatic Miningcore configuration reload integration
- Umbrel app packaging and networking
- DigiForge monitoring and statistics integration

---

## Runtime Dependencies

DigiForge uses third-party open-source components and does not claim ownership of them, including:

- DigiByte Core
- Miningcore
- PostgreSQL
- Python runtime components

Their respective licenses and attribution remain applicable.

---

<div align="center">

**DigiForge · Developed by Mikal**

`DigiByte` · `SHA256` · `umbrelOS`

</div>
