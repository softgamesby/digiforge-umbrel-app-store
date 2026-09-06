# DigiForge Umbrel App Store

DigiForge is a custom umbrelOS community app for a private DigiByte SHA256 mining pool.

Repository: https://github.com/softgamesby/digiforge-umbrel-app-store

## Current release

**DigiForge 1.0.1** fixes the web-container startup failure found during real installation testing on umbrelOS. The default Miningcore configuration is now read from `/data/config.default.json` through the existing app config mount, avoiding the nested read-only bind mount that prevented `web_1` from starting in 1.0.0.

## Install

Add this repository to **Umbrel → App Store → Community App Stores**:

`https://github.com/softgamesby/digiforge-umbrel-app-store`

Then install **DigiForge**.

## DigiForge-owned code

- responsive DigiForge dashboard
- original DigiForge icon
- first-run DGB address setup
- Python dashboard/backend
- Miningcore configuration generator
- automatic Miningcore configuration reload helper
- Umbrel app packaging and networking

## Runtime dependencies

DigiForge uses but does not claim ownership of DigiByte Core, Miningcore, PostgreSQL, and the Python runtime image.

## Bitaxe 601

After the node is synchronized:

- Pool: `stratum+tcp://YOUR-UMBREL-IP:3256`
- User: `YOUR_DGB_ADDRESS.bitaxe601`
- Password: `x`

Automatic payouts are disabled.
