# Experiment & Run Log — Village Indonesia 100 GW model

Running lab notebook of every model run and experiment. **Newest first.** Each
*experiment* is a question plus the run(s) that answer it; each *run* maps 1:1 to
a `results/<run-name>/` folder.

> **Maintaining this file:** when a run is launched, add a new `### EXP-NNN`
> section (copy the [template](#template--copy-for-each-new-experiment)) with the
> question and setup; when it finishes, fill in the results, solver outcome, and
> artifact paths, and update the [summary table](#summary) + its Status.

## Conventions
- **Run name** = `<scenario>_<island>_<year>_<clean>` — identical to the `jobs/`
  and `results/` folder names.
- **Coordination**: OFF = `village` (islanded microgrids); ON = `gridvillage`
  (villages may connect to the shared grid and trade surplus solar). See
  `functions/preflight.jl` → `scenario_settings`.
- **Cost** = `Total_Costs` from `cost_results.csv`, in **$M/yr** (annualized
  total system cost).
- **Defaults** (unless noted): `mipgap` 0.01, `import_price` 59 $/MWh,
  `village_storage_max_mwh` 208, Gurobi `TimeLimit` 72 h; `reference` = no CO₂/RE
  constraints.
- **Environment**: Julia 1.12.6, Gurobi 13.0.2 (bundled, academic licence).
  Invoke generators with `python3`.

## Summary
| Exp | Date | Question | Island / Year | Scenarios | Key change | Headline result | Status |
|-----|------|----------|---------------|-----------|------------|-----------------|--------|
| [EXP-003](#exp-003--diversity-stress-test-do-archetype-shapes-unlock-coordination) | 2026-06-25 | Does load-shape diversity unlock coordination value? | timor_diverse / 2030 | village vs gridvillage(free) | 390/780 villages reshaped to midday load | 🟡 running |
| [EXP-002](#exp-002--interconnection-cost-sensitivity-sweep) | 2026-06-25 | Where does coordination start to pay off? | timor / 2030 | `gridvillage` × cost scale | `connection_cost_scale` sweep | **nowhere** — even free connection saves 0.004% ($2.6k); 7.75 MWh traded | ✅ complete |
| [EXP-001](#exp-001--full-timor-coordination-off-vs-on-baseline) | 2026-06-24 | Does grid coordination lower cost for full Timor? | timor / 2030 | `village`, `gridvillage` | baseline (first-pass interconnection costs) | OFF = ON = **$64.63 M/yr**; 0/780 connect | ✅ complete |

---

## EXP-003 — Diversity stress test: do archetype shapes unlock coordination?
**Date:** 2026-06-25 | **Status:** 🟡 running | **Dataset:** `data_indonesia/2030/timor_diverse/` (built by `make_diverse_demand.py`)

**Question.** EXP-002 found ~0 coordination benefit and pinned the cause to homogeneity (773/780 villages share one residential load shape). Does injecting load-**shape** diversity unlock coordination value — i.e., could real per-archetype load calculators actually matter?

**Setup.** Copy of the real Timor dataset; **half the villages (390) reshaped to a midday-peaking load** (energy-preserved per village), the other 390 kept on the real residential/evening profile. Everything else identical (magnitudes, solar, costs, connection costs). Single shared bus, so daytime- and evening-load villages can trade. Compare the coordination benefit (OFF vs free ON) against the homogeneous EXP-002 result (0.004%, 7.75 MWh).

**Runs.**
| Run | scenario / scale | Connected | Traded MWh | Total $M | Outcome |
|-----|------------------|-----------|------------|----------|---------|
| `village_timor_diverse` | OFF | — | — | — | 🟡 running |
| `gridvillage_timor_diverse_cc0.0` | ON, free | — | — | — | 🟡 queued |

**Results.** _pending._

**Artifacts.** `results/village_timor_diverse_2030_reference/`, `results/gridvillage_timor_diverse_2030_reference_cc0.0/`, log `logs/diverse_test.log`, builder `make_diverse_demand.py`.

---

## EXP-002 — Interconnection-cost sensitivity sweep
**Date:** 2026-06-25 | **Status:** ✅ complete (stopped after probe — see conclusion) | **Configs:** `jobs/gridvillage_timor_2030_reference_cc<scale>/`

**Question.** At what interconnection-cost level does grid coordination start to pay off? (EXP-001 baseline: at full cost, 0/780 connect, OFF = ON = $64.63 M.)

**Setup.** `gridvillage`, timor / 2030 / reference, 780 villages. Sweep the new `connection_cost_scale` key (multiplies every village's `Cost_per_yr`); `lp_method=2` (barrier) by default. Design: run `scale=0` (free connection) FIRST to bound the maximum coordination benefit — if it yields ~0 benefit, coordination doesn't help at any cost and we stop; otherwise map the curve over {0, 0.1, 0.25, 0.5, 0.75}.

**Runs.**
| Run | scale | Solver | Wall time | Connected | Total $M | Outcome |
|-----|-------|--------|-----------|-----------|----------|---------|
| `..._cc0.0` | 0.0 | LP\* | 14.4 min | 780/780 | 64.62884 | optimal, gap 0% |

\*Nominally MILP, but presolve fixed all 780 connection binaries (free ⇒ connect-all is dominant), so it solved as a pure LP — no branching.

**Results.** Free, unlimited interconnection saves only **$2,569/yr vs the $64.63 M standalone baseline — 0.004%**. All 780 villages connect, but total energy traded across the whole island is **7.75 MWh/yr** (331 villages import a trace, 8 export; import = export, balanced). The sharing mechanism is exercised, but the volume is a rounding error.

**Conclusion.** **Grid coordination does not help Timor at any interconnection cost.** The `scale=0` run is the benefit ceiling; any positive cost only shrinks it toward the $0 already seen at `scale=1` (EXP-001). So the curve `{0.1, 0.25, 0.5, 0.75}` was **not run** — it would trace a flat ~0 line. Root cause: **village homogeneity** — 780 villages with similarly-sized solar+battery and similar GHI/demand profiles rarely have surplus/deficit that line up, so there's almost nothing to arbitrage. Interconnection-cost calibration is *not* the value lever after all.

**Artifacts.** `results/gridvillage_timor_2030_reference_cc0.0/`, log `logs/sweep_cc0.log`.

**Reproduce.** `julia --project=. run_model.jl --config jobs/gridvillage_timor_2030_reference_cc0/config.json`

---

## EXP-001 — Full Timor: coordination OFF vs ON (baseline)
**Date:** 2026-06-24 &nbsp;|&nbsp; **Status:** ✅ complete &nbsp;|&nbsp; **Scenario file:** `scenario_timor.yml`

**Question.** At realistic (first-pass) interconnection costs, does letting Timor
villages connect to a shared grid and trade surplus solar (`gridvillage`) reduce
total system cost vs. standalone microgrids (`village`)?

**Setup.**
- Island `timor` = all 4 kabupaten, **780 villages**, 1344 representative hours.
  Data built from the real NTT workbooks via `python -m tools.ntt.build_timor`.
- Year 2030, `reference` (no CO₂/RE limits). Params: defaults (mipgap 0.01,
  import_price 59 $/MWh, village_storage_max_mwh 208, TimeLimit 72 h, Crossover 0).
- Hardware: 72-core / 187 GB shared box.

**Runs.**
| Run | Coordination | Solver | Wall time | Outcome |
|-----|--------------|--------|-----------|---------|
| `village_timor_2030_reference` | OFF | LP (barrier) | 12:54 | optimal, obj 6.46314132e7 |
| `gridvillage_timor_2030_reference` | ON | MILP (780 binaries) | 37:24 | optimal, gap 0.0000%, 1 node |

**Results ($M/yr).**
| Component | OFF | ON |
|-----------|----:|---:|
| **Total** | **64.6314** | **64.6314** |
| Solar PV (fixed) | 25.80 | 25.80 |
| Battery (fixed) | 36.34 | 36.34 |
| Diesel (variable) | 2.49 | 2.49 |
| Grid imports | 0 | 0 |
| Non-served energy | 0 | 0 |
| **Villages connected** | — | **0 / 780** |

Totals match to ~8 significant figures (differ by ~$0.03 = solver tolerance).
Imports = exports = 0; `transmission_flow_results.csv` net flow = 0.

**Conclusion.** Coordination provides **no benefit** at the first-pass
interconnection costs in `village_connection.csv` — standalone solar+battery
beats interconnecting for every village, so 0 connect and `gridvillage` collapses
onto the standalone solution. Reproduces the documented 81-village Belu result at
full island scale. **The lever is interconnection-cost calibration** (docs:
making connection cheap → 18/81 connected in Belu).

**Performance notes.**
- Model size: village 23.1M rows / gridvillage 25.2M rows × 780 binaries; peak
  memory ~69 GB.
- gridvillage Gurobi breakdown: barrier 712 s → crossover 203 s →
  **~535 s wasted "concurrent spin"** (`can be avoided by choosing Method=3`) →
  B&B 1 node (instant). Setting an explicit LP `Method` in
  `functions/optimizer.jl` would reclaim ~9 min on large runs. Crossover runs at
  the MIP root even with `Crossover=0` (B&B needs a vertex basis).

**Artifacts.**
- `results/village_timor_2030_reference/`, `results/gridvillage_timor_2030_reference/` (15 CSVs each)
- Solver log: `logs/timor_full_run.log`
- Configs: `jobs/village_timor_2030_reference/config.json`, `jobs/gridvillage_timor_2030_reference/config.json`

**Reproduce.**
```bash
python3 generate_jobs_local.py \
  --scenarios-file scenario_timor.yml \
  --run-script run_model.jl \
  --output-root jobs --no-bootstrap
```

**Follow-ups.** interconnection-cost sensitivity sweep on `village_connection.csv`
(find the threshold where villages start connecting); LP `Method` tuning +
re-benchmark vs this run.

---

## Template — copy for each new experiment
```markdown
## EXP-NNN — <short title>
**Date:** YYYY-MM-DD | **Status:** 🟡 running / ✅ complete / ❌ failed | **Scenario file:** `...`

**Question.** <what this run answers / what changed vs the previous run>

**Setup.** island / year / clean, # villages, scenarios, params changed from defaults, hardware.

**Runs.**
| Run | Coordination | Solver | Wall time | Outcome |
|-----|--------------|--------|-----------|---------|

**Results ($M/yr).** <table or headline numbers; villages connected; NSE; imports>

**Conclusion.** <1–3 sentences>

**Performance notes.** <solve-time breakdown, memory, anything notable>

**Artifacts.** results/… , logs/… , configs/…

**Reproduce.** <command>

**Follow-ups.** <next experiments suggested>
```
