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
| [EXP-001](#exp-001--full-timor-coordination-off-vs-on-baseline) | 2026-06-24 | Does grid coordination lower cost for full Timor? | timor / 2030 | `village`, `gridvillage` | baseline (first-pass interconnection costs) | OFF = ON = **$64.63 M/yr**; 0/780 connect | ✅ complete |

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
