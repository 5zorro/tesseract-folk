# Safety

Tesseract Folk is meant to ship as a game mod that strangers install. This file
says what could go wrong, what the project does about it, and what it won't do.
Read it before adding I/O, an AI-model integration, a file format, or a release
pipeline.

Status markers match `DESIGN.md`: **[enforced]** is checked by a test or by the
code's structure, **[planned]** must be in place before the milestone that needs
it ships, **[decision]** is open and the maintainer's call.

---

## 1. What this project is, and isn't

The NPCs are tiny neural nets (~900 weights) living in a simulated grid. Their
"dimensions" are the axes of that grid. An NPC can only pick one of the
simulation's in-world actions (move, eat, give, pray, …), and the simulation
doesn't do anything outside its own memory except read and write snapshot files.

So the simulation itself is not a way to reach other systems: no network, no
files beyond snapshots, no code execution. What makes malware dangerous is
exploit, credential-theft and spreading code, and this project contains none of
that. Neuroevolution has been published openly for decades, so releasing this
code gives nobody new capability.

The real risks are at the edges, where the project touches other things:
players' machines (mods are native code), shared files (snapshots), AI-model
APIs (the planned Claude pawn and deity), and real people (voices).

## 2. Threat model

| Asset | Who could be hurt | Entry point | Section |
|---|---|---|---|
| The player's computer | Players | The mod DLL; loading snapshot files from others | 3, 4, 6 |
| The player's API key and money | Players who enable Claude features | AI-model integration, logs, snapshots | 5 |
| Other systems the AI model could reach | Anyone | An AI model given tools beyond the game | 5 |
| Players' wellbeing | Players | Dialogue written by an AI model | 5 |
| Voice actors' likeness | Real people | Cloned voices | 7 |
| The project's standing | 5zorro | Breaking a game's or site's modding rules | 6 |

## 3. The simulation core (`sim/`)

- **[enforced]** `sim/` imports no networking, process, or code-loading modules
  (`socket`, `http`, `urllib`, `requests`, `subprocess`, `ctypes`, `pickle`,
  `importlib`, …) and never calls `eval`, `exec` or `__import__`.
  `tests/test_safety.py` checks this on every test run.
- **[enforced]** NPC actions are in-world only. An action is an index into
  `sim.actions` and changes simulation state, nothing else.
- **Rule:** never wire an NPC action, sensor, or evolved behavior to anything
  outside the simulation (files, network, OS, other programs). Never evolve or
  train brains against a real system.
- **Rule:** anything that talks to the outside world lives outside `sim/` (for
  example an `integrations/` package) and plugs in through the `Controller`
  interface in `sim/controllers.py`. That keeps the core auditable and portable.

## 4. Snapshot files

Players may share snapshots, so treat every snapshot as untrusted input.

- **[enforced]** The format is data only: `state.json` plus `world.npz`.
  NumPy is never allowed to load pickled objects (`tests/test_safety.py` checks
  that `allow_pickle` is never turned on in `sim/`).
- **[enforced]** Every loaded brain is checked for exact array shapes and
  finite weights (`Brain.check`, used by `load_snapshot` and `seed_brains`).
  JSON accepts `NaN` and `Infinity`, so without this a crafted file would crash
  mid-run. Tests: `tests/test_nursery.py`.
- **[planned]** Before snapshots are shared publicly: size limits on both files,
  and shape checks on the world arrays (`world.npz`), so a crafted file fails
  with a clear error instead of exhausting memory.
- The nursery (`sim/nursery.py: load_brain_pool`) reads the same `state.json`,
  so brain pools shared between players are untrusted input under the same rules.
  It already refuses brains whose shape doesn't fit the world.
- **Rule:** never switch to pickle, `eval`, or any format that can carry code.
  The C++ port loads the same JSON and needs the same checks.

## 5. AI-model features (M8: Claude pawn and Claude deity)

None of this is built yet (`ClaudeController` is a stub). It has to be in place
before M8 ships.

**What the model can do:**
- **[planned]** The model sees a text description of the NPC's senses and
  answers with one action name. The code checks the answer against
  `sim.actions` and falls back to `stay` on anything else (unknown names,
  out-of-range numbers, malformed JSON).
- **[planned]** The model gets **no tools** beyond choosing in-game actions: no
  file, shell, web, email, or code-execution tools, ever. This is what stops
  prompt-injection attacks like the Morris II "AI worm" research (hostile text
  that makes an AI agent with real tools copy the attack onward). A model whose
  only output is "move east" has nothing to spread with.
- **[planned]** Text that comes from the game world (NPC names, player-written
  text, other models' replies) goes into the prompt as clearly marked data, never
  as instructions.

**Keys and money:**
- **[planned]** Claude features are opt-in and off by default.
- **[planned]** The player's API key comes from an environment variable or a local
  config file outside the game folder. It never goes into snapshots, logs, stats,
  crash reports, or anything else that gets shared.
- **[planned]** Hard limits the player controls: calls per minute and a spending
  budget per session. The mod stops calling when it reaches either one, and says so.
- **[planned]** In the C++ port, calls run on a background thread so the game
  never freezes waiting for a reply.

**Dialogue:**
- **[planned]** The deity and any speaking NPC get a system prompt that keeps
  them in character and within content limits. They never impersonate real
  people.
- **[decision]** Whether the Claude deity ships at all, or only the pawn.

## 6. Distributing the mod (M11: 4D Miner, or any other game)

A 4D Miner mod is a DLL that runs with the player's full permissions, so players
have to trust the binary.

- **[planned]** Source code is public, and release DLLs are built by public CI
  (the 4D-Modding template already uses GitHub Actions) and published with
  checksums.
- **[planned]** No auto-updater that downloads and runs code. Updates are manual.
- **[planned]** No telemetry. The only network traffic is the opt-in AI-model
  calls in section 5, to the provider the player chose, with their own key.
- **[decision]** Check the game developer's stance on mods before publishing.
  4D Miner's mod loader is community-made and unofficial. For Skyrim, follow
  Bethesda's and Nexus Mods' rules.

## 7. Voices

- **[decision]** `DESIGN.md` §11 mentions xVASynth, which imitates real game voice
  actors. Voice actors have publicly refused consent to AI imitations of their
  voices, and Nexus Mods may remove a mod after a credible complaint.
- **Rule:** don't clone a real person's voice without their consent. Use original
  recordings, licensed voices, or synthetic voices that aren't modeled on a real
  person.

## 8. The creatures themselves

Nets of a few hundred weights aren't sentient by any serious account, so hunger,
stink, collapse and smiting are game mechanics, not suffering. If brains ever
grow by orders of magnitude, or start learning during their lifetimes in rich
ways, revisit this section.

## 9. Before each public release

- [ ] `python -m pytest` passes, including `tests/test_safety.py`.
- [ ] No keys, tokens, `.env` files, personal emails or local paths in the repo
      or the release files (`git grep -nI` for `key`, `token`, `@`, `C:\Users`).
- [ ] Every **[planned]** item for the features in this release is now **[enforced]**.
- [ ] Release binaries were built by CI from a tagged commit, with checksums.
- [ ] The **[decision]** items for this release are settled, and this file is
      updated to say how.

## 10. Reporting a problem

See `SECURITY.md` in the repository root.
