function parse_cli_args(args::Vector{String})
    config_path = "config.json"
    preflight_only = false
    index = 1

    while index <= length(args)
        arg = args[index]

        if arg == "--preflight-only"
            preflight_only = true
        elseif arg == "--config"
            index += 1
            index <= length(args) || error("Missing value after --config")
            config_path = args[index]
        elseif startswith(arg, "--")
            error("Unknown argument: $(arg)")
        else
            config_path = arg
        end

        index += 1
    end

    return (abspath(config_path), preflight_only)
end

function load_config(config_path::AbstractString)
    isfile(config_path) || error("Config file not found: $(config_path)")
    cfg = JSON.parsefile(config_path)

    required_keys = [
        "island",
        "year",
        "scenario",
        "clean",
        "CO235reduction",
        "BAUCO2emissions",
        "CO2_limit",
    ]

    missing_keys = [key for key in required_keys if !haskey(cfg, key)]
    isempty(missing_keys) || error("Config file is missing required keys: $(join(missing_keys, ", "))")

    return cfg
end

function scenario_settings(scenario::AbstractString)
    # "captive" and "gridcaptive" are legacy aliases from the industrial-park
    # studies; they map to the same settings as "village" and "gridvillage".
    if scenario == "base"
        return (Grid = false, VillageBuild = false, ImportPrice = 59.0, NoCoal = false)
    elseif scenario == "gridvillage" || scenario == "gridcaptive"
        return (Grid = true, VillageBuild = true, ImportPrice = 59.0, NoCoal = false)
    elseif scenario == "grid"
        return (Grid = true, VillageBuild = false, ImportPrice = 59.0, NoCoal = false)
    elseif scenario == "village" || scenario == "captive"
        return (Grid = false, VillageBuild = true, ImportPrice = 59.0, NoCoal = false)
    elseif scenario == "highimportprice"
        return (Grid = true, VillageBuild = true, ImportPrice = 59.0 * 1.21, NoCoal = false)
    elseif scenario == "nocoal"
        return (Grid = true, VillageBuild = false, ImportPrice = 59.0, NoCoal = true)
    end

    error("Unknown scenario: $(scenario). Valid values: base, grid, village, gridvillage, highimportprice, nocoal")
end

function clean_settings(clean::AbstractString)
    if clean == "reference"
        return (CO2_constraint = false, RE_constraint = false)
    elseif clean == "clean"
        return (CO2_constraint = true, RE_constraint = true)
    end

    error("Unknown clean flag: $(clean)")
end

function expected_input_files(flags)
    required = [
        "generators.csv",
        "demand.csv",
        "generators_variability.csv",
        "fuels_data.csv",
    ]

    if flags.Grid
        push!(required, "network.csv")
    end

    if flags.VillageBuild
        append!(required, [
            "village_generators.csv",
            "village_demand.csv",
            "village_demandheat.csv",
            "village_generators_variability.csv",
        ])
    end

    return required
end

function validate_input_files(inputs_path::AbstractString, flags)
    isdir(inputs_path) || error("Input data directory not found: $(inputs_path)")

    missing_files = String[]
    for filename in expected_input_files(flags)
        full_path = joinpath(inputs_path, filename)
        isfile(full_path) || push!(missing_files, filename)
    end

    isempty(missing_files) || error(
        "Missing required input files in $(inputs_path): $(join(missing_files, ", "))"
    )
end

function validate_gurobi()
    try
        model = Model(Gurobi.Optimizer)
        set_silent(model)
        @variable(model, 0 <= x <= 1)
        @objective(model, Max, x)
        optimize!(model)
    catch err
        error(
            "Gurobi is installed but could not start a licensed optimizer session: " *
            sprint(showerror, err)
        )
    end

    return nothing
end

function run_preflight(config_path::AbstractString, repo_root::AbstractString)
    cfg = load_config(config_path)
    flags = scenario_settings(cfg["scenario"])
    clean_flags = clean_settings(cfg["clean"])
    inputs_path = joinpath(repo_root, "data_indonesia", cfg["year"], cfg["island"])
    cc_scale = Float64(get(cfg, "connection_cost_scale", 1.0))
    cc_suffix = cc_scale == 1.0 ? "" : "_cc$(cc_scale)"
    results_dir = joinpath(repo_root, "results", "$(cfg["scenario"])_$(cfg["island"])_$(cfg["year"])_$(cfg["clean"])$(cc_suffix)")

    validate_gurobi()
    validate_input_files(inputs_path, flags)

    return (
        cfg = cfg,
        flags = flags,
        clean_flags = clean_flags,
        inputs_path = inputs_path,
        results_dir = results_dir,
    )
end