function capacity_expansion(inputs, mipgap, CO2_constraint, CO2_limit, RE_constraint, RE_limit, Grid, VillageBuild, ImportPrice, NoCoal, CO235reduction, BAUCO2emissions; village_storage_max_mwh = 208.0)

    CE = Model(Gurobi.Optimizer)
    set_attribute(CE, "MIPGap", mipgap)
    #set_attribute(CE, "LogFile", "gurobi_output.log")
    set_attribute(CE, "Crossover", 0)
    #set_attribute(CE, "UnboundedRay", 1)
    #set_attribute(CE, "Nodes", 10)
    set_attribute(CE, "TimeLimit", 3*24*60*60)
    #set_attribute(CE, "Heuristics", 0)
    #set_attribute(CE, "Cuts", 3)

    #DECISION VARIABLES

    #Capacity decision variables
    @variables(CE, begin

        #standard capacity variables
        vCAP[g in inputs.G]                  >= 0 # power capacity (MW)
        vRET_CAP_ED[g in inputs.ED_OLD]      >= 0     # retirement of power capacity (MW)
        vNEW_CAP_ED[g in inputs.ED_NEW]      >= 0     # new build power capacity for (MW)

        vRET_CAP_UC[g in inputs.UC_OLD]            # retirement of power capacity for UC units (MW)
        vNEW_CAP_UC[g in inputs.UC_NEW]             # new build power capacity for UC units (MW)
            
        #storage variables
        vE_CAP[g in inputs.STOR]          >= 0 # storage energy capacity (MWh)
        vRET_E_CAP[g in intersect(inputs.STOR, inputs.OLD)]   >= 0 # retirement storage capacity
        vNEW_E_CAP[g in intersect(inputs.STOR, inputs.NEW)]   >= 0 # new build storage capacity

        #transmission variables
        vT_CAP[l in inputs.L]               >= 0 # transmission capacity (MW)
        vRET_T_CAP[l in inputs.L]           >= 0 # retirement transmission capacity (MW)
        vNEW_T_CAP[l in inputs.L]           >= 0 # new build transmission capacity (MW)
                
        vSTART[inputs.T, inputs.UC], Bin # start up units
        vSHUT[inputs.T, inputs.UC], Bin  # shut down units
        vCOMMIT[inputs.T, inputs.UC], Bin # commitment variable for UC units
    end)

    #unbounded till max_cap data is received
    for g in inputs.UC_NEW[inputs.generators[inputs.UC_NEW, :Max_Cap_MW].>0]
        set_upper_bound(vNEW_CAP_UC[g], inputs.generators.Max_Cap_MW[g])
    end

    for g in inputs.ED_NEW[inputs.generators[inputs.ED_NEW, :Max_Cap_MW].>0]
        set_upper_bound(vNEW_CAP_ED[g], inputs.generators.Max_Cap_MW[g])
    end

    #set upper bounds on transmission capacity expansion
    for l in inputs.L
        set_upper_bound(vNEW_T_CAP[l], inputs.lines.Line_Max_Reinforcement_MW[l])
    end

    #operational decision variables
    @variables(CE, begin
            vGEN[inputs.T, inputs.G]            >= 0 # power generation (MW)
            vCHARGE[inputs.T, inputs.STOR]     >= 0 # power charging (MW)
            vSOC[inputs.T, inputs.STOR]        >= 0 # energy storage state of charge (MW)
            vNSE[inputs.T, inputs.S, inputs.Z]  >= 0 # non-served energy/demand curtailment (MW)
            vFLOW[inputs.T, inputs.L]           >= 0 # transmission line flow (MW)
            # vTHETA[inputs.T, inputs.Z]          >= 0 # theta angle for transmission lines (radians)
    end)

    #village decision variables
    @variables(CE, begin
   
            vVIL_CAP[inputs.VIL_G]                                >= 0 #capacity of onsite power options
            vVIL_E_CAP[inputs.VIL_STOR]                          >= 0 #energy storage capacity (MWh)
            vVIL_RET_E_CAP[inputs.VIL_STOR]                      >= 0 #retirement of onsite storage units
            vVIL_NEW_E_CAP[inputs.VIL_STOR]                      >= 0 #new build onsite storage units

            vVIL_RET_CAP_ED[inputs.VIL_ED]                        >= 0 #retirement of onsite ED units
            vVIL_NEW_CAP_ED[inputs.VIL_ED]                        >= 0 #new build onsite ED units
            vVIL_RET_CAP_UC[inputs.VIL_UC]                        >= 0 #retirement of onsite UC units
            vVIL_NEW_CAP_UC[inputs.VIL_UC]                        >= 0 #new build onsite UC units

            vVIL_COMMIT[inputs.T, inputs.VIL_UC], Bin #commitment variable for onsite UC units
            vVIL_START[inputs.T, inputs.VIL_UC], Bin #start up variable for onsite UC units
            vVIL_SHUT[inputs.T, inputs.VIL_UC], Bin #shut down variable for onsite UC units
            #vVIL_CONNECT[inputs.VIL], Bin #binary variable for grid connection 
    end)

    #operational decision variables for industrial
    @variables(CE, begin
            vVIL_GEN[inputs.T, inputs.VIL_G]                      >= 0 #generation of onsite power options
            vVIL_GEN_HEAT[inputs.T, inputs.VIL_G]                 >= 0 #generation of onsite heat options
            vVIL_SOC[inputs.T, inputs.VIL_STOR]                   >= 0 #energy storage state of charge (MW)
            vVIL_CHARGE[inputs.T, inputs.VIL_STOR]                >= 0 #power charging (MW)
            vVIL_NSE[inputs.T, inputs.S, inputs.VIL]              >= 0 #non-served energy for villages
            vVIL_NSE_HEAT[inputs.T, inputs.S, inputs.VIL]         >= 0 #non-served energy for villages
    end)

    if Grid
        @variables(CE, begin
            vVIL_IMPORT[inputs.T, inputs.VIL]  >= 0  #grid import for the villages
            vVIL_EXPORT[inputs.T, inputs.VIL]  >= 0  #grid export (surplus solar) from the villages
            vVIL_CONNECT[inputs.VIL], Bin            #1 = village is connected to the grid
        end)
        #a village can only import from / export to the grid if it is connected;
        #import/export are also capped by its interconnection capacity.
        @constraints(CE, begin
            cVILImportConnect[t in inputs.T, vil in inputs.VIL],
                vVIL_IMPORT[t,vil] <= inputs.village_connect_max[vil]*vVIL_CONNECT[vil]
            cVILExportConnect[t in inputs.T, vil in inputs.VIL],
                vVIL_EXPORT[t,vil] <= inputs.village_connect_max[vil]*vVIL_CONNECT[vil]
        end)
    end

    # Per-village land/resource ceiling on new-build onsite capacity.
    # Max_Cap_MW == 0 means unbounded (no land data); a positive value caps the
    # new build, e.g. the developable-solar MW from the GIS resource assessment
    # (tools/resource_siting.py -> village solar Max_Cap_MW). Solar is Commit=0
    # so it lives in VIL_ED_NEW; the UC loop covers any committed onsite unit.
    for g in inputs.VIL_UC_NEW[inputs.village_generators[inputs.VIL_UC_NEW, :Max_Cap_MW].>0]
        set_upper_bound(vVIL_NEW_CAP_UC[g], inputs.village_generators.Max_Cap_MW[g])
    end

    for g in inputs.VIL_ED_NEW[inputs.village_generators[inputs.VIL_ED_NEW, :Max_Cap_MW].>0]
        set_upper_bound(vVIL_NEW_CAP_ED[g], inputs.village_generators.Max_Cap_MW[g])
    end

    for g in intersect(inputs.VIL_STOR, inputs.VIL_NEW)
        set_upper_bound(vVIL_NEW_E_CAP[g], village_storage_max_mwh)
    end


    

    #CONSTRAINTS
    if Grid
        #Supply Demand Balance Constraint
        @constraint(CE, cDemandBalance[t in inputs.T, z in inputs.Z], 
        sum(vGEN[t,g] for g in intersect(inputs.generators[inputs.generators.Zone.==z,:R_ID],inputs.G)) +
        sum(vNSE[t,s,z] for s in inputs.S) - 
        sum(vCHARGE[t,g] for g in intersect(inputs.generators[inputs.generators.Zone.==z,:R_ID],inputs.STOR)) -
        inputs.demand[t,z] - 
        sum(inputs.lines[l,Symbol(string("z",z))] * vFLOW[t,l] for l in inputs.L) -
        sum(vVIL_IMPORT[t,vil] for vil in inputs.VIL if inputs.village_zone[vil] == z) +
        sum(vVIL_EXPORT[t,vil] for vil in inputs.VIL if inputs.village_zone[vil] == z) == 0
        )
    else
        #Supply Demand Balance Constraint
        @constraint(CE, cDemandBalance[t in inputs.T, z in inputs.Z], 
        sum(vGEN[t,g] for g in intersect(inputs.generators[inputs.generators.Zone.==z,:R_ID],inputs.G)) +
        sum(vNSE[t,s,z] for s in inputs.S) - 
        sum(vCHARGE[t,g] for g in intersect(inputs.generators[inputs.generators.Zone.==z,:R_ID],inputs.STOR)) -
        inputs.demand[t,z] - 
        sum(inputs.lines[l,Symbol(string("z",z))] * vFLOW[t,l] for l in inputs.L) == 0
        )
    end

    
    
    
    #capacitated constraints
    @constraints(CE, begin

            #max power constraint for ED generators
            cMaxPowerED[t in inputs.T, g in inputs.ED], vGEN[t,g] <= inputs.variability[t,g]*vCAP[g]
            
            #max power constraints for UC generators
            cMaxPowerUC[t in inputs.T, g in inputs.UC], vGEN[t,g] <= inputs.generators.Existing_Cap_MW[g]*vCOMMIT[t,g]

            #min power constraints for UC generators
            cMinPowerUC[t in inputs.T, g in inputs.UC], vGEN[t,g] >=   
                inputs.generators.Min_Power_MW[g]*inputs.generators.Existing_Cap_MW[g]*vCOMMIT[t,g]
            
            #max charge constraint
            cMaxCharge[t in inputs.T, g in inputs.STOR], vCHARGE[t,g] <= vCAP[g]
            
            #max state of charge constraint
            cMaxSOC[t in inputs.T, g in inputs.STOR], vSOC[t,g] <= vE_CAP[g]
            
            #max NSE constraint
            cMaxNSE[t in inputs.T, s in inputs.S, z in inputs.Z], vNSE[t,s,z] <= 
                inputs.nse.NSE_Max[s]*inputs.demand[t,z]
            
            #max flow constraint
            cMaxFlow[t in inputs.T, l in inputs.L], vFLOW[t,l] <= vT_CAP[l]
            
            #min flow constraint
            cMinFlow[t in inputs.T, l in inputs.L], vFLOW[t,l] >= -vT_CAP[l]        
        end);

    #total capacity constraint
    @constraints(CE, begin

            #total capacity for exisiting ED units
            cCapOld[g in inputs.ED_OLD], vCAP[g] == inputs.generators.Existing_Cap_MW[g] - vRET_CAP_ED[g]

            #total capacity for new ED units
            cCapNew[g in inputs.ED_NEW], vCAP[g] == vNEW_CAP_ED[g]

            #total capacity for old UC units
            cCapOldUC[g in inputs.UC_OLD], vCAP[g] == inputs.generators.Existing_Cap_MW[g] - 
            vRET_CAP_UC[g]
        
            #total capacity for new UC units
            cCapNewUC[g in inputs.UC_NEW], vCAP[g] == vNEW_CAP_UC[g]

            #total energy storage capacity for existing units
            cCapEnergyOld[g in intersect(inputs.STOR, inputs.OLD)], 
                vE_CAP[g] == inputs.generators.Existing_Cap_MWh[g] - vRET_E_CAP[g]

            #total energy storage capacity for new units
            cCapEnergyNew[g in intersect(inputs.STOR, inputs.NEW)], 
                vE_CAP[g] == vNEW_E_CAP[g]

            #total transmission capacity
            cTransCap[l in inputs.L], vT_CAP[l] == inputs.lines.Line_Max_Flow_MW[l] - vRET_T_CAP[l] + vNEW_T_CAP[l]       
            
            # #setting reference bus for transmission lines
            # cThetaRef[t in inputs.T, z in inputs.Z], vTHETA[t,1] == 0
            
        end);

        # #DC power flow constraint
        # @constraint(CE, cDCPowerFlow[t in inputs.T, l in inputs.L],
        #    vFLOW[t,l] == (inputs.lines[l,:B] / inputs.lines[l,:distance_km]) * sum(inputs.lines[l,Symbol(string("z",i))] * vTHETA[t,i] for i in inputs.Z)
        # );

    # ramp, min up, min down, and storage constraints
    @constraints(CE, begin

            #ramp up for ED units, normal
            cRampUp[t in inputs.INTERIOR, g in inputs.ED],
                vGEN[t,g] - vGEN[t-1,g] <= inputs.generators.Ramp_Up_Percentage[g]*vCAP[g]

            #ramp up for ED units, sub-period wrapping
            cRampUpWrap[t in inputs.START, g in inputs.ED],
                vGEN[t,g] - vGEN[t+inputs.hours_per_period-1,g] <= inputs.generators.Ramp_Up_Percentage[g]*vCAP[g]

            #ramp up constraints for UC units, normal
            cRampUpUC[t in inputs.INTERIOR, g in inputs.UC],
                vGEN[t,g] - vGEN[t-1,g] <= 
                inputs.generators.Ramp_Up_Percentage[g]*inputs.generators.Existing_Cap_MW[g]*(vCOMMIT[t,g] - vSTART[t,g]) +
                max(inputs.generators.Min_Power_MW[g], 
                inputs.generators.Ramp_Up_Percentage[g])*inputs.generators.Existing_Cap_MW[g]*vSTART[t,g] - 
                inputs.generators.Min_Power_MW[g]*inputs.generators.Existing_Cap_MW[g]*vSHUT[t,g]

            #ramp up constraints for UC units, sub-period wrapping
            cRampUpWrapUC[t in inputs.START, g in inputs.UC],    
                vGEN[t,g] - vGEN[t+inputs.hours_per_period-1,g] <= 
                inputs.generators.Ramp_Up_Percentage[g]*inputs.generators.Existing_Cap_MW[g]*(vCOMMIT[t,g] - vSTART[t,g]) +
                max(inputs.generators.Min_Power_MW[g], 
                inputs.generators.Ramp_Up_Percentage[g])*inputs.generators.Existing_Cap_MW[g]*vSTART[t,g] - 
                inputs.generators.Min_Power_MW[g]*inputs.generators.Existing_Cap_MW[g]*vSHUT[t,g]
        
            #ramp down for ED units, normal
            cRampDown[t in inputs.INTERIOR, g in inputs.ED],
                vGEN[t-1,g] - vGEN[t,g] <= inputs.generators.Ramp_Dn_Percentage[g]*vCAP[g]

            #ramp down for ED units, sub-period warping
            cRampDownWrap[t in inputs.START, g in inputs.ED],
                vGEN[t+inputs.hours_per_period-1,g] - vGEN[t,g] <= inputs.generators.Ramp_Dn_Percentage[g]*vCAP[g]
 
            #ramp down constraints for UC units, normal
            cRampDownUC[t in inputs.INTERIOR, g in inputs.UC],
                vGEN[t-1,g] - vGEN[t,g] <= 
                inputs.generators.Ramp_Dn_Percentage[g]*inputs.generators.Existing_Cap_MW[g]*(vCOMMIT[t,g] - vSTART[t,g]) +
                max(inputs.generators.Min_Power_MW[g], 
                inputs.generators.Ramp_Dn_Percentage[g])*inputs.generators.Existing_Cap_MW[g]*vSHUT[t,g] - 
                inputs.generators.Min_Power_MW[g]*inputs.generators.Existing_Cap_MW[g]*vSTART[t,g]

            #ramp down constraints for UC units, sub-period wrapping
            cRampDownWrapUC[t in inputs.START, g in inputs.UC],    
                vGEN[t+inputs.hours_per_period-1,g] - vGEN[t,g] <= 
                inputs.generators.Ramp_Dn_Percentage[g]*inputs.generators.Existing_Cap_MW[g]*
                (vCOMMIT[t,g] - vSTART[t,g]) +
                max(inputs.generators.Min_Power_MW[g], inputs.generators.Ramp_Dn_Percentage[g])*
                inputs.generators.Existing_Cap_MW[g]*vSHUT[t,g] - 
                inputs.generators.Min_Power_MW[g]*inputs.generators.Existing_Cap_MW[g]*vSTART[t,g]

            #minimum up constraints
            cUpTime[t in inputs.T, g in inputs.UC],
                vCOMMIT[t,g] >= sum(vSTART[tt, g]
                                for tt in intersect(inputs.T,
                                (t-inputs.generators.Up_Time[g]:t)))
            #minimum down constraints
            cDownTime[t in inputs.T, g in inputs.UC],
                vCAP[g] / inputs.generators.Existing_Cap_MW[g] >= sum(vSHUT[tt, g]
                                                            for tt in intersect(inputs.T,
                                                            (t-inputs.generators.Down_Time[g]:t)))

            #storage state of charge, normal
            cSOC[t in inputs.INTERIOR, g in inputs.STOR],
                vSOC[t,g] == vSOC[t-1,g] + inputs.generators.Eff_Up[g]*vCHARGE[t,g] - 
                vGEN[t,g]/inputs.generators.Eff_Down[g]

            #storage state of charge, sub-period warping
            cSOCWrap[t in inputs.START, g in inputs.STOR], 
                vSOC[t,g] == vSOC[t+inputs.hours_per_period-1,g] + inputs.generators.Eff_Up[g]*vCHARGE[t,g] - 
                vGEN[t,g]/inputs.generators.Eff_Down[g]

    
        end);

    #state variables
    @constraints(CE, begin
            
            #upper bound commit constraints
            cCommitBound[t in inputs.T, g in inputs.UC],
                vCOMMIT[t,g] <= vCAP[g] / inputs.generators.Existing_Cap_MW[g]

            #upper bound start constraints
            cStartBound[t in inputs.T, g in inputs.UC],
                vSTART[t,g] <= vCAP[g] / inputs.generators.Existing_Cap_MW[g]

            #upper bound shut constraints
            cShutBound[t in inputs.T, g in inputs.UC],
                vSHUT[t,g] <= vCAP[g] / inputs.generators.Existing_Cap_MW[g]

            #define the commit variable
            cCommitState[t in inputs.T_red, g in inputs.UC],
                vCOMMIT[t+1,g] == vCOMMIT[t,g] + vSTART[t+1,g] - vSHUT[t+1,g]

        end);



    #village constraints - demand balance
    #demand balance for villages - heat
    @constraints(CE, begin
            cVILHeatBalance[t in inputs.T, vil in inputs.VIL],
            sum(vVIL_GEN_HEAT[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_UC)) +
            sum(vVIL_NSE_HEAT[t,s,vil] for s in inputs.VIL_S) -  
            inputs.village_demandheat[t,vil] == 0
        end);

    #demand balance for villages - electricity
    if Grid
        if NoCoal
            @constraints(CE, begin
                cVILElectricityBalance[t in inputs.T, vil in inputs.VIL], 
                sum(vVIL_GEN[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_RE)) +
                sum(vVIL_IMPORT[t,vil]) +
                sum(vVIL_NSE[t,s,vil] for s in inputs.VIL_S) -
                sum(vVIL_CHARGE[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_STOR)) -
                sum(vVIL_EXPORT[t,vil]) -
                inputs.village_demand[t,vil] == 0
            end);

        elseif VillageBuild
            @constraints(CE, begin
                cVILElectricityBalance[t in inputs.T, vil in inputs.VIL], 
                sum(vVIL_GEN[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_G)) +
                sum(vVIL_IMPORT[t,vil]) +
                sum(vVIL_NSE[t,s,vil] for s in inputs.VIL_S) -
                sum(vVIL_CHARGE[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_STOR)) -
                sum(vVIL_EXPORT[t,vil]) -
                inputs.village_demand[t,vil] == 0
            end);

        else
            @constraints(CE, begin
                cVILElectricityBalance[t in inputs.T, vil in inputs.VIL], 
                sum(vVIL_GEN[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_UC)) +
                sum(vVIL_IMPORT[t,vil]) +
                sum(vVIL_NSE[t,s,vil] for s in inputs.VIL_S) -
                sum(vVIL_EXPORT[t,vil]) -
                inputs.village_demand[t,vil] == 0
            end);
        end
    else
        if NoCoal
            @constraints(CE, begin
                cVILElectricityBalance[t in inputs.T, vil in inputs.VIL], 
                sum(vVIL_GEN[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_RE)) +
                sum(vVIL_NSE[t,s,vil] for s in inputs.VIL_S) -
                sum(vVIL_CHARGE[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_STOR)) -
                # include export variable here -
                inputs.village_demand[t,vil] == 0
            end);

        elseif VillageBuild
            @constraints(CE, begin
                cVILElectricityBalance[t in inputs.T, vil in inputs.VIL], 
                sum(vVIL_GEN[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_G)) +
                sum(vVIL_NSE[t,s,vil] for s in inputs.VIL_S) -
                sum(vVIL_CHARGE[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_STOR)) -
                # include export variable here -
                inputs.village_demand[t,vil] == 0
            end);

        else
            @constraints(CE, begin
                cVILElectricityBalance[t in inputs.T, vil in inputs.VIL], 
                sum(vVIL_GEN[t,g] for g in intersect(inputs.village_generators[inputs.village_generators.Village.==vil,:R_ID],inputs.VIL_UC)) + 
                sum(vVIL_NSE[t,s,vil] for s in inputs.VIL_S) -
                # include export variable here -
                inputs.village_demand[t,vil] == 0
            end);
        end
    end

    #village capacity constraints
    @constraints(CE, begin

            #capacity for existing ED units
            cVILEdOld[g in inputs.VIL_ED_OLD], 
                vVIL_CAP[g] == inputs.village_generators.Existing_Cap_MW[g] - vVIL_RET_CAP_ED[g]

            #capacity for new ED units
            cVILEdNew[g in inputs.VIL_ED_NEW], 
                vVIL_CAP[g] == vVIL_NEW_CAP_ED[g]

            #capacity for existing UC units
            cVILUcOld[g in inputs.VIL_UC_OLD], 
                vVIL_CAP[g] == inputs.village_generators.Existing_Cap_MW[g] - vVIL_RET_CAP_UC[g]

            #capacity for new UC units
            cVILUcNew[g in inputs.VIL_UC_NEW], 
                vVIL_CAP[g] == vVIL_NEW_CAP_UC[g]

            #max charge constraint
            cVILMaxCharge[t in inputs.T, g in inputs.VIL_STOR], vVIL_CHARGE[t,g] <= vVIL_CAP[g]
            
            #max state of charge constraint
            cVILMaxSOC[t in inputs.T, g in inputs.VIL_STOR], vVIL_SOC[t,g] <= vVIL_E_CAP[g]

            #total energy storage capacity for existing units
            cVILCapEnergyOld[g in intersect(inputs.VIL_STOR, inputs.VIL_OLD)], 
                vVIL_E_CAP[g] == inputs.village_generators.Existing_Cap_MWh[g] - vVIL_RET_E_CAP[g]

            #total energy storage capacity for new units
            cVILCapEnergyNew[g in intersect(inputs.VIL_STOR, inputs.VIL_NEW)], 
                vVIL_E_CAP[g] == vVIL_NEW_E_CAP[g]

            #NSE constraints for villages electricity
            cVILNSE[t in inputs.T, s in inputs.VIL_S, vil in inputs.VIL], 
                vVIL_NSE[t,s,vil] <= inputs.village_nse.NSE_Max[s]*inputs.village_demand[t,vil]

            #NSE constraints for villages heat
            cVILNSEHeat[t in inputs.T, s in inputs.VIL_S, vil in inputs.VIL], 
                vVIL_NSE_HEAT[t,s,vil] <= inputs.village_nse.NSE_Max[s]*inputs.village_demandheat[t,vil]

        end);

    #village capacity constraints
    @constraints(CE, begin

            #max power constraint for ED generators
            cVILEdMaxPower[t in inputs.T, g in inputs.VIL_ED], 
            vVIL_GEN[t,g] <= inputs.village_variability[t,g]*vVIL_CAP[g]

            #max power constraints for UC generators
            cVILUcMaxPower[t in inputs.T, g in inputs.VIL_UC], 
                (vVIL_GEN_HEAT[t,g] + vVIL_GEN[t,g]) <= inputs.village_generators.Existing_Cap_MW[g]*vVIL_COMMIT[t,g]

            #min power constraints for UC generators
            cVILUcMinPower[t in inputs.T, g in inputs.VIL_UC], 
                (vVIL_GEN[t,g] + vVIL_GEN_HEAT[t,g]) >=   
                inputs.village_generators.Min_Power_MW[g]*inputs.village_generators.Existing_Cap_MW[g]*vVIL_COMMIT[t,g]
            
        end);

    #village ramp, min up, min down, and storage constraints
    @constraints(CE, begin

            #ramp up for ED units, normal
            cVILRampUp[t in inputs.INTERIOR, g in inputs.VIL_ED],
                vVIL_GEN[t,g] - vVIL_GEN[t-1,g] <= 
                inputs.village_generators.Ramp_Up_Percentage[g]*vVIL_CAP[g]

            #ramp up for ED units, sub-period wrapping
            cVILRampUpWrap[t in inputs.START, g in inputs.VIL_ED],
                vVIL_GEN[t,g] - vVIL_GEN[t+inputs.hours_per_period-1,g]  <= 
                inputs.village_generators.Ramp_Up_Percentage[g]*vVIL_CAP[g]

            #ramp up constraints for UC units, normal
            cVILRampUpUC[t in inputs.INTERIOR, g in inputs.VIL_UC],
                (vVIL_GEN[t,g] + vVIL_GEN_HEAT[t,g]) - (vVIL_GEN[t-1,g] + vVIL_GEN_HEAT[t-1,g]) <= 
                inputs.village_generators.Ramp_Up_Percentage[g]*inputs.village_generators.Existing_Cap_MW[g]*(vVIL_COMMIT[t,g] - vVIL_START[t,g]) +
                max(inputs.village_generators.Min_Power_MW[g], 
                inputs.village_generators.Ramp_Up_Percentage[g])*inputs.village_generators.Existing_Cap_MW[g]*vVIL_START[t,g] - 
                inputs.village_generators.Min_Power_MW[g]*inputs.village_generators.Existing_Cap_MW[g]*vVIL_SHUT[t,g]

            #ramp up constraints for UC units, sub-period wrapping
            cVILRampUpWrapUC[t in inputs.START, g in inputs.VIL_UC],    
                (vVIL_GEN[t,g] + vVIL_GEN_HEAT[t,g]) - (vVIL_GEN[t+inputs.hours_per_period-1,g] + vVIL_GEN_HEAT[t+inputs.hours_per_period-1,g]) <= 
                inputs.village_generators.Ramp_Up_Percentage[g]*inputs.village_generators.Existing_Cap_MW[g]*(vVIL_COMMIT[t,g] - vVIL_START[t,g]) +
                max(inputs.village_generators.Min_Power_MW[g], 
                inputs.village_generators.Ramp_Up_Percentage[g])*inputs.village_generators.Existing_Cap_MW[g]*vVIL_START[t,g] - 
                inputs.village_generators.Min_Power_MW[g]*inputs.village_generators.Existing_Cap_MW[g]*vVIL_SHUT[t,g]

            #ramp down for ED units, normal
            cVILRampDown[t in inputs.INTERIOR, g in inputs.VIL_ED],
                vVIL_GEN[t-1,g] - vVIL_GEN[t,g] <= inputs.village_generators.Ramp_Dn_Percentage[g]*vVIL_CAP[g]

            #ramp down for ED units, sub-period warping
            cVILRampDownWrap[t in inputs.START, g in inputs.VIL_ED],
                vVIL_GEN[t+inputs.hours_per_period-1,g] - vVIL_GEN[t,g] <= inputs.village_generators.Ramp_Dn_Percentage[g]*vVIL_CAP[g]

            #ramp down constraints for UC units, normal
            cVILRampDownUC[t in inputs.INTERIOR, g in inputs.VIL_UC],
                (vVIL_GEN[t-1,g] + vVIL_GEN_HEAT[t-1,g]) - (vVIL_GEN[t,g] + vVIL_GEN_HEAT[t,g]) <= 
                inputs.village_generators.Ramp_Dn_Percentage[g]*inputs.village_generators.Existing_Cap_MW[g]*(vVIL_COMMIT[t,g] - vVIL_START[t,g]) +
                max(inputs.village_generators.Min_Power_MW[g], 
                inputs.village_generators.Ramp_Dn_Percentage[g])*inputs.village_generators.Existing_Cap_MW[g]*vVIL_SHUT[t,g] - 
                inputs.village_generators.Min_Power_MW[g]*inputs.village_generators.Existing_Cap_MW[g]*vVIL_START[t,g]

            #ramp down constraints for UC units, sub-period wrapping
            cVILRampDownWrapUC[t in inputs.START, g in inputs.VIL_UC],    
                (vVIL_GEN[t+inputs.hours_per_period-1,g] + vVIL_GEN_HEAT[t+inputs.hours_per_period-1,g]) - (vVIL_GEN[t,g] + vVIL_GEN_HEAT[t,g]) <= 
                inputs.village_generators.Ramp_Dn_Percentage[g]*inputs.village_generators.Existing_Cap_MW[g]*(vVIL_COMMIT[t,g] - vVIL_START[t,g]) +
                max(inputs.village_generators.Min_Power_MW[g], 
                inputs.village_generators.Ramp_Dn_Percentage[g])*inputs.village_generators.Existing_Cap_MW[g]*vVIL_SHUT[t,g] - 
                inputs.village_generators.Min_Power_MW[g]*inputs.village_generators.Existing_Cap_MW[g]*vVIL_START[t,g]
                
            #minimum up constraints
            cVILUpTime[t in inputs.T, g in inputs.VIL_UC],
                vVIL_COMMIT[t,g] >= sum(vVIL_START[tt,g]
                                for tt in intersect(inputs.T,
                                (t-inputs.village_generators.Up_Time[g]:t)))
            #minimum down constraints
            cVILDownTime[t in inputs.T, g in inputs.VIL_UC],
                vVIL_CAP[g] / inputs.village_generators.Existing_Cap_MW[g] >= sum(vVIL_SHUT[tt,g]
                                                            for tt in intersect(inputs.T,
                                                            (t-inputs.village_generators.Down_Time[g]:t)))
            #storage state of charge, normal
            cVILSOC[t in inputs.INTERIOR, g in inputs.VIL_STOR],
                vVIL_SOC[t,g] == vVIL_SOC[t-1,g] + inputs.village_generators.Eff_Up[g]*vVIL_CHARGE[t,g] -
                vVIL_GEN[t,g]/inputs.village_generators.Eff_Down[g]

            #storage state of charge, sub-period warping
            cVILSOCWrap[t in inputs.START, g in inputs.VIL_STOR],
                vVIL_SOC[t,g] == vVIL_SOC[t+inputs.hours_per_period-1,g] + inputs.village_generators.Eff_Up[g]*vVIL_CHARGE[t,g] -
                vVIL_GEN[t,g]/inputs.village_generators.Eff_Down[g]
        end);

    #village state variables
    @constraints(CE, begin
            
            #upper bound commit constraints
            cVILCommitBound[t in inputs.T, g in inputs.VIL_UC],
                vVIL_COMMIT[t,g] <= vVIL_CAP[g] / inputs.village_generators.Existing_Cap_MW[g]

            #upper bound start constraints
            cVILStartBound[t in inputs.T, g in inputs.VIL_UC],
                vVIL_START[t,g] <= vVIL_CAP[g] / inputs.village_generators.Existing_Cap_MW[g]

            #upper bound shut constraints
            cVILShutBound[t in inputs.T, g in inputs.VIL_UC],
                vVIL_SHUT[t,g] <= vVIL_CAP[g] / inputs.village_generators.Existing_Cap_MW[g]

            #define the commit variable
            cVILCommitState[t in inputs.T_red, g in inputs.VIL_UC],
                vVIL_COMMIT[t+1,g] == vVIL_COMMIT[t,g] + vVIL_START[t+1,g] - vVIL_SHUT[t+1,g]

        end);


    # clean energy constraints

    #CO2 emissions
    @expression(CE, eCO2EmissionsGrid,
    (sum(inputs.sample_weight[t]*inputs.generators.CO2_Rate[g]*vGEN[t,g] for t in inputs.T, g in inputs.G) +
    sum(inputs.sample_weight[t]*inputs.generators.CO2_Per_Start[g]*vSTART[t,g] for t in inputs.T, g in inputs.UC))
    );

    @expression(CE, eCO2EmissionsVIL,
    (sum(inputs.sample_weight[t]*inputs.village_generators.CO2_Rate[g]*(vVIL_GEN[t,g] + vVIL_GEN_HEAT[t,g]) for t in inputs.T, g in inputs.VIL_UC) +
    sum(inputs.sample_weight[t]*inputs.village_generators.CO2_Per_Start[g]*vVIL_START[t,g] for t in inputs.T, g in inputs.VIL_UC))
    );
    
    
    if CO2_constraint
        #setting CO2 emissions constraint to 290 as per JETP agreement
        @constraint(CE, cCO2EmissionsGrid, eCO2EmissionsGrid <= CO2_limit);
    end

    if CO235reduction
        #setting CO2 emissions constraint to 235 as per JETP agreement
        @constraint(CE, cCO2EmissionsVIL,  eCO2EmissionsVIL <= 0.65*BAUCO2emissions);
    end

    #renewable energy share
    @expression(CE, eREShare, 
    (sum(inputs.sample_weight[t]*inputs.generators.RE[g]*vGEN[t,g] for t in inputs.T, g in inputs.G) /
    sum(inputs.sample_weight[t]*inputs.demand[t,z] for t in inputs.T, z in inputs.Z))
    );
    
    if RE_constraint
        #setting renewable energy share constraint to 34% as per JETP agreement
        @constraint(CE, cREShare, eREShare >= RE_limit);
    end

    #OBJECTIVE FUNCTION
    
    #fixed cost for generation
    @expression(CE, eFixedCostsGeneration,
        #fixed costs for total capacity
        sum(inputs.generators.Fixed_OM_Cost_per_MWyr[g]*vCAP[g] for g in inputs.G) +
        # Investment cost for new ED capacity
        sum(inputs.generators.Inv_Cost_per_MWyr[g]*vNEW_CAP_ED[g] for g in inputs.ED_NEW) + 
         # Investment cost for new UC capacity
        sum(inputs.generators.Inv_Cost_per_MWyr[g]*vNEW_CAP_UC[g] for g in inputs.UC_NEW)
        );

    #fixed cost for village generation
    @expression(CE, eFixedCostsVILGeneration,
        #fixed costs for total capacity
        sum(inputs.village_generators.Fixed_OM_Cost_per_MWyr[g]*vVIL_CAP[g] for g in inputs.VIL_G) +
        # Investment cost for new ED capacity
        sum(inputs.village_generators.Inv_Cost_per_MWyr[g]*vVIL_NEW_CAP_ED[g] for g in inputs.VIL_ED) + 
         # Investment cost for new UC capacity
        sum(inputs.village_generators.Inv_Cost_per_MWyr[g]*vVIL_NEW_CAP_UC[g] for g in inputs.VIL_UC)
        );
    
    #fixed cost for storage
    @expression(CE, eFixedCostsStorage,
        #fixed costs for total storage capacity
        sum(inputs.generators.Fixed_OM_Cost_per_MWhyr[g]*vE_CAP[g] for g in inputs.STOR) + 
        #investment costs for new storage energy capacity
        sum(inputs.generators.Inv_Cost_per_MWhyr[g]*vNEW_E_CAP[g] for g in intersect(inputs.STOR, inputs.NEW))
        );

    #fixed cost for storage
    @expression(CE, eVILFixedCostsStorage,
        #fixed costs for total storage capacity
        sum(inputs.village_generators.Fixed_OM_Cost_per_MWhyr[g]*vVIL_E_CAP[g] for g in inputs.VIL_STOR) + 
        #investment costs for new storage energy capacity
        sum(inputs.village_generators.Inv_Cost_per_MWhyr[g]*vVIL_NEW_E_CAP[g] for g in intersect(inputs.VIL_STOR, inputs.VIL_NEW))
        );
    
    #fixed cost for transmission
    @expression(CE, eFixedCostsTransmission,
     # Investment and fixed O&M costs for transmission lines
        sum(inputs.lines.Line_Fixed_Cost_per_MW_yr[l]*vT_CAP[l] +
            inputs.lines.Line_Reinforcement_Cost_per_MWyr[l]*vNEW_T_CAP[l] for l in inputs.L)
        );

    #variable costs for grid generators
    @expression(CE, eVariableCostsGrid,
        # Variable costs for generation, weighted by hourly sample weight 
        sum(inputs.sample_weight[t]*inputs.generators.Var_Cost[g]*vGEN[t,g] for t in inputs.T, g in inputs.G)
        );

    #variable costs for village ED generators
    @expression(CE, eVariableCostsVILED,
        # Variable costs for generation, weighted by hourly sample weight 
        sum(inputs.sample_weight[t]*inputs.village_generators.Var_Cost[g]*vVIL_GEN[t,g] for t in inputs.T, g in inputs.VIL_ED)
        );

    #variable costs for village UC generators
    @expression(CE, eVariableCostsVILUC,
        # Variable costs for generation, weighted by hourly sample weight 
        sum(inputs.sample_weight[t]*inputs.village_generators.Var_Cost[g]*(vVIL_GEN[t,g] + vVIL_GEN_HEAT[t,g]) for t in inputs.T, g in inputs.VIL_UC)
        );

    #NSE costs for grid
    @expression(CE, eNSECosts,
     # Non-served energy costs, weighted by hourly sample weight to ensure non-served energy costs estimate annual costs
    sum(inputs.sample_weight[t]*inputs.nse.NSE_Cost[s]*vNSE[t,s,z] for t in inputs.T, s in inputs.S, z in inputs.Z)
        );

    #NSE costs for village
    @expression(CE, eVILNSECosts,
        # Non-served energy costs, weighted by hourly sample weight to ensure non-served energy costs estimate annual costs
        sum(inputs.sample_weight[t]*inputs.village_nse.NSE_Cost[s]*vVIL_NSE[t,s,vil] for t in inputs.T, s in inputs.S, vil in inputs.VIL)
        );

    #NSE costs for village heat
    @expression(CE, eVILNSEHeatCosts,
         # Non-served energy costs, weighted by hourly sample weight to ensure non-served energy costs estimate annual costs
        sum(inputs.sample_weight[t]*inputs.village_nse.NSE_Cost[s]*vVIL_NSE_HEAT[t,s,vil] for t in inputs.T, s in inputs.S, vil in inputs.VIL)
        );


    #start costs for grid generators
    @expression(CE, eStartCostsGrid,
    sum(inputs.sample_weight[t]*inputs.generators.Start_Cost[g]*vSTART[t,g]*inputs.generators.Existing_Cap_MW[g] 
            for t in inputs.T, g in inputs.UC)
        );
    
    #start costs for village generators
    @expression(CE, eStartCostsVIL,
    sum(inputs.sample_weight[t]*inputs.village_generators.Start_Cost[g]*vVIL_START[t,g]*inputs.village_generators.Existing_Cap_MW[g] 
            for t in inputs.T, g in inputs.VIL_UC)
        );
    
    if Grid
        #grid import costs
        @expression(CE, eGridImportCosts,
            sum(inputs.sample_weight[t]*ImportPrice*vVIL_IMPORT[t,vil] for t in inputs.T, vil in inputs.VIL) #change import cost to a constant value
        );
    else
        @expression(CE, eGridImportCosts,
            0
        );
    end

    # annualised cost of connecting villages to the grid (co-optimised decision)
    if Grid
        @expression(CE, eVILConnectCost,
            sum(inputs.village_connect_cost[vil]*vVIL_CONNECT[vil] for vil in inputs.VIL)
        );
    else
        @expression(CE, eVILConnectCost, 0);
    end

    @expression(CE, eCostObjective,
    eFixedCostsGeneration + eFixedCostsVILGeneration + 
    eFixedCostsStorage + eVILFixedCostsStorage +
    eFixedCostsTransmission + eGridImportCosts + eVILConnectCost +
    eVariableCostsGrid + eVariableCostsVILED + eVariableCostsVILUC +
    eNSECosts + eVILNSECosts + eVILNSEHeatCosts +
    eStartCostsGrid + eStartCostsVIL
        );
    
    @objective(CE, Min, eCostObjective);


    optimize!(CE)

    # … after you build CE …
    #report_unbounded_continuous(CE)

    if termination_status(CE) == MOI.OPTIMAL
        println("The model solved successfully.")
    elseif termination_status(CE) == MOI.TIME_LIMIT
        println("The model reached the time limit.")
    elseif termination_status(CE) == MOI.INFEASIBLE
        println("The model is infeasible.")
    else
        println("The model did not solve successfully. Termination status: ", termination_status(CE))
    end

    if Grid
        VIL_IMPORT = vVIL_IMPORT
        VIL_EXPORT = vVIL_EXPORT
        VIL_CONNECT = vVIL_CONNECT
    else
        VIL_IMPORT = 0
        VIL_EXPORT = 0
        VIL_CONNECT = 0
    end

    VIL_E_CAP = vVIL_E_CAP

    return (
        CAP = vCAP,
        GEN = vGEN,
        E_CAP = vE_CAP,
        VIL_CAP = vVIL_CAP,
        VIL_E_CAP = VIL_E_CAP,
        VIL_GEN = vVIL_GEN,
        VIL_GEN_HEAT = vVIL_GEN_HEAT,
        VIL_IMPORT = VIL_IMPORT,
        VIL_EXPORT = VIL_EXPORT,
        VIL_CONNECT = VIL_CONNECT,
        FLOW = vFLOW,
        T_CAP = vT_CAP,
        NSE = vNSE,
        VIL_NSE = vVIL_NSE,
        VIL_NSE_HEAT = vVIL_NSE_HEAT,
        FixedCostsGeneration = eFixedCostsGeneration,
        FixedCostsStorage = eFixedCostsStorage,
        FixedCostsTransmission = eFixedCostsTransmission,
        FixedCostsVILGeneration = eFixedCostsVILGeneration,
        FixedCostsVILStorage = eVILFixedCostsStorage,
        VariableCostsGrid = eVariableCostsGrid,
        VariableCostsVIL = eVariableCostsVILED + eVariableCostsVILUC,
        GridImportCosts = eGridImportCosts,
        StartCostsGrid = eStartCostsGrid,
        StartCostsVIL = eStartCostsVIL,
        CO2Emissions = eCO2EmissionsGrid + eCO2EmissionsVIL,
        CO2EmissionsGrid = eCO2EmissionsGrid,
        CO2EmissionsVIL = eCO2EmissionsVIL,
        REShare = eREShare,
        NSECosts = eNSECosts,
        VILNSECosts = eVILNSECosts,
        VILNSEHeatCosts = eVILNSEHeatCosts,
        cost = objective_value(CE)
        )

end
