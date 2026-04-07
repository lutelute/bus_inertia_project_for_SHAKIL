"""
============================================================================
Bus Inertia Analysis on IEEE 39-Bus New England System
============================================================================

Main script that executes the complete analysis pipeline:

    Study 1: Base case inertia distribution
    Study 2: Frequency response after generator trip
    Study 3: Impact of renewable penetration on inertia & frequency
    Study 4: Multi-machine frequency dynamics
    Study 5: Summary tables for paper

References:
    [1] P. Kundur, Power System Stability and Control, McGraw-Hill, 1994.
    [2] A. Ulbig, T.S. Borsche, G. Andersson, "Impact of Low Rotational
        Inertia on Power System Stability and Operation," IFAC, 2014.
    [3] F. Milano et al., "Foundations and Challenges of Low-Inertia
        Systems," Proc. 20th PSCC, 2018.
    [4] H. Bevrani, T. Ise, Y. Miura, "Virtual Synchronous Generators:
        A Survey and New Perspectives," IJEP&ES, 2014.
    [5] A. Fernandez-Guillamon et al., "Inertia and Frequency Control
        Strategies," Renew. Sustain. Energy Rev., 2019.
    [6] M. Dreidy et al., "Inertia Response and Frequency Control Techniques
        for Renewable Energy Sources," RSER, 2017.
    [7] M. Tuo, X. Li, "Dynamic Estimation of Power System Inertia
        Distribution Using Synchrophasor Measurements," IEEE NAPS, 2021.
    [8] Z. Li et al., "New Energy Power System Inertia Weak Position
        Evaluation," Frontiers in Energy Research, 2024.

Usage:
    python main.py

Output:
    results/           - All figures and data tables
    results/summary.txt - Numerical results summary
============================================================================
"""

import os
import time
import numpy as np
import pandas as pd

from config import (GENERATOR_DATA, PENETRATION_LEVELS, REPLACEMENT_ORDER,
                    DISTURBANCE_SCENARIOS, S_BASE, F_NOMINAL,
                    ROCOF_LIMIT, FREQ_NADIR_LIMIT, OUTPUT_DIR,
                    FIG_FORMAT)
from ieee39_network import (create_ieee39, get_admittance_matrix,
                             get_impedance_matrix, compute_electrical_distance)
from inertia_distribution import (compute_system_inertia,
                                   compute_bus_inertia_distribution,
                                   identify_weak_buses,
                                   compute_inertia_with_renewables)
from frequency_simulation import (simulate_aggregated_frequency,
                                   simulate_multi_machine)
from visualization import (plot_bus_inertia_bar, plot_frequency_response,
                            plot_penetration_study, plot_multi_machine_frequency,
                            plot_inertia_comparison, plot_heatmap_inertia)


def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def main():
    start_time = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    summary_lines = []
    def log(msg):
        print(msg)
        summary_lines.append(msg)

    print_header("Bus Inertia Analysis - IEEE 39-Bus New England System")
    log("System: IEEE 39-Bus New England (10 generators)")
    log(f"Base MVA: {S_BASE} MVA, Nominal Frequency: {F_NOMINAL} Hz")

    # =========================================================================
    # Study 1: Base Case - Network and Inertia Distribution
    # =========================================================================
    print_header("Study 1: Base Case Inertia Distribution")

    log("\n--- Generator Data ---")
    log(f"{'Bus':>4s} {'Name':>5s} {'H (s)':>7s} {'S (MVA)':>8s} {'E_kin (MWs)':>12s}")
    log("-" * 40)
    total_S_mva = 0
    for bus in sorted(GENERATOR_DATA.keys()):
        g = GENERATOR_DATA[bus]
        E_kin = g["H"] * g["S_mva"]
        total_S_mva += g["S_mva"]
        log(f"{bus:4d} {g['name']:>5s} {g['H']:7.2f} {g['S_mva']:8.0f} {E_kin:12.1f}")

    H_sys, E_total = compute_system_inertia()
    log(f"\nSystem Inertia (COI): H_sys = {H_sys:.3f} s")
    log(f"Total Kinetic Energy: E_kin = {E_total:.1f} MWs")
    log(f"Total Generation Capacity: S_total = {total_S_mva:.0f} MVA")

    # Build network and compute electrical distances
    log("\nBuilding IEEE 39-bus network...")
    net = create_ieee39()
    log(f"  Buses: {len(net.bus)}, Lines: {len(net.line)}, Transformers: {len(net.trafo)}")

    Y_bus, bus_indices = get_admittance_matrix(net)
    Z_bus = get_impedance_matrix(Y_bus)
    D_elec = compute_electrical_distance(Z_bus)
    log(f"  Admittance matrix: {Y_bus.shape}, Impedance matrix: {Z_bus.shape}")

    # Compute bus-level inertia distribution
    gen_bus_indices = [bus_indices[b] for b in GENERATOR_DATA.keys()
                       if b in bus_indices]
    bus_inertia, idi = compute_bus_inertia_distribution(
        D_elec, gen_bus_indices, bus_indices
    )

    log("\n--- Bus Inertia Distribution (Top 10 highest / lowest) ---")
    sorted_inertia = sorted(bus_inertia.items(), key=lambda x: x[1])
    log(f"\n  Lowest inertia buses:")
    for bus, H in sorted_inertia[:10]:
        log(f"    Bus {bus:3d}: H_eff = {H:.3f} s (IDI = {idi[bus]:.3f})")
    log(f"\n  Highest inertia buses:")
    for bus, H in sorted_inertia[-10:]:
        log(f"    Bus {bus:3d}: H_eff = {H:.3f} s (IDI = {idi[bus]:.3f})")

    weak_buses = identify_weak_buses(bus_inertia, threshold_percentile=25)
    log(f"\n--- Inertia-Weak Buses (bottom 25th percentile) ---")
    for bus, H in weak_buses:
        log(f"  Bus {bus:3d}: H_eff = {H:.3f} s")

    log("\nGenerating figures...")
    plot_bus_inertia_bar(bus_inertia, weak_buses)
    plot_heatmap_inertia(bus_inertia)

    # =========================================================================
    # Study 2: Frequency Response After Generator Trip
    # =========================================================================
    print_header("Study 2: Frequency Response - Generator Trip Scenarios")

    for scenario_name, scenario in DISTURBANCE_SCENARIOS.items():
        P_loss_mw = scenario["P_loss_mw"]
        log(f"\n--- Scenario: {scenario_name} ---")
        log(f"  Tripped generator at Bus {scenario['bus']}, "
            f"Power loss: {P_loss_mw} MW")

        t, freq, rocof, metrics = simulate_aggregated_frequency(
            E_total, total_S_mva, P_loss_mw
        )

        log(f"  H_sys = {metrics['H_sys']:.3f} s")
        log(f"  RoCoF (analytical) = {metrics['rocof_analytical_hz_s']:.4f} Hz/s")
        log(f"  RoCoF (simulated)  = {metrics['rocof_initial_hz_s']:.4f} Hz/s")
        log(f"  Frequency nadir    = {metrics['nadir_hz']:.4f} Hz at t = {metrics['t_nadir_s']:.3f} s")
        log(f"  Steady-state dev   = {metrics['steady_state_dev_hz']:.4f} Hz")

        rocof_ok = abs(metrics["rocof_analytical_hz_s"]) < ROCOF_LIMIT
        nadir_ok = metrics["nadir_hz"] > FREQ_NADIR_LIMIT
        log(f"  RoCoF within limit ({ROCOF_LIMIT} Hz/s): {'YES' if rocof_ok else 'NO - VIOLATION'}")
        log(f"  Nadir within limit ({FREQ_NADIR_LIMIT} Hz):  {'YES' if nadir_ok else 'NO - VIOLATION'}")

        plot_frequency_response(
            t, freq, metrics,
            title=f"Frequency Response - {scenario_name}",
            filename=f"fig2_{scenario_name}"
        )

    # =========================================================================
    # Study 3: Renewable Penetration Impact
    # =========================================================================
    print_header("Study 3: Renewable Penetration Impact on System Inertia")

    dist_scenario = DISTURBANCE_SCENARIOS["trip_G10"]
    P_loss_mw = dist_scenario["P_loss_mw"]
    penetration_results = []
    inertia_scenarios = []

    log(f"\nDisturbance: Trip G10 (Bus {dist_scenario['bus']}), "
        f"{P_loss_mw} MW loss")
    log(f"\n{'Pen.(%)':>8s} {'H_sys(s)':>9s} {'E_kin(MWs)':>11s} "
        f"{'RoCoF(Hz/s)':>12s} {'Nadir(Hz)':>10s} {'Replaced':>30s}")
    log("-" * 85)

    for pen_level in PENETRATION_LEVELS:
        mod_data, replaced = compute_inertia_with_renewables(
            pen_level, REPLACEMENT_ORDER
        )

        # Compute inertia of remaining synchronous generators
        active_data = {b: g for b, g in mod_data.items() if g["H"] > 0}
        if not active_data:
            log(f"  {pen_level*100:5.0f}%: No synchronous generators remaining!")
            continue

        H_sys_mod, E_kin_mod = compute_system_inertia(mod_data)
        # E_kinetic for active (synchronous) generators only
        E_kin_active = sum(g["H"] * g["S_mva"] for g in active_data.values())
        S_total_mod = sum(g["S_mva"] for g in mod_data.values())

        t, freq, rocof, metrics = simulate_aggregated_frequency(
            E_kin_active, S_total_mod, P_loss_mw
        )

        replaced_names = [mod_data[b]["name"] for b in replaced]
        log(f"{pen_level*100:7.0f}% {H_sys_mod:9.3f} {E_kin_mod:11.1f} "
            f"{metrics['rocof_analytical_hz_s']:12.4f} {metrics['nadir_hz']:10.4f} "
            f"{', '.join(replaced_names):>30s}")

        penetration_results.append({
            "penetration": pen_level,
            "metrics": metrics,
            "replaced": replaced,
            "mod_data": mod_data,
        })

        # Compute bus inertia for this scenario
        mod_bus_inertia, _ = compute_bus_inertia_distribution(
            D_elec, gen_bus_indices, bus_indices, mod_data
        )
        inertia_scenarios.append({
            "bus_inertia": mod_bus_inertia,
            "label": f"RES {pen_level*100:.0f}%",
        })

    plot_penetration_study(penetration_results)
    plot_inertia_comparison(inertia_scenarios)

    # =========================================================================
    # Study 4: Multi-Machine Frequency Dynamics
    # =========================================================================
    print_header("Study 4: Multi-Machine Frequency Dynamics")

    for pen_level in [0.0, 0.40, 0.60]:
        mod_data, replaced = compute_inertia_with_renewables(
            pen_level, REPLACEMENT_ORDER
        )
        tripped_bus = dist_scenario["bus"]

        log(f"\n--- Penetration: {pen_level*100:.0f}%, Trip Bus {tripped_bus} ---")
        try:
            t, gen_freqs, coi_freq = simulate_multi_machine(
                mod_data, P_loss_mw, tripped_bus
            )

            coi_nadir = np.min(coi_freq[t >= 1.0])
            log(f"  COI frequency nadir: {coi_nadir:.4f} Hz")
            log(f"  Active generators: {len(gen_freqs)}")

            plot_multi_machine_frequency(
                t, gen_freqs, coi_freq, mod_data, tripped_bus,
                filename=f"fig4_multi_machine_pen{int(pen_level*100)}"
            )
        except ValueError as e:
            log(f"  Skipped: {e}")

    # =========================================================================
    # Study 5: Summary Tables for Paper
    # =========================================================================
    print_header("Study 5: Summary Tables")

    # Table 1: Generator parameters
    table1_data = []
    for bus in sorted(GENERATOR_DATA.keys()):
        g = GENERATOR_DATA[bus]
        table1_data.append({
            "Bus": bus,
            "Generator": g["name"],
            "H (s)": g["H"],
            "Rating (MVA)": g["S_mva"],
            "E_kinetic (MWs)": g["H"] * g["S_mva"],
        })
    df_table1 = pd.DataFrame(table1_data)
    table1_path = os.path.join(OUTPUT_DIR, "table1_generator_data.csv")
    df_table1.to_csv(table1_path, index=False)
    log(f"\nTable 1 saved: {table1_path}")
    log(df_table1.to_string(index=False))

    # Table 2: Penetration study results
    table2_data = []
    for r in penetration_results:
        m = r["metrics"]
        replaced_names = [GENERATOR_DATA[b]["name"] for b in r["replaced"]
                          if b in GENERATOR_DATA]
        table2_data.append({
            "Penetration (%)": r["penetration"] * 100,
            "H_sys (s)": round(m["H_sys"], 3),
            "E_kin (MWs)": round(m["E_kinetic"], 1),
            "RoCoF (Hz/s)": round(m["rocof_analytical_hz_s"], 4),
            "Nadir (Hz)": round(m["nadir_hz"], 4),
            "Steady-State (Hz)": round(m["steady_state_hz"], 4),
            "Replaced Generators": ", ".join(replaced_names),
        })
    df_table2 = pd.DataFrame(table2_data)
    table2_path = os.path.join(OUTPUT_DIR, "table2_penetration_results.csv")
    df_table2.to_csv(table2_path, index=False)
    log(f"\nTable 2 saved: {table2_path}")
    log(df_table2.to_string(index=False))

    # Table 3: Bus inertia distribution (base case)
    table3_data = []
    for bus in sorted(bus_inertia.keys()):
        table3_data.append({
            "Bus": bus,
            "H_eff (s)": round(bus_inertia[bus], 4),
            "IDI": round(idi[bus], 4),
            "Weak": "Yes" if bus in {b for b, _ in weak_buses} else "",
        })
    df_table3 = pd.DataFrame(table3_data)
    table3_path = os.path.join(OUTPUT_DIR, "table3_bus_inertia.csv")
    df_table3.to_csv(table3_path, index=False)
    log(f"\nTable 3 saved: {table3_path}")

    # =========================================================================
    # Save Summary
    # =========================================================================
    elapsed = time.time() - start_time
    log(f"\nTotal computation time: {elapsed:.1f} s")

    summary_path = os.path.join(OUTPUT_DIR, "summary.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(summary_lines))
    print(f"\nFull summary saved to: {summary_path}")

    print_header("Analysis Complete")
    print(f"All results saved to: {OUTPUT_DIR}/")
    print(f"Figures: fig1-fig6 (.{FIG_FORMAT})")
    print(f"Tables:  table1-table3 (.csv)")
    print(f"Summary: summary.txt")


if __name__ == "__main__":
    main()
