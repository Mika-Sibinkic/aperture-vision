# Changelog — Aperture

> State: stable · Optionality: low · Open to Change: append-only. Format: [Keep a Changelog](https://keepachangelog.com). Entries before 2026-06-10 reconstructed during Git migration from checkpoint logs, file timestamps, Pocket recordings, and Notion records.

## [Unreleased]
- Cul2vate Mac→Dell bridge migration (Phases 2–5; paused since 2026-04-18, awaiting the client contact's camera serial + Farmbrite creds and a Dell RustDesk session)
- Farmbrite write path (gated on API key; workflow guard-skips to "Farmbrite skipped (pending key)")
- EnterpriseCo conveyor mode: sub-300 ms re-architecture (Jetson Orin Nano + Basler GigE + barcode trigger) pending pilot agreement
- Kitchen-test capture set for accuracy report (KITCHEN-TEST-INSTRUCTIONS.md; only IMG_0739 so far)

## 2026-05-07 — EnterpriseCo meeting package
### Added
- Static-mode demo: deterministic OpenCV ChArUco pipeline, harness, stub + OpenAI providers (`demo/`)
- Deploy containers: Dockerfile.bridge, Dockerfile.demo, compose, QUICKSTART (`deploy/`)
- EnterpriseCo conveyor architecture brief (`docs/EnterpriseCo-conveyor-architecture.md`)
- Auto-detected deployed board params: DICT_6X6_50, 8×10, 4.0" squares (legacy generator did NOT match)
### Context
Thu 8 AM Teams with the prospect contact; posture: static demo, conveyor pivot, paid pilot.

## 2026-04-20 — README architecture + resume guide

## 2026-04-18 — Dell migration prep
### Added
- DELL-SESSION.md runbook (Phases 2+3), the client contact outreach (serial + Farmbrite ask), Hik-Connect account
### Changed
- Mac bridge intentionally killed (Mac off Cul2vate LAN); n8n snapshot URL points at dead quick-tunnel until Phase 4

## 2026-04-17 — Live Cul2vate demo ✅
### Added
- Demo-proven end-to-end: iPad PWA → Vercel relay → n8n (16 nodes) → Google Sheet; light theme (cream + soft sage)
### Facts
- Camera: Hikvision AcuSense <device-serial>, manual focus, zoom locked; ChArUco board 36×44" Dibond on brick

## 2026-04-16 — Initial Aperture build
### Added
- Next.js 16 PWA (big-button UI), Vercel serverless relay with shared-token auth, n8n Cloud workflow, Mac camera bridge (socat IPv6 + cloudflared), ChArUco-calibrated vision prompts, scripts/check-state.sh

## Pre-history (Branch Cam era, ~Dec 2025–Feb 2026)
- n8n + OpenAI vision prototype at The Branch food bank (Antioch): Azure web app, Cosmos DB, anomaly-detection and ChArUco roadmap (see Notion "Branch Cam" page and `docs/history/ORIGINS.md`)
- Origin: scale bottleneck at The Branch via a contact at The Branch; 92–95% production accuracy, 98% test ceiling
