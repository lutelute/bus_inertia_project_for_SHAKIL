"""
Frequency Response Simulation using the Swing Equation.

Simulates system frequency dynamics after a generation-load imbalance
(e.g., generator trip) using the aggregated swing equation and
multi-machine swing equations.

The aggregated (COI) swing equation:
    2 * H_sys * (d delta_f / dt) = -(delta_P / S_total) - D * delta_f

where:
    H_sys = sum(H_i * S_i) / sum(S_i)  -- system inertia constant
    delta_P is in MW, S_total is total generation in MVA
    delta_f is frequency deviation in per-unit

Key formula for initial RoCoF:
    RoCoF = -delta_P_mw * f_0 / (2 * sum(H_i * S_i))

References:
    [1] P. Kundur, Power System Stability and Control, 1994, Ch. 11-12.
    [2] A. Ulbig et al., "Impact of Low Rotational Inertia," IFAC 2014.
    [5] A. Fernandez-Guillamon et al., "Inertia and Frequency Control
        Strategies," Renew. Sustain. Energy Rev., 2019.
"""

import numpy as np
from scipy.integrate import solve_ivp
from config import (F_NOMINAL, D_COEFF, T_GOV, R_DROOP,
                    T_START, T_END, DT, T_DISTURBANCE)


def simulate_aggregated_frequency(E_kinetic, S_total, P_loss_mw,
                                   D=None, t_gov=None, R=None, t_end=None):
    """
    Simulate system frequency using aggregated swing equation with
    first-order governor response.

    Args:
        E_kinetic: total kinetic energy sum(H_i * S_i) in MWs
        S_total: total generation capacity in MVA
        P_loss_mw: power loss in MW (positive = generation loss)
        D: damping coefficient (pu)
        t_gov: governor time constant (s)
        R: droop setting (pu)
        t_end: simulation end time (s)

    Returns:
        t, freq, rocof, metrics
    """
    if D is None:
        D = D_COEFF
    if t_gov is None:
        t_gov = T_GOV
    if R is None:
        R = R_DROOP
    if t_end is None:
        t_end = T_END

    H_sys = E_kinetic / S_total
    P_loss_pu = P_loss_mw / S_total  # Normalize to total generation base

    def swing_ode(t, x):
        delta_f = x[0]
        P_gov = x[1]

        if t >= T_DISTURBANCE:
            P_dist = P_loss_pu
        else:
            P_dist = 0.0

        d_delta_f = (1.0 / (2.0 * H_sys)) * (-P_dist - D * delta_f + P_gov)
        d_P_gov = (1.0 / t_gov) * (-delta_f / R - P_gov)

        return [d_delta_f, d_P_gov]

    t_span = (T_START, t_end)
    t_eval = np.arange(T_START, t_end, DT)
    x0 = [0.0, 0.0]

    sol = solve_ivp(swing_ode, t_span, x0, t_eval=t_eval,
                    method="RK45", max_step=DT)

    delta_f_pu = sol.y[0]
    freq = F_NOMINAL * (1.0 + delta_f_pu)

    rocof = np.gradient(freq, sol.t)

    # Metrics (post-disturbance)
    post_dist = sol.t >= T_DISTURBANCE
    freq_post = freq[post_dist]
    t_post = sol.t[post_dist]
    rocof_post = rocof[post_dist]

    nadir = np.min(freq_post)
    nadir_idx = np.argmin(freq_post)
    t_nadir = t_post[nadir_idx]
    rocof_initial = rocof_post[min(5, len(rocof_post) - 1)]
    steady_state = freq_post[-1]

    # Analytical RoCoF: df/dt = -P_loss_mw * f0 / (2 * E_kinetic)
    rocof_analytical = -(P_loss_mw * F_NOMINAL) / (2.0 * E_kinetic)

    metrics = {
        "nadir_hz": nadir,
        "rocof_initial_hz_s": rocof_initial,
        "rocof_analytical_hz_s": rocof_analytical,
        "t_nadir_s": t_nadir,
        "steady_state_hz": steady_state,
        "steady_state_dev_hz": steady_state - F_NOMINAL,
        "H_sys": H_sys,
        "E_kinetic": E_kinetic,
        "S_total": S_total,
        "P_loss_mw": P_loss_mw,
    }

    return sol.t, freq, rocof, metrics


def simulate_multi_machine(generator_data, P_loss_mw, tripped_bus,
                            D=None, t_end=None):
    """
    Simulate individual generator frequencies using multi-machine
    swing equations.

    Args:
        generator_data: dict {bus: {"H": .., "S_mva": .., "name": ..}}
        P_loss_mw: lost generation in MW
        tripped_bus: bus number of tripped generator
        D: damping coefficient
        t_end: simulation end time

    Returns:
        t, gen_freqs, coi_freq
    """
    if D is None:
        D = D_COEFF
    if t_end is None:
        t_end = T_END

    active_gens = {b: g for b, g in generator_data.items()
                   if b != tripped_bus and g["H"] > 0}

    if not active_gens:
        raise ValueError("No active synchronous generators remaining.")

    buses = sorted(active_gens.keys())
    n_gen = len(buses)

    total_S = sum(active_gens[b]["S_mva"] for b in buses)

    # Power redistribution proportional to MVA rating (in pu on each machine base)
    # For the swing equation: 2*H_i * d(delta_f)/dt = -(P_share_i/S_i) - D*delta_f
    P_share_mw = {b: P_loss_mw * active_gens[b]["S_mva"] / total_S for b in buses}

    def multi_swing_ode(t, x):
        dxdt = np.zeros(n_gen)
        for i, bus in enumerate(buses):
            H_i = active_gens[bus]["H"]
            S_i = active_gens[bus]["S_mva"]
            if t >= T_DISTURBANCE:
                P_dist_pu_i = P_share_mw[bus] / S_i
            else:
                P_dist_pu_i = 0.0
            dxdt[i] = (1.0 / (2.0 * H_i)) * (-P_dist_pu_i - D * x[i])
        return dxdt

    t_span = (T_START, t_end)
    t_eval = np.arange(T_START, t_end, DT)
    x0 = np.zeros(n_gen)

    sol = solve_ivp(multi_swing_ode, t_span, x0, t_eval=t_eval,
                    method="RK45", max_step=DT)

    gen_freqs = {}
    for i, bus in enumerate(buses):
        gen_freqs[bus] = F_NOMINAL * (1.0 + sol.y[i])

    # COI frequency
    total_HS = sum(active_gens[b]["H"] * active_gens[b]["S_mva"] for b in buses)
    coi_delta_f = np.zeros_like(sol.t)
    for i, bus in enumerate(buses):
        weight = active_gens[bus]["H"] * active_gens[bus]["S_mva"] / total_HS
        coi_delta_f += weight * sol.y[i]
    coi_freq = F_NOMINAL * (1.0 + coi_delta_f)

    return sol.t, gen_freqs, coi_freq


def compute_rocof_analytical(E_kinetic, P_loss_mw):
    """
    Compute analytical initial RoCoF.
        RoCoF = -P_loss_mw * f_0 / (2 * E_kinetic)
    """
    return -(P_loss_mw * F_NOMINAL) / (2.0 * E_kinetic)
