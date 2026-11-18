# Ponytail project skill

Added 2026-11-18 from [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) commit `96608e078b2d5ea607c5c3b8b5a54d1c1fba6846`. The exact upstream `skills/ponytail/SKILL.md` and MIT license are stored in `.agents/skills/ponytail/`. Claude Code's project skill path `.claude/skills/ponytail` points to that same directory.

Codex discovers repository skills under `.agents/skills`. Claude Code discovers them under `.claude/skills`. This integration supplies the skill text to those hosts. Canopy's `AGENTS.md` and master development mandate take precedence, including their testing and safety requirements. Plugin lifecycle hooks and mode persistence are outside this project skill.

Validation on 2026-11-18 checked the copied files against upstream blobs, resolved the Claude Code symlink, and ran the existing Python test suite. A fresh Codex CLI 0.167.0-alpha.4 `codex debug prompt-input` attempt stopped with `Read-only file system (os error 30)` before it could enumerate project skills. Claude Code was unavailable in this workspace. Fresh-session discovery remains unverified in both hosts.
