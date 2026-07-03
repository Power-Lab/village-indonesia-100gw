# function_compiler.jl
include("input_data.jl")
include("optimizer.jl")
include("result_extraction_function.jl")
# benders_decomposition.jl provides an optional capacity_expansion_benders
# solver for very large problems; include it and swap the call below to use it

function function_compiler(
        filepath::AbstractString,
        results_dir::AbstractString,
        mipgap::Float64,
        CO2_constraint::Bool,
        CO2_limit,
        RE_constraint::Bool,
        RE_limit,
        Grid::Bool,
        VillageBuild::Bool,
        ImportPrice,
        NoCoal::Bool,
        CO235reduction::Bool,
        BAUCO2emissions;
        village_storage_max_mwh::Float64 = 208.0,
        connection_cost_scale::Float64 = 1.0,
        lp_method::Int = 2,
        battery_duration_h::Float64 = 0.0
    )
    # 1) Load inputs
    inputs = input_data(filepath; connection_cost_scale = connection_cost_scale)

    # 2) Run the optimization
    solution = capacity_expansion(
        inputs,
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
        lp_method = lp_method,
        battery_duration_h = battery_duration_h
    )

    # 3) Extract & write results into the folder
    result_extraction(
        solution,
        inputs.demand,
        inputs,
        filepath,
        results_dir
    )

    return solution
end