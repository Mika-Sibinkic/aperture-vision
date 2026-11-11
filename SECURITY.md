# Security

## Report a problem

Email TODO-MIKA-SECURITY-CONTACT. Do not open a public issue for a vulnerability.

## What is secret

- The relay URL. Until the device token is set, anyone who has it can log, export and void donations.
- `APERTURE_DEVICE_TOKEN` (iPad → relay) and `APERTURE_SHARED_TOKEN` (relay → n8n).
- The generated iPad build, `camera-access/ipad/Aperture.local.js`. It holds the camera admin password in plain text. It is gitignored. Move it by AirDrop or iCloud Drive only.
- API keys (NVIDIA NIM, Farmbrite, Vercel Blob) live in Vercel env and n8n credentials, never in this repo. `/api/void` needs `FARMBRITE_API_KEY` to delete an order on undo.

## The device-token check is open until you set it

Every `/api/*` route checks the `x-aperture-token` header against `APERTURE_DEVICE_TOKEN`. While that variable is unset, the routes accept any caller and log a warning. This keeps the live iPad working until it gets a build that sends the token. Set the variable in Vercel as soon as your iPad build sends it. The legacy PWA in `app/` sends no token, so it stops working once the variable is set.

## Known advisory left in place

`npm audit` reports one high-severity chain: `zod` below 4.6.6 (GHSA-mrhx-c7xc-m3w5), pulled in by `@vercel/blob` → `@vercel/oidc` → `@vercel/cli-config`. The only fix npm offers downgrades `@vercel/blob` to 2.4.0, which is a breaking change. In that chain, zod parses the local Vercel CLI auth file during an OIDC token refresh. No request data reaches it, so the advisory stays until Vercel ships a fixed release.
