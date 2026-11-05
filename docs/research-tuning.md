# Research: tuning rules and similar projects (2026-11-04)

5zorro asked whether there's a "golden ratio" that makes tuning easier. There's no
single one, but several well-known results map onto our knobs. Each suggests a
*dimensionless ratio* to hold fixed when the world, the brain or the dimension
changes. None is tested here yet; each is a candidate for a plan slice.

## 1. Mutation: about one mutation per genome per birth (the 1/L rule)
- Classic genetic-algorithm guideline: per-gene mutation rate ≈ 1/L, where L is
  the genome length, so each child gets about one mutation. Traced to
  Bremermann (1966) and De Jong (1975); Mühlenbein (1992) showed it optimal for
  simple (unimodal) problems; Smith and Fogarty (1996) found it the best fixed
  setting. Limits (Ochoa 2002): scale it with selection pressure, and dynamic
  environments can favor more.
- **Ours:** `mutation_rate` 0.1 is a per-weight chance, so a birth mutates
  ~102 of 1,023 weights (2D, 16 hidden units), ~52 of 519 (8 hidden), ~138 of
  1,379 (4D, 16 hidden). That's **50–140× the rule**; 1/L would be 0.001–0.002.
- **Possible link to slice 3d:** bigger brains did worse at every dimension.
  At a fixed per-weight rate they also get more mutations per child, so
  "bigger is worse" may be "more mutations is worse". Testable: hold mutations
  per birth fixed (rate = k / n_weights) and redo the hidden-size sweep.
- Fits 5zorro's idea of lowering mutation over the nursery (openitems: Evolution),
  and his ancestor-lifespan idea is a form of self-adaptive mutation.

## 2. Mutation step size: the 1/5 success rule (or 1/e)
- Rechenberg's rule for evolution strategies: adjust the step size
  (`mutation_scale` here) so that about 1 in 5 mutations is an improvement;
  grow it when more succeed, shrink it when fewer do. For a discrete (1+1)
  evolutionary algorithm, Doerr et al. (2019) proved the optimal success ratio
  is e − 1 to 1, i.e. a 1/e success rate. (Not the 1/e map size 5zorro asked
  about, but a real 1/e in this problem.)
- **Ours:** we never measure how often a child beats its parent. Cheap to add
  (child lifetime or fitness vs parent's), then `mutation_scale` could follow it.

## 3. Dimension: random walks return in 1D and 2D, not in 3D+ (Pólya)
- Pólya's theorem (1921): a random walk on a grid returns to where it started
  with certainty in 1D and 2D, but in 3D and up it has a real chance of never
  coming back.
- **Ours:** in 2D, aimless wandering keeps bumping back into patches, so
  barely-steered brains survive and 2D-tuned numbers "work". In 3D/4D a
  wanderer that leaves a patch may never find it again: foraging has to be
  steered by senses. This matches slice 3e/3f (search times grow with
  dimension, 4D NPCs camp on crumbs).

## 4. Smell reach shrinks with dimension in our code (derived, not yet checked)
- Our scent spreads by mixing each cell with the mean of its 2 × dims
  neighbors. That's a discrete Laplacian divided by 2 × dims, so the effective
  diffusion per axis is `scent_diffusion / (2 * dims)`. With decay k, a smell
  reaches about λ = √(D / k) cells: **2.7 in 2D, 2.2 in 3D, 1.9 in 4D** (with
  0.3 and 0.01). Signals from a source also thin out faster with distance in
  higher dimensions (they spread over more directions).
- **Ratio to hold:** smell reach ÷ distance between patches. Scaling
  `scent_diffusion` by dims / 2 would keep λ fixed. Verify by measuring the
  scent profile around a lone patch in 2D–4D (the test in `tests/test_scent.py`
  is a template).

## 5. When to leave a patch: the marginal value theorem (Charnov 1976)
- A forager should leave a patch when its intake rate there drops to the
  average rate for the whole habitat (counting travel). Longer travel means
  staying longer and accepting poorer pickings.
- **Ours:** nibbling crumbs instead of walking to a meal is what the theorem
  predicts when travel looks long or uncertain (4D, slice 3f). For "skip the
  crumb" to pay, a rich patch's intake rate must beat the crumb rate by more
  than the trip costs. Ratio to hold: (meal intake rate − crumb intake rate) ×
  trip time vs. the hunger clock. 5zorro's two eat actions and the meal scent both
  change the meal side of that ratio.

## 6. Search for sparse targets: Lévy flights (contested)
- Viswanathan et al. (1999): when targets are sparse and revisitable, mixing
  many short steps with rare long straight runs (step lengths ~ 1/length²)
  beats a plain random walk. Later work disputes how general this is,
  especially in 2D and up (Palyulin et al. 2014; a 2020 Physical Review Letters
  paper titled "Inverse Square Lévy Walks are not Optimal Search Strategies
  for d≥2").
- **Ours:** informational. If 3D/4D brains evolve "run straight for a while"
  behavior, that's this. Brains can't do it without memory of a heading; the
  memory stack (slice 4a) or recurrent units would allow it.

## Similar projects
- **Polyworld** (Larry Yaeger, 1990s–2010s): agents with vision and
  neural-network brains (Hebbian learning) evolving in an ecology; foraging,
  flocking and attack avoidance emerged; evolution shapes the wiring. The
  closest research ancestor of this project.
- **The Bibites** (indie game, itch.io): evolving creatures with neural-network
  brains, pheromone production and sensing, and visualized brains. The closest
  game-side relative; worth playing to see how they tune food and pheromones.
- **Creatures** (1996): already the inspiration (`docs/DESIGN.md`).
- **EvoJAX** (Google Brain, 2022): neuroevolution with the network, the
  algorithm *and the task* written as array code compiled for GPUs/TPUs; tasks
  that took hours on CPU solve in minutes. It's the model for the batched,
  many-worlds-at-once rewrite in `openitems.md` (Speed). JAX itself doesn't run
  on AMD GPUs under Windows, so the backend would differ.

## Candidate slices from this (for 5zorro)
1. **Mutation per genome:** set the rate from the brain size (≈ 1–3 mutations
   per birth), then redo the hidden-size sweep. Cheap, and it may change the
   brain-size conclusion.
2. **Smell reach per dimension:** measure λ in 2D–4D, then scale
   `scent_diffusion` with dims and rerun the travel-time worlds.
3. **Success-rate logging** for the 1/5 (or 1/e) rule.

## Sources
- Ochoa, "Setting the mutation rate: scope and limitations of the 1/L heuristic" (GECCO 2002): https://www.cs.stir.ac.uk/~goc/papers/SettingMutRateGECCO02.pdf
- Doerr et al., "Self-adjusting mutation rates with provably optimal success rules" (arXiv 1902.02588): https://arxiv.org/pdf/1902.02588
- Rechenberg's (1+1)-ES with the 1/5 rule (PyPop7 docs): https://pypop.readthedocs.io/en/latest/es/res.html
- Pólya's random walk theorem (ar5iv 1301.3916): https://ar5iv.arxiv.org/html/1301.3916
- Marginal value theorem: https://en.wikipedia.org/wiki/Marginal_value_theorem
- Lévy flight foraging hypothesis: https://en.wikipedia.org/wiki/L%C3%A9vy_flight_foraging_hypothesis ; Palyulin, Chechkin & Metzler (PNAS 2014): https://www.agnld.uni-potsdam.de/papers/2014_PalCheMe_PNAS111.pdf
- Yaeger et al. 2010, Polyworld network evolution: https://www.shinyverse.org/larryy/YaegerEtAl2010_EvolutionarySelectionOfNetworkStructureAndFunction_ALife12.pdf
- The Bibites: https://thebibites.itch.io/the-bibites
- EvoJAX (arXiv 2202.05008): https://arxiv.org/abs/2202.05008v1
