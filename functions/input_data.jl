function input_data(filepath)

    #GRID
    #Generators
    #reading generator data
    generators = DataFrame(CSV.File(joinpath(filepath, "generators.csv")));
    
    #ID for all generators for easy reference
    G = generators.R_ID;

    #set of zones
    Z = convert(Array{Int64}, unique(collect(skipmissing(generators.Zone))));

    #Demand
    #reading reference demand input data
    demand_inputs_ref = DataFrame(CSV.File(joinpath(filepath, "demand.csv")))
    
    #value of losr load (cost of involuntary non-served energy)
    VOLL = demand_inputs_ref.Voll[1]
    
    #set of price responsive demand (non-served energy) segments
    S = convert(Array{Int64}, collect(skipmissing(demand_inputs_ref.Demand_Segment)))
    
    #creating a data frame for nse segments
    nse = DataFrame(Segment = S, 
                    NSE_Cost = VOLL.*collect(skipmissing(demand_inputs_ref.Cost_of_Demand_Curtailment_per_MW)),
                    NSE_Max = collect(skipmissing(demand_inputs_ref.Max_Demand_Curtailment)))
    
    #set of time sample sub-periods
    P = convert(Array{Int64}, 1:demand_inputs_ref.Rep_Periods[1])
    #sub-period cluster weights = number of hours represented by each sample period
    W = convert(Array{Int64}, collect(skipmissing(demand_inputs_ref.Sub_Weights)))
    #set of sequential hours per sub-period
    hours_per_period = convert(Int64, demand_inputs_ref.Timesteps_per_Rep_Period[1])

    #set of all time steps
    T = convert(Array{Int64}, demand_inputs_ref.r_id);
    
    #set of all time steps excluding the last time step
    T_red = T[1:end-1]

    #creating a vector of sample weights
    sample_weight = zeros(Float64, size(T,1))
    t=1
    for p in P
        for h in 1:hours_per_period
            sample_weight[t]=W[p]/hours_per_period
            t += 1
        end
    end
    
    #grid demand
    demand_input = DataFrame(CSV.File(joinpath(filepath, "demand.csv")))
    demand_cols = [Symbol("demand_z$i") for i in Z]
    demand = select(demand_input, demand_cols...);
    

    #Variability
    #read generator capacity factors by hour
    #the first column of generators_variability.csv is the hour index (r_id), so it is
    #dropped to line profile column g up with generator R_ID g; generators beyond the
    #last profile column (e.g. new-build candidates) get a flat 1.0 availability
    variability = DataFrame(CSV.File(joinpath(filepath, "generators_variability.csv")))[:, 2:end]
    for g in (ncol(variability)+1):maximum(G)
        variability[!, Symbol("flat_cf_", g)] .= 1.0
    end

    #Fuel - same data will be used for village generators
    #read fuels data
    fuels = DataFrame(CSV.File(joinpath(filepath, "fuels_data.csv")));

    #Lines
    #reading network data
    if isfile(joinpath(filepath, "network.csv"))
        lines = DataFrame(CSV.File(joinpath(filepath, "network.csv")));
        #fixed O&M costs for lines
        lines.Line_Fixed_Cost_per_MW_yr = lines.Line_Reinforcement_Cost_per_MWyr
        #set of all lines
        L = convert(Array{Int64}, lines.r_id);
    else
        lines = DataFrame(
            r_id                       = Int[],
            path_name                  = String[],
            substation_path            = String[],
            Line_Reinforcement_Cost_per_MWyr = Float64[],
            Line_Max_Flow_MW           = Float64[],
            B                          = Float64[],
            distance_km                = Float64[],
        )
            L = Int[]  # empty line set
    end

    #calculating the associated variable costs for generators
    generators.Var_Cost = zeros(Float64, size(G,1))
    generators.CO2_Rate = zeros(Float64, size(G,1))
    generators.Start_Cost = zeros(Float64, size(G,1))
    generators.CO2_Per_Start = zeros(Float64, size(G,1))
    
    for g in G
        # Variable cost ($/MWh) = variable O&M ($/MWh) + fuel cost ($/MMBtu) * heat rate (MMBtu/MWh)
        generators.Var_Cost[g] = generators.Var_OM_Cost_per_MWh[g] +
            fuels[fuels.Fuel.==generators.Fuel[g],:Cost_per_MMBtu][1]*generators.Heat_Rate_MMBTU_per_MWh[g]
        # CO2 emissions rate (tCO2/MWh) = fuel CO2 content (tCO2/MMBtu) * heat rate (MMBtu/MWh)
        generators.CO2_Rate[g] = fuels[fuels.Fuel.==generators.Fuel[g],:CO2_content_tons_per_MMBtu][1]*generators.Heat_Rate_MMBTU_per_MWh[g]
        # Start-up cost ($/start/MW) = start up O&M cost ($/start/MW) + fuel cost ($/MMBtu) * start up fuel use (MMBtu/start/MW) 
        generators.Start_Cost[g] = generators.Start_Cost_per_MW[g] +
            fuels[fuels.Fuel.==generators.Fuel[g],:Cost_per_MMBtu][1]*generators.Start_Fuel_MMBTU_per_MW[g]
        # Start-up CO2 emissions (tCO2/start/MW) = fuel CO2 content (tCO2/MMBtu) * start up fuel use (MMBtu/start/MW) 
        generators.CO2_Per_Start[g] = fuels[fuels.Fuel.==generators.Fuel[g],:CO2_content_tons_per_MMBtu][1]*generators.Start_Fuel_MMBTU_per_MW[g]
    end
    
    #VILLAGES
    #Village Generators
    #reading village generator data
    if isfile(joinpath(filepath, "village_generators.csv"))
        village_generators = DataFrame(CSV.File(joinpath(filepath, "village_generators.csv")));

    else
        village_generators = DataFrame(
            R_ID                        = Int[],
            Resource                    = String[],
            Zone                        = String[],
            Village                     = Int[],
            technology                  = String[],
            Existing_Cap_MW             = Float64[],
            Fuel                        = String[],
            Heat_Rate_MMBTU_per_MWh     = Float64[],
            Var_OM_Cost_per_MWh         = Float64[],
            Start_Cost_per_MW           = Float64[],
            Start_Fuel_MMBTU_per_MW     = Float64[],
            Commit                      = Int[],
            New_Build                   = Int[],
            STOR                        = Int[]
        )
    end

    #ID for all villages for easy reference
    VIL = convert(Array{Int64}, unique(collect(skipmissing(village_generators.Village))));

    #village generators set
    VIL_G = village_generators.R_ID;

    #grid zone of each village (taken from its first listed generator), used to
    #assign village grid imports to the right zone bus
    village_zone = Dict{Int,Int}()
    for v in VIL
        idx = findfirst(x -> !ismissing(x) && x == v, village_generators.Village)
        village_zone[v] = village_generators.Zone[idx]
    end

    #per-village grid interconnection cost ($/yr) and capacity cap (MW), read from
    #village_connection.csv; drives the co-optimised connect-vs-island decision in
    #optimizer.jl. Missing rows / missing file default to free connection with a
    #generous cap (i.e. reproduces the prior always-connected behaviour).
    village_connect_cost = Dict{Int,Float64}()
    village_connect_max  = Dict{Int,Float64}()
    if isfile(joinpath(filepath, "village_connection.csv"))
        vc = DataFrame(CSV.File(joinpath(filepath, "village_connection.csv")))
        for r in eachrow(vc)
            village_connect_cost[r.Village] = r.Cost_per_yr
            village_connect_max[r.Village]  = r.Max_Connect_MW
        end
    end
    for v in VIL
        get!(village_connect_cost, v, 0.0)
        get!(village_connect_max, v, 1.0e6)
    end

    #Village Demand
    if isfile(joinpath(filepath, "village_demand.csv"))
        village_demand_input = DataFrame(CSV.File(joinpath(filepath, "village_demand.csv")));
        #generate column symbols based on VIL indices
        village_demand_cols = [Symbol("demand_village$i") for i in VIL]
        village_demand = select(village_demand_input, village_demand_cols...);

        #set of price responsive demand (non-served energy) segments
        VIL_S = convert(Array{Int64}, collect(skipmissing(village_demand_input.Demand_Segment)))

        VIL_VOLL = village_demand_input.Voll[1]
    
        #creating a data frame for nse segments
        nse_village = DataFrame(Segment = VIL_S, 
                    NSE_Cost = VIL_VOLL.*collect(skipmissing(village_demand_input.Cost_of_Demand_Curtailment_per_MW)),
                    NSE_Max = collect(skipmissing(village_demand_input.Max_Demand_Curtailment)))
    else
        village_demand = DataFrame(
            r_id = Int[]
        )

        nse_village = DataFrame(
            Segment = Int[],
            NSE_Cost = Float64[],
            NSE_Max = Float64[]
        )

        VIL_S = Int[]
        VIL_VOLL = 0.0
    end

    if isfile(joinpath(filepath, "village_demandheat.csv"))
        village_heat_demand_input = DataFrame(CSV.File(joinpath(filepath, "village_demandheat.csv")));
        # Generate column symbols based on VIL indices
        village_heat_demand_cols = [Symbol("demand_village$i") for i in VIL]
        village_demandheat = select(village_heat_demand_input, village_heat_demand_cols...);
    else
        village_demandheat = DataFrame(
            r_id = Int[]
        )
    end

    #VIL Variability
    if isfile(joinpath(filepath, "village_generators_variability.csv"))
        #read village generator capacity factors by hour, dropping the leading hour
        #index column so profile column g lines up with village generator R_ID g
        village_variability = DataFrame(CSV.File(joinpath(filepath, "village_generators_variability.csv")))[:, 2:end]
        for g in (ncol(village_variability)+1):(isempty(VIL_G) ? 0 : maximum(VIL_G))
            village_variability[!, Symbol("flat_cf_", g)] .= 1.0
        end
    else
        village_variability = DataFrame(
            r_id = Int[]
        )
    end

    #calculating the associated variable costs for village generators
    village_generators.Var_Cost = zeros(Float64, size(VIL_G,1))
    village_generators.CO2_Rate = zeros(Float64, size(VIL_G,1))
    village_generators.Start_Cost = zeros(Float64, size(VIL_G,1))
    village_generators.CO2_Per_Start = zeros(Float64, size(VIL_G,1))

    for g in VIL_G
        # Variable cost ($/MWh) = variable O&M ($/MWh) + fuel cost ($/MMBtu) * heat rate (MMBtu/MWh)
        village_generators.Var_Cost[g] = village_generators.Var_OM_Cost_per_MWh[g] +
            fuels[fuels.Fuel.==village_generators.Fuel[g],:Cost_per_MMBtu][1]*village_generators.Heat_Rate_MMBTU_per_MWh[g]
        # CO2 emissions rate (tCO2/MWh) = fuel CO2 content (tCO2/MMBtu) * heat rate (MMBtu/MWh)
        village_generators.CO2_Rate[g] = fuels[fuels.Fuel.==village_generators.Fuel[g],:CO2_content_tons_per_MMBtu][1]*village_generators.Heat_Rate_MMBTU_per_MWh[g]
        # Start-up cost ($/start/MW) = start up O&M cost ($/start/MW) + fuel cost ($/MMBtu) * start up fuel use (MMBtu/start/MW) 
        village_generators.Start_Cost[g] = village_generators.Start_Cost_per_MW[g] +
            fuels[fuels.Fuel.==village_generators.Fuel[g],:Cost_per_MMBtu][1]*village_generators.Start_Fuel_MMBTU_per_MW[g]
        # Start-up CO2 emissions (tCO2/start/MW) = fuel CO2 content (tCO2/MMBtu) * start up fuel use (MMBtu/start/MW) 
        village_generators.CO2_Per_Start[g] = fuels[fuels.Fuel.==village_generators.Fuel[g],:CO2_content_tons_per_MMBtu][1]*village_generators.Start_Fuel_MMBTU_per_MW[g]
    end
    
    #SUBSET DEFINITIONS

    #subset of thermal generators that are subject to unit commitment constraints
    UC = intersect(generators.R_ID[generators.Commit.==1], G)
    
    #subset of generators that are not subject to unit commitment constraints
    ED = intersect(generators.R_ID[generators.Commit.==0], G)
    
    #subset of storage resources
    STOR = intersect(generators.R_ID[generators.STOR.>=1], G)
    
    #subset of variable renewable resources
    VRE = intersect(generators.R_ID[generators.VRE.==1], G)
    
    #subset of new build generators
    NEW = intersect(generators.R_ID[generators.New_Build.==1], G)
    
    #subset of existing generators
    OLD = intersect(generators.R_ID[.!(generators.New_Build.==1)], G)
    
    #subset of RPS qualifying resources
    #RPS = intersect(generators.R_ID[generators.RPS.==1], G);

    #subset of time steps that begin a sub period
    START = 1:hours_per_period:maximum(T)

    #subset of time periods that do not begin a sub period
    INTERIOR = setdiff(T, START)
    
    # Subset of all unit commitment generators
    UC_OLD = intersect(UC, OLD)
    
    # Subset of all new unit commitment generators
    UC_NEW = intersect(UC, NEW)
    
    # Subset of all oth2er old generators
    ED_OLD = intersect(ED, OLD)
    
    # Subset of all other new generators
    ED_NEW = intersect(ED, NEW);
    
    # Subset of all unit commitment generators
    UC_OLD = intersect(UC, OLD)
    
    # Subset of all new unit commitment generators
    UC_NEW = intersect(UC, NEW)
    
    # Subset of all other old generators
    ED_OLD = intersect(ED, OLD)
    
    # Subset of all other new generators
    ED_NEW = intersect(ED, NEW);

    # subset of VIL generators that are subject to unit commitment constraints
    VIL_UC = intersect(village_generators.R_ID[village_generators.Commit.==1], VIL_G)

    # subset of VIL generators that are not subject to unit commitment constraints
    VIL_ED = intersect(village_generators.R_ID[village_generators.Commit.==0], VIL_G)

    # subset of VIL generators that are RE + storage
    VIL_RE = intersect(village_generators.R_ID[.!(village_generators.Commit.==1)], VIL_G)

    # subset of new VIL generators
    VIL_NEW = intersect(village_generators.R_ID[village_generators.New_Build.==1], VIL_G)

    # subset of existing VIL generators
    VIL_OLD = intersect(village_generators.R_ID[.!(village_generators.New_Build.==1)], VIL_G)

    #subset of all old VIL UC generators
    VIL_UC_OLD = intersect(VIL_UC, VIL_OLD)

    #subset of all new VIL UC generators
    VIL_UC_NEW = intersect(VIL_UC, VIL_NEW)

    #subset of all old VIL ED generators
    VIL_ED_OLD = intersect(VIL_ED, VIL_OLD)

    #subset of all new VIL ED generators
    VIL_ED_NEW = intersect(VIL_ED, VIL_NEW)

    #subset of all VIL storage resources
    VIL_STOR = intersect(village_generators.R_ID[village_generators.STOR.==1], VIL_G)


    return (
        generators = generators,
        demand = demand,
        variability = variability,
        lines = lines,
        nse = nse,
        hours_per_period = hours_per_period,
        sample_weight = sample_weight,
        village_generators = village_generators,
        village_nse = nse_village,
        village_demand = village_demand,
        village_demandheat = village_demandheat,
        village_variability = village_variability,
        G = G,
        S = S,
        P = P,
        W = W,
        T = T,
        T_red = T_red,
        Z = Z,
        L = L,
        UC = UC,
        ED = ED,
        STOR = STOR,
        VRE = VRE,
        NEW = NEW,
        OLD = OLD,
        START = START,
        INTERIOR = INTERIOR,
        UC_OLD = UC_OLD,
        UC_NEW = UC_NEW,
        ED_OLD = ED_OLD,
        ED_NEW = ED_NEW,
        VIL_UC = VIL_UC,
        VIL_ED = VIL_ED,
        VIL_NEW = VIL_NEW,
        VIL_OLD = VIL_OLD,
        VIL_RE = VIL_RE,
        VIL = VIL,
        VIL_G = VIL_G,
        village_zone = village_zone,
        village_connect_cost = village_connect_cost,
        village_connect_max = village_connect_max,
        VIL_S = VIL_S,
        VIL_UC_OLD = VIL_UC_OLD,
        VIL_UC_NEW = VIL_UC_NEW,
        VIL_ED_OLD = VIL_ED_OLD,
        VIL_ED_NEW = VIL_ED_NEW,
        VIL_STOR = VIL_STOR
        )
    
end