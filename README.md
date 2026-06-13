# Village Indonesia Capacity Expansion Model (100 GW Program)

This repository contains an **open-source capacity expansion and operational model** tailored for Indonesia’s islands and village energy systems.  
The model simultaneously determines **generation capacity investments** and **dispatch decisions** under various policy scenarios, allowing researchers and planners to explore how **clean energy, grid expansion, village solar-plus-storage deployment, and emissions constraints** affect electricity supply and village electrification. The framework was originally developed to study industrial captive power coordination; village systems reuse the same decentralised-site machinery (formerly `ip_*`, now `village_*`).

It is written in **Julia** using **JuMP** for optimisation and is accompanied by Python scripts to create and run scenario jobs — `generate_jobs.py` for HPC/SLURM clusters and `generate_jobs_local.py` for local execution.

---

## Repository Structure

| Path / Folder | Description |
|----------------|--------------|
| `data_indonesia/<year>/<island>` | Raw input data used by the model. Each year/island folder contains CSV files describing generators (`generators.csv`), demand profiles (`demand.csv`), variability of renewable resources (`generators_variability.csv`), fuel costs (`fuels_data.csv`) and optional network files. Village-level data are stored in analogous `village_*` files. See `data_indonesia/README.md` for the full data dictionary. The Julia script reads these files and converts them into the sets and parameters required by the model. |
| `functions/` | Collection of Julia modules. `input_data.jl` parses the CSVs into data structures and calculates variable costs and emission rates; `optimizer.jl` builds the mixed-integer linear program representing the capacity expansion and dispatch problem; `result_extraction_function.jl` writes results such as generation by technology, industrial park outputs, and cost summaries to CSV files; `benders_decomposition.jl` implements an optional Benders decomposition algorithm for large problems; and `function_compiler.jl` ties everything together by loading input data, solving the optimisation, and exporting results. |
| `run_model.jl` | Stand-alone Julia script that reads a `config.json` file, interprets scenario flags and emission constraints, locates the appropriate input folder, and calls `function_compiler` to solve the model. It contains logic to enable or disable grid expansion, village-side generation investment, high import prices, and coal restrictions based on the scenario name, and adjusts emissions and renewable requirements when a clean scenario is selected. |
| `generate_jobs.py` | Python CLI utility for **HPC/SLURM** clusters. Reads a YAML scenario definition and generates subdirectories for every island/year/scenario/clean combination. For each job it writes a `config.json` file with the selected parameters and creates a symbolic link to a submission script. With the `--submit` flag, it submits each job via `sbatch`. CLI options: `--scenarios-file`, `--submit-script`, `--output-root`, `--submit`. |
| `generate_jobs_local.py` | Python CLI utility for **local execution**. Generates the same per-job `config.json` files as `generate_jobs.py` but, instead of creating SLURM symlinks, it immediately runs each job with `julia run_model.jl` in sequence. Reports a timestamped start and finish line for every job. CLI options: `--scenarios-file`, `--run-script` (path to `run_model.jl`), `--output-root`, `--bootstrap/--no-bootstrap` (skip the Julia environment check for faster repeat runs). |
| `scenario_*.yml` | YAML files that list islands, model years, scenario names, and whether to run a reference or clean case. They also define baseline "business-as-usual" (BAU) emissions and specify CO₂ limits for each island and year. You can create your own scenario file to customise the analysis. `scenario_maluku_test.yml` is a minimal single-island test case for local runs — see the [Test Case](#test-case-maluku-island-local) section. |

---

## Getting Started

**Prerequisites:** [Julia](https://julialang.org/downloads/) (tested with 1.12; `Manifest.toml` pins exact package versions), Python ≥ 3.8, and a valid Gurobi licence — see `docs/environment_setup.md` for licence options, **Windows + conda setup**, and environment hardening.

> Install Julia from the [official downloads page](https://julialang.org/downloads/) or via [juliaup](https://github.com/JuliaLang/juliaup). Avoid conda-forge Julia — package resolution is more reliable with the official toolchain.

1. **Install Python dependencies:**
   ```bash
   pip install click pyyaml
   ```

2. **Bootstrap the Julia environment** (once, from the repository root):
   ```bash
   julia --project=. bootstrap.jl
   ```
   This resolves and installs all Julia packages into a repo-local environment and confirms Gurobi can start. Takes about a minute the first time; instant on subsequent runs.

---

## Documentation Map

| Document | What it covers |
|----------|----------------|
| `data_indonesia/README.md` | Input data dictionary — every CSV, column by column |
| `docs/village_adaptation.md` | How the industrial-park framework maps to villages; scenario semantics |
| `docs/new_region_guide.md` | Step-by-step: add a new island/region (e.g. Timor) |
| `docs/outputs_guide.md` | Result files, columns, and headline metrics |
| `docs/environment_setup.md` | Gurobi licensing, Julia/juliaup setup, Python environment |
| `MODEL.md` | Mathematical formulation cross-referenced to the code |
| `CHANGES.md` | June 2026 village adaptation: renames, bug fixes, verification record |
| `data_indonesia/2030/timor_demo/README.md` | Synthetic village test case — solves in ~30 s |

---

## First Run: Maluku Island

`scenario_maluku_test.yml` is the recommended entry point. It runs a single small island (`maluku`, 2030, `base` scenario, no CO₂ constraints) that requires only four CSV files and typically solves in about a minute on a laptop.

```bash
python generate_jobs_local.py \
  --scenarios-file scenario_maluku_test.yml \
  --run-script run_model.jl \
  --output-root jobs
```

Expected output:
```
[...] ▶ Preparing Julia environment
[...] ✅ Julia environment ready (took 0:00:02)

[...] ▶ Starting job base_maluku_2030_reference
[...] ✅ Completed base_maluku_2030_reference (took 0:01:00)

🎉 All scenarios finished.
```

Results are written to `results/base_maluku_2030_reference/`.

Once this run succeeds, you can extend it by editing `scenario_maluku_test.yml`:
- Add `"clean"` to the `cleans` list to enable CO₂ and RE constraints.
- Add `"village"` to `scenarios` — requires the `village_*` input files not present in `data_indonesia/2030/maluku/`.
- Add `"2035"` to `years` once the corresponding data folder is populated.

---

## Second Run: Village Scenarios (timor_demo)

Once Maluku works, run the synthetic village test case — four village clusters
with diesel, candidate solar, and batteries (see
`data_indonesia/2030/timor_demo/README.md`):

```bash
python generate_jobs_local.py \
  --scenarios-file scenario_timor_demo.yml \
  --run-script run_model.jl \
  --output-root jobs
```

This solves the `village` (standalone) and `gridvillage` (coordinated)
scenarios in about 30 seconds each and demonstrates the core comparison of the
village solar study: coordination builds smaller village assets, imports
marginal energy from the grid, and lowers total cost.

---

## Run a Custom Scenario Locally

Create or edit a scenario YAML file (see [Preparing a Scenario File](#preparing-a-scenario-file)), then:

```bash
python generate_jobs_local.py \
  --scenarios-file your_scenario.yml \
  --run-script run_model.jl \
  --output-root jobs
```

This creates one job folder per island/year/scenario/clean combination under `jobs/`, runs each sequentially, and writes results to `results/<job_name>/`.

**Run a single job directly:**
```bash
julia --project=. run_model.jl --config jobs/<job_folder>/config.json
```

**Validate a config without solving** (preflight-only, useful before a long batch run):
```bash
julia --project=. run_model.jl --config jobs/<job_folder>/config.json --preflight-only
```

---

## HPC / SLURM Batch

`generate_jobs.py` generates job directories and SLURM submission scripts without running them locally:

```bash
python generate_jobs.py \
  --scenarios-file scenario_2030_example.yml \
  --submit-script submit_template.sb \
  --output-root jobs
```

Add `--submit` to automatically call `sbatch` on each generated job folder.

---

## Preparing a Scenario File

A scenario file (e.g., `scenario_2030_example.yml`) defines:

- `islands`: list of islands to model (e.g., `sumatera`, `jawa_bali`)
- `years`: list of planning years (e.g., `2030`, `2035`)
- `scenarios`: policy/system configurations that control flags in `run_model.jl` — valid values are `base`, `grid`, `village`, `gridvillage`, `nocoal`, `highimportprice` (`captive`/`gridcaptive` are accepted as legacy aliases for `village`/`gridvillage`)
- `cleans`: `reference` (no CO₂ or RE constraints) or `clean` (constraints active)
- `island_params`: baseline BAU CO₂ emissions per island (tonnes CO₂), used when `clean` is active
- `co2_limits`: CO₂ cap per island per year

See `scenario_maluku_test.yml` for a minimal working example and `scenario_2030_example.yml` for a full multi-island run.

---

## Model Assumptions

Defaults preserve the original study's behaviour; the first four are overridable
per run by adding the key to your scenario YAML (top level) or a job's
`config.json`.

| Parameter | Default | Meaning | Where |
|-----------|---------|---------|-------|
| `mipgap` | `0.01` | Gurobi relative MIP gap | config key |
| `RE_limit` | `0.34` | Minimum grid renewable share (`clean` runs only; counts grid generators' `RE` flag — village generation does not contribute) | config key |
| `import_price` | `59.0` $/MWh (×1.21 under `highimportprice`) | Flat price villages pay for grid imports | config key |
| `village_storage_max_mwh` | `208.0` | Per-unit cap on new village storage energy | config key |
| VOLL & NSE segments | data | Value of lost load and curtailment segments | `demand.csv` / `village_demand.csv` |
| Solve time limit | 72 h | Gurobi `TimeLimit` | `functions/optimizer.jl` |
| Village `Max_Cap_MW` | not enforced | Village new-build power capacity is unbounded | `functions/optimizer.jl` (commented out) |

---

## Customising Your Analysis

### Editing Scenario Parameters
- Modify scenario YAML files to adjust policies (e.g., include `highimportprice` to raise import costs).
- Emission caps and renewable shares can be changed by editing `co2_limits`, `BAU_emissions`, or setting `clean` cases.

### Adding New Input Data
- Create a new folder under `data_indonesia/` (e.g., `data_indonesia/2040/kalimantan`) and supply required CSVs (`generators.csv`, `demand.csv`, etc.).
- `input_data.jl` automatically parses these into the model.

### Changing Solver or Tolerance
- The default solver is **Gurobi** with a **1 % relative MIP gap** (`mipgap = 0.01`).
- The gap, RE share, village import price, and village storage cap can be set per run via optional config keys (see [Model Assumptions](#model-assumptions)); other solver options live in `functions/optimizer.jl`.

### Benders Decomposition
- For very large problems, an optional implementation lives in `functions/benders_decomposition.jl`. It is **not loaded by default**.
- To use it, add `include("benders_decomposition.jl")` in `functions/function_compiler.jl` and call `capacity_expansion_benders` instead of `capacity_expansion`.

---

## Output Files

After solving, each job’s results folder contains:

| File | Description |
|------|--------------|
| `generator_results.csv` | Grid generator capacity (start, final, change) and annual generation by unit. |
| `storage_results.csv` | Grid storage energy capacity by unit. |
| `transmission_results.csv` | Transfer capacity per corridor (start, final, change). |
| `nse_results.csv` | Non-served energy by segment and zone. |
| `cost_results.csv` | Annual cost breakdown ($M): fixed/variable, grid/village, NSE, imports, start-up. |
| `clean_energy_results.csv` | CO₂ emissions (grid, village, total) and grid renewable share. |
| `village_generator_results.csv` | Village unit capacity and generation per village. |
| `village_storage_results.csv` | Village battery energy capacity (MWh) per unit. |
| `village_import_results.csv` | Village grid imports (total MWh, peak MW) — `gridvillage` runs. |
| `village_nse_results.csv`, `village_nse_heat_results.csv` | Village non-served electricity / heat. |
| `village_heat_generator_results.csv` | Village heat output (zero in electricity-only setups). |

See `docs/outputs_guide.md` for column-level detail and how to compute the
headline coordinated-vs-standalone metrics.

You can import these CSVs into **Python (pandas)** or **Julia** for analysis and visualisation.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `julia: command not found` | Julia not on PATH | Install from [julialang.org](https://julialang.org/downloads/) or via juliaup, then restart your terminal |
| `ModuleNotFoundError: No module named 'click'` | The `python`/`python3` you invoked isn't the one with the dependencies installed (e.g. system Python vs conda) | Run `pip install click pyyaml` in the environment you use, and invoke the scripts with that same interpreter |
| Julia hangs printing `Juliaup configuration is locked by another process` | A concurrent julia launch or a stalled `juliaup self update` holds the juliaup lock | Wait for or kill the other juliaup/julia process; consider `juliaup config` settings to disable auto-update |
| `Error: Gurobi is installed but could not start a licensed optimizer session` | Licence missing, expired, or wrong path | Ensure `GRB_LICENSE_FILE` points to a valid `gurobi.lic`; run `gurobi_cl` to confirm |
| `Error: Config file not found` | Wrong working directory or missing `--config` flag | Run from the repo root: `julia --project=. run_model.jl --config jobs/<job>/config.json` |
| `Error: Unknown scenario: <name>` | Typo in `scenarios` list | Valid values: `base`, `grid`, `village`, `gridvillage`, `highimportprice`, `nocoal` |
| `Error: Missing required input files … village_generators.csv` | `village` or `gridvillage` on an island with no `village_*` files | Supply the `village_*` CSVs or remove village scenarios for that island |
| `Error: Missing required input files … network.csv` | `grid`, `gridvillage`, or `nocoal` on an island with no network data | Supply `network.csv` or use `base`/`village` scenarios instead |
| Julia package error on first run | Stale or missing `Manifest.toml` | Run `julia --project=. bootstrap.jl` to resolve and reinstall |

---

## Contributing

Contributions are welcome!  
Please open an issue or pull request with a clear description of proposed changes or bugs.  
Major modifications should first be discussed via an issue to ensure consistency with the existing framework.

This repository follows — and is the reference implementation of — the [Power-Lab Code Standards](https://github.com/Power-Lab/.github/blob/main/CONTRIBUTING.md). See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the per-PR checklist (formatting, naming, config-driven runs, hygiene).

---

## Licence

This project is released under the **MIT Licence**.  
See [`LICENSE`](LICENSE) for details.
