"""
IEEE 39-Bus New England System Model using pandapower.

Builds the network and computes admittance/impedance matrices
for inertia distribution analysis.

References:
    [1] P. Kundur, Power System Stability and Control, McGraw-Hill, 1994.
    [3] F. Milano et al., "Foundations and Challenges of Low-Inertia Systems,"
        Proc. 20th PSCC, 2018.
"""

import numpy as np
import pandapower as pp
import pandapower.networks as pn


def create_ieee39():
    """Create IEEE 39-bus New England system with power flow solved."""
    net = pn.case39()
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True)
    return net


def get_admittance_matrix(net):
    """
    Extract the bus admittance matrix Y_bus from a solved pandapower network.

    Returns:
        Y_bus: complex admittance matrix (n_bus x n_bus)
        bus_indices: mapping from pandapower bus index to matrix index
    """
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True)

    from pandapower.pd2ppc import _pd2ppc
    from pandapower.pypower.makeYbus import makeYbus

    ppc, _ = _pd2ppc(net)
    baseMVA = ppc["baseMVA"]
    bus = ppc["bus"]
    branch = ppc["branch"]

    Y_bus, _, _ = makeYbus(baseMVA, bus, branch)
    Y_bus = Y_bus.toarray()

    bus_indices = {int(bus[i, 0]): i for i in range(len(bus))}
    return Y_bus, bus_indices


def get_impedance_matrix(Y_bus):
    """
    Compute bus impedance matrix Z_bus = inv(Y_bus).

    Returns:
        Z_bus: complex impedance matrix
    """
    return np.linalg.inv(Y_bus)


def compute_electrical_distance(Z_bus):
    """
    Compute electrical distance between all bus pairs.

    The electrical distance between bus i and bus j is defined as:
        d_ij = |Z_ii + Z_jj - 2*Z_ij|

    This metric captures how electrically "close" two buses are,
    which determines how much a generator's inertia is "felt" at a load bus.

    Reference: [3] Milano et al., 2018.

    Returns:
        D: electrical distance matrix (real, symmetric)
    """
    n = Z_bus.shape[0]
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            D[i, j] = abs(Z_bus[i, i] + Z_bus[j, j] - 2 * Z_bus[i, j])
    return D


def get_generator_bus_mapping(net):
    """
    Get mapping from generator index to bus number.

    Returns:
        dict: {gen_idx: bus_number}
    """
    mapping = {}
    for idx in net.gen.index:
        mapping[idx] = int(net.gen.at[idx, "bus"])
    # Also include ext_grid (slack bus)
    for idx in net.ext_grid.index:
        mapping[f"ext_{idx}"] = int(net.ext_grid.at[idx, "bus"])
    return mapping
