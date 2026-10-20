# Snapshot-Laya: live controls

Goal: identify the interface currently rendered by Pragmatic demo games, classify
its controls with local Laya/DirectML, and record verified transitions before
closing each owned game and moving to the next.

Architecture: local FastAPI dashboard -> HardFire MCP on loopback -> isolated demo
session. Read runtime drawn controls (including base bet controls), filter noise,
retain hit rectangles and crop references, then send only semantic metadata to
Laya. Model output proposes a role; it never proves a click or exhaustive coverage.

Implementation plan (writing-plans; executed inline):
- [x] Tests first: filtering, out-of-bounds, hidden/disabled/duplicates and overlays.
- [x] Strict evidence validation: pending controls, interrupted bonus or missing
  protocol evidence must prevent a validated completion.
- [x] Loopback MCP client, persistent configurable ONNX engine, live session manager.
- [x] Dashboard: current screenshot, classifications, explicit current actions,
  live refresh, observed-scope validation, close-incomplete, sequential game queue.
- [x] Unit tests and live Sweet Bonanza/Gates of Olympus 1000 demo observations.
- [x] Review, sanitized evidence report, commit and push to requested repository.

Constraints: preserve upstream observation tokens; no action retry; only official
demo launch URLs; only close owned sessions; do not expose session credentials.
Occlusion NOT_VERIFIED remains explicit. Operator visual review is required to
execute a control; Laya confidence is not calibrated for these games.

Ruling: completion means validated coverage of observed controls and visited states,
never proof that undiscovered or hidden game states do not exist. Auto-close is
opt-in and can happen only when this evidence gate passes.

Validation: 28 unit tests, live Sweet Bonanza purchase protocol and Gates of Olympus 1000 observation. No exhaustive search validation was claimed. Live artifacts are excluded from Git; only the sanitized summary is committed.
