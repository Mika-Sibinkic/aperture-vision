# Aperture — notes for AI assistants

Aperture is a donation-weighing camera system: an iPad tap pulls a frame from an IP
camera, a Vercel relay forwards it to an n8n workflow, a vision model returns structured
JSON with an estimated weight, and the result is logged to a Google Sheet and Farmbrite.

- Start with `README.md`, then `docs/OPERATIONS.md` for what is live.
- Vision prompt versions live in `prompts/weight-estimation.md`; each version records the
  failure it fixes. Do not remove the anti-parroting or empty-zone rules.
- Before committing, run the offline block in README's "Try it in a minute" (9 Python
  tests, 33 web tests). CI runs lines 2-4 of it plus `scripts/test_*.js`, not the demo.
- Never commit credentials. `.env*` files other than `.env.example` are gitignored.
