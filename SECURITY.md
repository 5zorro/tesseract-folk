# Security policy

Tesseract Folk is a hobby prototype, but it is meant to become a game mod that
other people install, so security reports are welcome.

**To report a vulnerability,** use GitHub's private reporting: the repository's
**Security** tab → **Report a vulnerability**. Please don't open a public issue
for anything that could hurt players before it's fixed.

Worth reporting, for example:
- a crafted snapshot file that crashes, hangs, or runs code when loaded
- any way an NPC, a snapshot, or an AI-model reply could reach files, the network,
  or the operating system
- an API key ending up anywhere it could be shared

The threat model and the project's safety rules are in
[docs/SAFETY.md](docs/SAFETY.md).
