# Video script

About 90 seconds. Recording is manual. This file is the narration, not a recording.

---

This is Evalflow, a synthetic prototype. It is not a Nuro system and not a real autonomy stack.

Each scenario depends on a subset of model components. The cache key is a sha256 of the evaluator version, a fingerprint of the scenario, and hashes of only the components that scenario lists. An unrelated edit does not change the key.

The suite is two hundred committed scenarios. Version one uses a conservative planner. The first run fills an empty cache. Every scenario is a miss, and the JSONL header records wall clock, hits, and misses.

Version two lowers planner conservatism and changes nothing else. The second run recomputes the seventy scenarios that depend on the planner. The other one hundred thirty, perception only and prediction only, are cache hits. Their metrics match the first run.

Compare joins the two run files on scenario id. A pass that flips from true to false is a regression. Minimum distance that falls by more than the tolerance, or jerk that rises by more than the tolerance, is a regression too. If one metric improves and another regresses, the scenario still counts as a regression.

The report is one static HTML page: a banner, counts by category, the top regressions with pass flips first, and the runtime from both headers. The footer says the evaluator is synthetic.

That is the demo. Change the planner, recompute only what depends on it, and hand an engineer a single page.
