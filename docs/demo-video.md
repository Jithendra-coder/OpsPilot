# OpsPilot demo video

## Story

**Find the cause. Keep control.** The introduction page at `/` contains an 85-second narrated, captioned product walkthrough; `/demo.webm` serves the same local video directly. It follows seeded scenario `SCN-001`, **Peak traffic alert · Checkout API**, from evidence to independent approval and verified recovery. All observations are synthetic, and actions affect only the local simulator.

## Setup

1. Start OpsPilot with distinct operator and approver credentials of at least 16 characters. Configure both before recording when possible; if the app generates them, read them from the private setup terminal off-camera. Do not restart during the take because generated credentials rotate on startup.
2. Open the introduction at `http://127.0.0.1:8765`, then choose **Get started** to enter the console at `/console`.
3. For a clean take, point `OPSPILOT_DATA_DIR` at a new empty directory. Keep existing incident history intact; do not delete the current data directory to prepare the video.
4. Frame the browser at 1440 × 900 or larger, zoom at 100%, hide unrelated windows, and record the full app window. Keep passwords and terminal output out of the recording.

## 85-second walkthrough

| Time | Screen/action | Narration |
| --- | --- | --- |
| 0:00–0:07 | Open on OpsPilot and the product promise. | “OpsPilot turns an alert into a structured investigation, with people still in control of change.” |
| 0:08–0:17 | Identify the seeded Checkout API replay and synthetic-data boundary. | “This Checkout API case is a seeded local replay. The evidence is synthetic, not production telemetry.” |
| 0:17–0:26 | Correlate the incident-scoped signal sources. | “The investigator reads only evidence scoped to this incident: logs, metrics, traces, and deployment changes.” |
| 0:26–0:36 | Show the two measured symptom values. | “All thirty-two database pool connections are occupied. Checkout waits 1.84 seconds before acquisition fails.” |
| 0:36–0:46 | Show evidence-linked leading and competing causes. | “The database pool is the supported cause. Evidence is linked, while competing explanations remain visible.” |
| 0:46–0:59 | Show the bounded typed action and separate approval gate. | “OpsPilot proposes one typed, allowlisted action: restore the seeded pool baseline to sixty-four connections. The investigator cannot write, approve, or execute it.” |
| 1:00–1:08 | Show the distinct approver and operator roles. | “A different approver reviews the exact parameters. Then the operator runs it once, only in the simulator.” |
| 1:08–1:17 | Finish on server-owned recovery checks and the retained incident record. | “Server-owned checks decide if the incident resolves. The approval and verification remain in the incident record.” |
| 1:17–1:25 | Product name and the local/synthetic boundary. | “Evidence first. Action under human control. OpsPilot.” |

## Recording notes

- The shipped video uses custom motion graphics to explain the real workflow; it is not a screen recording of an authenticated user session.
- Keep captions enabled. `/demo-captions.vtt` is also served as a standalone English caption track.
- Keep pauses short but allow the audience to read the evidence values and action parameters.
- Use captions for “read-only investigation”, “independent approval”, and “simulator-only execution”.
- Do not claim the optional LLM is enabled unless the recording environment explicitly configures it and the UI identifies its role accurately.
- Do not describe the seeded observations as live logs, live Prometheus metrics, or distributed traces from running microservices.
- The benchmark currently contains 28 labelled cases and 8 intentionally inconclusive cases. Report labelled accuracy separately from appropriate abstentions.

## Reset for another take

Use the Replay Lab to start a new scenario after the prior run reaches a terminal status. The console preserves the previous incident and audit history; avoid deleting database files to reset a recording.
