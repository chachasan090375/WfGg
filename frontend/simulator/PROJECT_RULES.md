# Simulator project rules

## Preview-only visual workflow

For all simulator UI/UX work:

- Do **not** generate or deliver separate visual mockups, image previews, or design-only renders.
- Implement every requested visual/UX change directly in code on the `simulator-standalone-v1` branch.
- Validate changes on the Cloudflare preview for that branch.
- Share the deployed preview URL for review.
- Do not merge simulator UI changes to `main`, add portal links, or touch production until explicit final validation.

This rule is project-level and should be treated as persistent guidance for future simulator work.
