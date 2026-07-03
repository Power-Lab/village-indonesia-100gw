#!/usr/bin/env julia
using Pkg

const REPO_ROOT = @__DIR__
Pkg.activate(REPO_ROOT)

using JSON
using JuMP
using DataFrames, CSV
using Gurobi
using Base.Filesystem: mkpath

include(joinpath(REPO_ROOT, "functions", "preflight.jl"))

# 1) Load your core modeling code
include(joinpath(REPO_ROOT, "functions/function_compiler.jl"))

# 2) Read config.json
config_path, preflight_only = parse_cli_args(ARGS)
preflight = run_preflight(config_path, REPO_ROOT)
cfg = preflight.cfg
island           = cfg["island"]
year             = cfg["year"]
scenario         = cfg["scenario"]
clean            = cfg["clean"]
CO235reduction   = cfg["CO235reduction"]
BAUCO2emissions  = cfg["BAUCO2emissions"]
CO2_limit        = cfg["CO2_limit"]

# 3) Baseline model settings — overridable per job via optional config.json keys
mipgap         = Float64(get(cfg, "mipgap", 0.01))            # relative MIP gap
CO2_constraint = preflight.clean_flags.CO2_constraint
RE_constraint  = preflight.clean_flags.RE_constraint
RE_limit       = Float64(get(cfg, "RE_limit", 0.34))          # min RE share (clean runs)
village_storage_max_mwh = Float64(get(cfg, "village_storage_max_mwh", 208.0)) # per-unit cap on new village storage
connection_cost_scale = Float64(get(cfg, "connection_cost_scale", 1.0))      # multiplier on per-village interconnection cost (sensitivity lever)
lp_method      = Int(get(cfg, "lp_method", 2))                               # Gurobi LP Method (2 = barrier)
battery_duration_h = Float64(get(cfg, "battery_duration_h", 0.0))            # fixed battery duration (h); 0 = off (co-optimised)

# 4) Scenario toggles
Grid = preflight.flags.Grid
VillageBuild = preflight.flags.VillageBuild
ImportPrice = Float64(get(cfg, "import_price", preflight.flags.ImportPrice)) # $/MWh village grid imports
NoCoal = preflight.flags.NoCoal

if preflight_only
    println("Preflight checks passed for $(scenario)_$(island)_$(year)_$(clean)")
    exit()
end

# 6) Build input path
inputs_path = preflight.inputs_path

# 7) Create a scenario‑specific results folder
results_dir = preflight.results_dir
mkpath(results_dir)

# 8) Invoke the compiler, passing that folder
function_compiler(
    inputs_path,
    results_dir,
    mipgap,
    CO2_constraint,
    CO2_limit,
    RE_constraint,
    RE_limit,
    Grid,
    VillageBuild,
    ImportPrice,
    NoCoal,
    CO235reduction,
    BAUCO2emissions;
    village_storage_max_mwh = village_storage_max_mwh,
    connection_cost_scale = connection_cost_scale,
    lp_method = lp_method,
    battery_duration_h = battery_duration_h
)
