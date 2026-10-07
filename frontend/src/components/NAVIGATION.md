# PAS navigation

The October 2026 navigation update combines a sliding current-page highlight with
a keyboard command palette. It keeps the existing five sidebar groups, page
destinations and pink-gray / blue-gray palette.

- Click **Find a page**, or press **⌘ K / Ctrl K** from the main UI or embedded
  research workspace. Search English page names/descriptions or Chinese aliases
  such as `机构`, `项目` and `论文`.
- Use **↑ / ↓**, **Enter** and **Esc**. Closing restores focus; navigating moves
  focus to the main content. A native dialog contains keyboard focus.
- The active highlight follows the label width with a 280 ms transition. Reduced
  motion disables the highlight transition and dialog entrance animation.
- Mobile retains the existing icon rail and expandable menu, with a search icon
  and a responsive palette.

`navigation.ts` is the shared sidebar/search directory. `access` describes a
destination; it does not grant access. Existing page gates and backend authorization
remain authoritative. Restricted destinations retain an administrator hint;
**Manage access** appears only for administrators. Search runs locally over page
metadata and never searches personal notes, conversations or project contents.
The embedded shortcut message is accepted only from the known research iframe
and the same origin. Other open dialogs keep their keyboard interaction.

Validation for this release:

- Main and reading production builds; `npm run check:navigation` and
  `npm run check:paper-view` passed. The preservation check covers 29 original
  page components and existing routing/protected asset rules.
- Local synthetic member/admin browser checks covered search, keyboard selection,
  focus restoration/containment, the iframe shortcut, unique active links,
  administrator gating, and a 390 × 844 mobile viewport. Reduced-motion emulation
  confirmed the dialog animation is disabled.
- Published frontend assets were compared by SHA-256 over HTTPS; CloudFront
  invalidation completed. Live browser checks covered search, restricted-page
  gating and a populated Papers table. Public catalogue/Wiki endpoints returned
  200; sampled private/admin endpoints and the protected institution report
  returned 401 without a session.
- Backend services stayed on revisions 16 and 10; no backend release was needed.

Evidence: `tools/author-paper-monitor/review-evidence/navigation-verification.json`.
Authenticated browser scenarios use local fixtures; this release does not claim
an authenticated production regression run of every analytics page.
