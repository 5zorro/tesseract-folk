# Research: tuning rules and similar projects (2026-11-04)

5zorro asked whether there's a "golden ratio" that makes tuning easier. There's no
single one, but several well-known results map onto our knobs. Each suggests a
*dimensionless ratio* to hold fixed when the world, the brain or the dimension
changes. None is tested here yet; each is a candidate for a plan slice.

## 1. Mutation: about one mutation per genome per birth (the 1/L rule; measured: loses here)
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

**For real-valued brains like ours (added 2026-11-04).** The 1/L rule comes
from bit-string genomes. Neural-network evolution follows the same idea in a
different form: keep the *total change per child* small and about the same
whatever the genome size.
- Evolution strategies theory: the best step per weight shrinks as 1/n with the
  number of weights n, and the 1/5 rule (§2) tunes it (Beyer; Jägersküpper).
- Deep neuroevolution (Such et al. 2017, Uber): a plain genetic algorithm
  evolved ~4 million weights by adding tiny noise to *every* weight
  (σ ≈ 0.002–0.005), with no crossover.
- NEAT (Stanley and Miikkulainen 2002/2004): 80% of children get their weights
  perturbed; crossover lines genes up by "historical markings" so unrelated
  parents aren't mixed blindly.

**Ours, measured on the ladder nurseries:** an evolved brain's weights are
~0.3 in size (root mean square), and each mutated weight gets noise of 0.3, so
one mutation roughly rewrites a weight. With ~52–102 of them per child, a
child lands **31–35% of the brain's own length** away from its parent (one
mutation: 3–4%). In the nursery nearly every newcomer is a mutated copy of a
hall-of-fame brain (2D: 7 births vs 99 copies in 4,000 ticks; 3D: 0 vs 155),
so mutation is the nursery's only source of variation.

**Measured 2026-11-04 (plan-m2 slice R1):** in our nursery the textbook rule
*loses*. 1 or 3 mutated weights per child gave clearly worse 3D nurseries
(collapses up 60-100%, food types per life down ~20%); 10, 30 and today's
52-102 sit on a plateau within noise. Likely because the nursery is short and
noisy (one life per evaluation), so tiny changes are invisible to selection.
With mutations per child held equal, 16 hidden units were no longer worse
than 8, so the slice 3d "bigger is worse" result was at least partly a
mutation-count effect. Proposed default: 30 per child.

**Measured further (slices R3, R4):** a chosen parent's single-life score is
mostly luck (its near-clones are barely better than average; parent-child
correlation 0.06-0.26), so Rechenberg's success rule can't be applied as-is.
Mutating costs a child little up to ~20 weights, then more. 5zorro's
lineage-adaptive rule (base 30, x1/4 to x4 by the ancestors' collapse rate
relative to the population's) beat a fixed 30 in 3D in 6 of 6 nursery pairs;
base 10 lost to both. It resembles CLONALG's fitness-scaled hypermutation.

**Crossover (the permutation problem).** Mixing two unrelated networks weight
by weight tends to break both: the same job can sit in different hidden units
(Radcliffe 1993; Schaffer et al. 1992 called it "competing conventions"; the reason NEAT has historical markings and Such et al.
skip crossover). Ours is uniform crossover between whoever mates. In the
nurseries, a child of two random NPCs lands 75–83% of a brain's length from
either parent. Births are rare in nurseries, so this matters for play worlds
(where 2D has ~90 births per run), not for training.

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

## 4. Smell reach shrinks with dimension in our code (measured: harmless)
- Our scent spreads by mixing each cell with the mean of its 2 × dims
  neighbors. That's a discrete Laplacian divided by 2 × dims, so the effective
  diffusion per axis is `scent_diffusion / (2 * dims)`. With decay k, a smell
  reaches about λ = √(D / k) cells: **2.7 in 2D, 2.2 in 3D, 1.9 in 4D** (with
  0.3 and 0.01). Signals from a source also thin out faster with distance in
  higher dimensions (they spread over more directions).
- **Measured 2026-11-04** (`scripts/probe_scent.py`, plan-m2 slice R2): the
  lengths hold (2.74 / 2.24 / 1.95), but it doesn't matter. NPCs sense the
  scent difference between neighbors *relative to its sum*, so a faint smell
  points as well as a strong one: stepping toward the strongest smell gets
  closer to that food 92–100% of the time in 2D, 3D and 4D, even 6+ cells away.
  Scaling `scent_diffusion` by dims / 2 changed nothing. Reach becomes a ratio
  to hold only if senses get noise or a detection threshold.

## 4b. Random-walk search time vs dimension (measured 2026-11-05, plan-m2 R6)
- On a grid of N cells, a random walk needs about N^2 steps to find a target in
  1D, N log N in 2D, and N / (target size) in 3D and up (Pólya's transience:
  above 2D, time follows volume). At a fixed width, volume grows as
  width^dims, so search time is exponential in dims with base ~0.7 x width /
  target radius (measured 3.5x at width 10, 4.8x at width 14). There's no
  universal base like 2 or e.
- **Ratio to hold:** walk time to the needed food / hunger clock. Our
  travel-time worlds keep it near 2D's in 3D (97% vs 98% in time), less so in
  4D (84%).

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

## Relationships we measured (laws and hints, with evidence)
5zorro's standing priority: relationships and formulas over single results.
"Law" = repeated across dimensions or runs; "hint" = one run or noisy; the
plan section holds the table and the command. CSVs aren't published (`runs/` is
gitignored). The plan tables are the record; to check one, rerun its script.

| Relationship | Status | Evidence |
|---|---|---|
| Search time per extra dimension grows ~0.7 x width / target size | law | plan-m2 R6; section 4b above |
| Ticks for a nursery to reach its knee ~ weights^0.5 (same in 2D and 3D) | law (2 dims, 5 sizes; single points noisy) | plan-m2 R7 "Brain size vs ideal training length"; `long_nursery.py --arms h4..h64` |
| 4D nurseries peak at 50-200k ticks, then decay (16, 32, 64 units; mean of 10 nurseries +0.25 collapses by 350k, ~4 se); a single nursery wanders +-0.3 | law for 4D (3 sizes, 10 seeds) | plan-m2 R7 "4D, 700,000-tick baseline", R10 test 3; `long_nursery.py --nursery-seeds` |
| The decay isn't the nursery rules: checkpoints decay the same under nursery and play rules | finding | plan-m2 R10 test 1; `probe_decay.py rules` |
| Freezing the hall of fame holds the 4D peak (2.1 vs 2.4) but stops evolution | finding | plan-m2 R10 test 2; `probe_decay.py freeze` |
| Squared weight norm = start + mutations/child x scale^2 x generations (neutral drift; 4D r = 1.000 at 3 sizes) | law in 4D; 2D grows at ~half that, 3D near it (hint: harder world, more neutral drift) | plan-m2 R10; `probe_decay.py hof` |
| The hall of fame turns over completely between 4D checkpoints (1.1 lives per entry) | finding | plan-m2 R10 |
| The last fertile hunger falls ~0.6x per dimension (interpolated: 2D 1.0-1.2x, 3D 0.6x, 4D 0.35-0.4x); today's 1x is past it in 3D and 4D | hint (2 seeds) | plan-m2 R11; `scripts/hunger_ladder.py` |
| **Hunger distance:** births stop when the median random walk from one food to another costs ~0.14 of a hunger clock (0.12-0.16 in 2D-4D, both arms), while the fertile hunger itself varies 3x; mate reach doesn't fit (7-15) | hint (3 dims, 2 seeds, scratch brains, a random walker) | plan-m2 R11 "Hunger distance"; `hunger_ladder.py`, `probe_random_walk.py` |
| 4D births are density-limited (30 NPCs in 10,000 cells even at 0.25x hunger) | finding | plan-m2 R11, R9 |
| At equal hunger distance, fertility lines up across dimensions but collapse pressure falls with dimension (scratch 2D 1.5, 3D 0.4, 4D 0.2 at 0.14 clocks) | hint (3 seeds) | plan-m2 R12; `sweep.py` |
| Travel is required in the travel-time worlds: a never-moving NPC collapses 3-15x more than a random wanderer and eats 0.1-0.5 food types per life in 3D/4D | finding | plan-m2 R12; `sweep.py --variant controller=still` |
| Diet diversity needs hunger: lowering hunger to the fertile edge lowers it (3D 0.93 -> 0.85, 4D 0.81 -> 0.75) | hint (2 nurseries x 5 seeds) | plan-m2 R12; `ladder.py --set` |
| 3D diet diversity falls ~0.04 per 0.1x of hunger below 1x (0.93, 0.89, 0.85 at 1x, 0.85x, 0.75x) | hint (3 levels, 2 nurseries x 5 seeds each) | plan-m2 R12 |
| Populations are bistable (Allee effect): 3D worlds at 0.85x either boom to the 250 cap or stay at the 30 floor, none in between | hint (10 worlds) | plan-m2 R12; follows from mate reach ~ N |
| 3D births switch on sharply as hunger drops: ~1x top-ups at 0.95x, ~11x at 0.9x; every M2 goal still met at 0.9x | finding (2 nurseries x 5 seeds per level) | plan-m2 R12; `scripts/hunger_search.py` |
| Hall-of-fame trials lose in 4D at 0.36x hunger: food types 1.75-1.80 vs 2.03 (every trial nursery below every base one), collapses 2x | finding (4 nurseries x 5 seeds per arm, 20k ticks) | plan-m2 R13 |
| Trials halve a nursery's generations at a fixed tick budget (clones take most top-ups) | finding | plan-m2 R13 |
| At 0.36x hunger 4D nurseries barely collapse (0-0.06 per 1,000 ticks, nursery rules): collapse-based merit has no signal there | finding | plan-m2 R13 |
| 4D births are blocked by nutrient pressure, not body burn: with nutrient decay at 1x, births stay ~0 (2-6 vs ~285 top-ups) at body burn 0.25-1x | finding (2 nurseries x 5 seeds per level) | plan-m2 R13; `hunger_search.py --keys metabolism_rate` |
| 4D at 0.36x: training levels off, it doesn't improve to the last tick. Types -> ~2.65 with tau ~93k (plain) or ~165k (arena), 95% there by ~280k / ~490k; same ceiling either way | finding (4 nurseries x 3 seeds, 7 scored rounds to 700k) | plan-m2 R14; `arena.py --start-round 5 --rounds 35` |
| 4D diet tops out at ~0.80-0.86 at 0.36x whatever the training length (goal 0.9) | finding | plan-m2 R14 |
| Brain quality differences in a hall of fame shrink ~100x in the first ~100k ticks (variance 6 -> 0.05) while luck shrinks ~10x: luck's share of one score rises from ~20% to 50-80% | hint (one dimension, 4 nurseries) | plan-m2 R14; `arena.py --measure` |
| After ~60k ticks one untested life is 15-45% quality: 0.8 reliability needs ~5-20 lives alone, or ~2-6 shared scenarios (common random numbers cut the tests 2-4x) | hint | plan-m2 R14 (Spearman-Brown) |
| A hall of fame's own merit ranks brains no better than chance against a shared-scenario race (rank corr. ~0, top-half agreement 42-57%) | finding (every measured round, 1-35) | plan-m2 R14 |
| Race verdicts written into the hall of fame don't last a 20k round: ~1% of kept entries survive to the next race (though the survivors are better); the 5-copies floor drops most of them on luck | finding | plan-m2 R14; `race.json` |
| Taking luck out of selection (races whose picks persist) doesn't raise 4D's food-types ceiling (~2.6-2.65 in all arms); it raises late diet ~0.05 (0.85 vs 0.80), still below 0.9 | finding (4 nurseries per arm, to 700k) | plan-m2 R14 persist arm |
| With persistent champions, the next race's newcomers (mostly their mutated copies) are as good as the champions: the population converges on them | finding | plan-m2 R14 persist arm |
| Hunger isn't 4D's M2 lever: food types 1.96 at 1x, 2.11 at 0.36x (goal 2.5) | finding | plan-m2 R12 |
| Diagonal (king) steps cut the food-to-food walk 1.4x / 1.75x / 1.9x in 2D / 3D / 4D (theory for an open grid: 2d/3) | finding (random walker) | plan-m2 R12; `probe_random_walk.py --diagonal` |
| The kids rules (birth weight + child credit) raise births only where births are possible: 2D 12x at 1.25x hunger, 4D 5x at 0.25x; the finish line moves at most one step | hint (2 seeds) | plan-m2 R11 |
| At 0.25x hunger 4D lives are nearly collapse-free (~0.01 per 1,000 ticks) and, with the kids rules, births are most of the replacements (9-12 vs 4-7 top-ups) | finding (scratch brains, 2 seeds) | plan-m2 R11 |
| Stink only matters in crowded 2D: 17-53% of 2D collapses (65-69% for NPCs that never move), 0-2% in 3D/4D | finding (no law yet: candidate reach ~ sqrt(diffusion / decay) ~ 2.4 cells, mean stink ~ NPCs per cell x poop rate / decay; unmeasured) | plan-m2 R12 sanity logs; `runs/hunger-sanity-*.log` |
| Ideal or equilibrium population density | open: no law. Seen: at 0.25x hunger 2D grows to ~0.19 NPCs/cell, 3D hits the 250 cap, 4D stays at the 30 floor (0.003/cell); population x hunger isn't constant | plan-m2 R11, R12 |
| Collapses rise linearly with hunger past the fertile range: ~3.4 per 1x in 2D/3D, ~4.6 in 4D | hint | plan-m2 R11 |
| In 4D, body starvation's share of collapses rises with hunger (19% at 1x, 80% at 6x); 2D/3D stay nutrient starvation | finding | plan-m2 R11 |
| Gives fall ~30x from 0.25x to 1x hunger in 2D; worship ~0 everywhere | finding | plan-m2 R11 |
| Clean lives (0 collapses): 2D 59%, 3D 34%, 4D 0%; lives with a child 11% / 7% / 0% | finding | plan-m2 R11 |
| 4D's peak is 3-6x the 3D knee at similar size: dimension adds its own factor | hint | same two sections |
| The more ticks at full pressure, the better the nursery (thermostat < ramp < fixed) | hint (one budget, 10 runs per row) | plan-m2 R7 anneal and ramp tables |
| Lowering hunger only by nutrient decay doesn't spare 4D bodies (body burn is the other hunger) | finding | plan-m2 R7 anneal design notes |
| Mates within reach ~ 1 - (1 - (1 + 2d) / cells)^(N - 1), about N (1 + 2d) / cells; NPCs sit as if scattered at random | law (matches measured 2D-4D) | plan-m2 R9; `scripts/probe_mating.py` |
| Births are rare in every dimension; most mate attempts come from NPCs too young, thin or unwell | finding | plan-m2 R9 |
| The senses carry enough for the diet goals in 2D-4D (a sense-only forager passes) | finding | plan-m2 R8; `scripts/probe_senses.py` |
| A policy right 30% of the time still passes 4D: the action draw isn't the limit | finding | plan-m2 R8 diagnostic; `probe_senses.py --follow` |
| The forager's move *and* eat rules are products (need x what's there): no linear brain can do it | finding | plan-m2 R8 diagnostic; `scripts/probe_handbrain.py` |
| Collapses vs hidden width at 20k ticks are U-shaped, best at 4 | superseded: a short-budget artifact (4 units plateau, 16+ keep learning) | plan-m2 R7 width sweep, then the 4D nursery-length table |
| Training time vs number of outputs | no law: 2D k ~ 0.5-0.7, 3D k ~ 0-0.1 with dummy outputs, which are cheap | plan-m2 R7 "Outputs vs training time" |
| float32 + exact transfers + plug keep verdicts; drift ~1e-12 at plug ticks | law | docs/plan-gpu-backend.md |

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
1. ~~Mutation per genome~~: done 2026-11-04 (slice R1). 1-3 per child loses;
   10-100 is a plateau; proposed default 30 per child.
2. ~~Smell reach per dimension~~: done 2026-11-04 (slice R2). Not the cause;
   no setting added.
3. ~~Success-rate logging~~: done 2026-11-04 (slice R3). Copies beat their
   parents only 8-12% at any count, because a chosen parent's score is mostly
   luck; the 1/5 rule can't be used as-is. Led to 5zorro's lineage rule (R4) and
   track record (R5).

## Sources
- Such et al., "Deep Neuroevolution: genetic algorithms are a competitive alternative..." (arXiv 1712.06567): https://arxiv.org/pdf/1712.06567
- Stanley and Miikkulainen, NEAT parameters (JAIR 2004 appendix): https://www-ai.cs.tu-dortmund.de/DOKUMENTE/JAIR/volume21/stanley04a-html/node9.html.gz
- Evolution strategy runtime on the sphere, Jägersküpper (GECCO 2005): https://gpbib.pmacs.upenn.edu/gecco2005/docs/p849.pdf
- Ochoa, "Setting the mutation rate: scope and limitations of the 1/L heuristic" (GECCO 2002): https://www.cs.stir.ac.uk/~goc/papers/SettingMutRateGECCO02.pdf
- Doerr et al., "Self-adjusting mutation rates with provably optimal success rules" (arXiv 1902.02588): https://arxiv.org/pdf/1902.02588
- Rechenberg's (1+1)-ES with the 1/5 rule (PyPop7 docs): https://pypop.readthedocs.io/en/latest/es/res.html
- Pólya's random walk theorem (ar5iv 1301.3916): https://ar5iv.arxiv.org/html/1301.3916
- Marginal value theorem: https://en.wikipedia.org/wiki/Marginal_value_theorem
- Lévy flight foraging hypothesis: https://en.wikipedia.org/wiki/L%C3%A9vy_flight_foraging_hypothesis ; Palyulin, Chechkin & Metzler (PNAS 2014): https://www.agnld.uni-potsdam.de/papers/2014_PalCheMe_PNAS111.pdf
- Yaeger et al. 2010, Polyworld network evolution: https://www.shinyverse.org/larryy/YaegerEtAl2010_EvolutionarySelectionOfNetworkStructureAndFunction_ALife12.pdf
- The Bibites: https://thebibites.itch.io/the-bibites
- EvoJAX (arXiv 2202.05008): https://arxiv.org/abs/2202.05008v1
