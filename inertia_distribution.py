"""
Bus-Level Inertia Distribution Analysis.

Computes how synchronous generator inertia is distributed across all buses
in the network using electrical distance weighting.

Methodology:
    The effective inertia at bus k is computed as:
        H_eff(k) = sum_i [ w_ki * H_i * S_i ] / S_base

    where w_ki is the weight based on inverse electrical distance:
        w_ki = (1/d_ki) / sum_j (1/d_kj)   for all generators j

    This captures the physical reality that a generator's inertia
    contribution to frequency support is stronger at electrically
    closer buses.

References:
    [7] M. Tuo and X. Li, "Dynamic Estimation of Power System Inertia
        Distribution Using Synchrophasor Measurements," Proc. IEEE NAPS, 2021.
    [8] Z. Li et al., "New Energy Power System Inertia Weak Position
        Evaluation," Frontiers in Energy Research, vol. 12, 2024.
"""

import numpy as np
from config import GENERATOR_DATA, S_BASE


def compute_system_inertia(generator_data=None):
    """
    Compute total system inertia using Center of Inertia (COI) formulation.

        H_sys = sum(H_i * S_i) / sum(S_i)

    Reference: [1] Kundur, 1994, Chapter 12.

    Returns:
        H_sys: system-wide equivalent inertia constant (s)
        E_kinetic: total kinetic energy (MWs)
    """
    if generator_data is None:
        generator_data = GENERATOR_DATA

    numerator = sum(g["H"] * g["S_mva"] for g in generator_data.values())
    denominator = sum(g["S_mva"] for g in generator_data.values())
    H_sys = numerator / denominator
    E_kinetic = numerator  # Total kinetic energy in MWs
    return H_sys, E_kinetic


def compute_bus_inertia_distribution(electrical_distance, gen_bus_indices,
                                     all_bus_indices, generator_data=None):
    """
    Compute effective inertia at each bus using electrical distance weighting.

    Args:
        electrical_distance: electrical distance matrix (n x n)
        gen_bus_indices: list of matrix indices for generator buses
        all_bus_indices: dict mapping bus number to matrix index
        generator_data: dict of generator parameters

    Returns:
        bus_inertia: dict {bus_number: effective_H}
        inertia_distribution_index: dict {bus_number: IDI}
    """
    if generator_data is None:
        generator_data = GENERATOR_DATA

    n_bus = electrical_distance.shape[0]

    # Reverse mapping: matrix index -> bus number
    idx_to_bus = {v: k for k, v in all_bus_indices.items()}

    # Generator matrix indices and their H*S products
    gen_indices = []
    gen_HS = []
    for bus_num, gdata in generator_data.items():
        if bus_num in all_bus_indices:
            gen_indices.append(all_bus_indices[bus_num])
            gen_HS.append(gdata["H"] * gdata["S_mva"])

    gen_indices = np.array(gen_indices)
    gen_HS = np.array(gen_HS)

    bus_inertia = {}
    for k in range(n_bus):
        bus_num = idx_to_bus.get(k, k)

        # Electrical distances from bus k to all generators
        distances = electrical_distance[k, gen_indices]

        # Avoid division by zero (bus is a generator bus)
        distances = np.where(distances < 1e-10, 1e-10, distances)

        # Inverse distance weights
        inv_dist = 1.0 / distances
        weights = inv_dist / inv_dist.sum()

        # Effective inertia at bus k
        H_eff = np.sum(weights * gen_HS) / S_BASE
        bus_inertia[bus_num] = H_eff

    # Inertia Distribution Index (IDI)
    # IDI = H_eff(bus) / H_sys
    H_sys, _ = compute_system_inertia(generator_data)
    idi = {bus: H / H_sys for bus, H in bus_inertia.items()}

    return bus_inertia, idi


def identify_weak_buses(bus_inertia, threshold_percentile=25):
    """
    Identify inertia-weak buses (lowest effective inertia).

    Reference: [8] Li et al., 2024.

    Args:
        bus_inertia: dict {bus_number: effective_H}
        threshold_percentile: percentile below which buses are "weak"

    Returns:
        weak_buses: list of (bus_number, H_eff) sorted by H ascending
    """
    values = np.array(list(bus_inertia.values()))
    threshold = np.percentile(values, threshold_percentile)

    weak = [(bus, H) for bus, H in bus_inertia.items() if H <= threshold]
    weak.sort(key=lambda x: x[1])
    return weak


def compute_inertia_with_renewables(penetration_level, replacement_order,
                                     generator_data=None):
    """
    Compute modified generator data after replacing synchronous generators
    with inverter-based resources (IBRs) at a given penetration level.

    IBRs contribute zero rotational inertia (H=0) unless equipped with
    virtual inertia control.

    Reference: [2] Ulbig et al., 2014.

    Args:
        penetration_level: fraction of total generation replaced (0.0 to 1.0)
        replacement_order: list of generator bus numbers to replace in order
        generator_data: original generator data dict

    Returns:
        modified_data: new generator data dict with IBR replacements
        replaced_gens: list of replaced generator bus numbers
    """
    if generator_data is None:
        generator_data = GENERATOR_DATA

    total_capacity = sum(g["S_mva"] for g in generator_data.values())
    target_replacement = penetration_level * total_capacity

    modified = {}
    replaced = []
    cumulative = 0.0

    for bus in replacement_order:
        if bus not in generator_data:
            continue
        g = generator_data[bus]
        if cumulative + g["S_mva"] <= target_replacement * 1.01:
            # Replace with IBR (H=0)
            modified[bus] = {"H": 0.0, "S_mva": g["S_mva"], "name": g["name"] + "_IBR"}
            replaced.append(bus)
            cumulative += g["S_mva"]
        else:
            modified[bus] = g.copy()

    # Keep remaining generators unchanged
    for bus, g in generator_data.items():
        if bus not in modified:
            modified[bus] = g.copy()

    return modified, replaced
