# Rotation rounds v2

Scope confirmed on 2026-08-25:

- Train remains the sole source of truth for schedule generation.
- The 14-day manual editing window belongs only to the Train application.
- Portal home/profile only reads Train schedule/statistics; it never generates a schedule.
- R4/R5 Portal Settings > Player statistics gets a dedicated per-player rotations subsection.
- Lifetime history remains visible for statistics but must not bias fairness inside a new rotation round.
- Current-round fairness is tracked separately per applicable role and resets when the eligible round is complete.

Implementation stays on test branches until QA passes.
