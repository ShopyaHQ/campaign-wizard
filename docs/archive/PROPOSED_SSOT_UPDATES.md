# PROPOSED SSOT UPDATES — recorded for owner review, NOT applied (autonomous run 2026-08-07)
1. Channel-failure vs thesis-failure: when a collection concept cannot reach depth because
   sourcing CHANNELS failed (blocked endpoints) rather than because inventory doesn't exist,
   the concept is 'sourcing-blocked', not 'failed' — alternates are promoted provisionally
   with the original preserved. (Demonstrated: H1 blankets -> H5 promoted, H1 preserved.)
2. Root /products.json returns newest-first (drops, bundles, pre-releases) — hero staples
   require collection-handle endpoints. Belongs in the engine fetch config as method guidance.
   (Demonstrated: Kosas/Merit/Béis/Fellow all surfaced sets/pre-releases, not heroes.)
3. Proposed-build mode: builds produced without owner approval carry status PROPOSED in the
   manifest, hard QA converted to labeled warnings, and are never import-ready. (Demonstrated: b004.)
4. Single-brand pin concentration cap (like PS-4 but per collection source): 9/9 East Fork
   pins is a concentration risk — propose a soft cap pending owner view.
