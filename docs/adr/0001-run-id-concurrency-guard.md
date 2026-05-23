# Session concurrency guard uses run_id, not status callback

The factory graph no longer calls a best-effort HTTP callback to update session status. Instead, the `send_events` route stores the active `run_id` on the session row. The factory graph's `finally` block is removed entirely. Session status becomes purely informational (UI badges), not a locking mechanism. A periodic reconciliation job checks Aegra run states for stale run_id values and clears them.

We made this change because the status callback was best-effort and unreliable: network blips, Aegra worker crashes, and missing reconciliation all left sessions stuck in "running" forever, blocking new events with HTTP 409. run_id is the actual source of truth for whether a run is active.
