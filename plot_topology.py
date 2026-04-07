"""
IEEE 39-Bus System Topology Visualization with Inertia Overlay.

Draws the network single-line diagram with:
  - Bus nodes colored by effective inertia (green=high, red=low)
  - Generator nodes shown as squares
  - Load buses shown as circles
  - Line connections drawn to scale
  - Multiple penetration scenarios side-by-side
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.lines import Line2D
import networkx as nx

from config import GENERATOR_DATA, OUTPUT_DIR, FIG_DPI, PENETRATION_LEVELS, REPLACEMENT_ORDER
from ieee39_network import (create_ieee39, get_admittance_matrix,
                             get_impedance_matrix, compute_electrical_distance)
from inertia_distribution import (compute_system_inertia,
                                   compute_bus_inertia_distribution,
                                   identify_weak_buses,
                                   compute_inertia_with_renewables)

# ============================================================================
# IEEE 39-Bus Standard Layout Coordinates
# Based on the well-known New England system single-line diagram
# Bus index 0-38 corresponds to Bus 1-39
# ============================================================================
BUS_POS = {
    0:  (5.0, 8.0),    # Bus 1
    1:  (7.5, 9.5),    # Bus 2
    2:  (10.0, 9.5),   # Bus 3
    3:  (12.5, 9.0),   # Bus 4
    4:  (15.0, 9.0),   # Bus 5
    5:  (17.0, 9.0),   # Bus 6
    6:  (19.0, 8.0),   # Bus 7
    7:  (17.0, 7.0),   # Bus 8
    8:  (14.0, 6.0),   # Bus 9
    9:  (19.0, 5.5),   # Bus 10
    10: (19.0, 6.8),   # Bus 11
    11: (20.5, 5.5),   # Bus 12
    12: (20.5, 7.5),   # Bus 13
    13: (14.0, 8.0),   # Bus 14
    14: (12.0, 6.5),   # Bus 15
    15: (10.0, 6.0),   # Bus 16
    16: (8.0, 6.0),    # Bus 17
    17: (8.0, 8.0),    # Bus 18
    18: (6.5, 5.5),    # Bus 19
    19: (5.0, 4.5),    # Bus 20
    20: (7.5, 4.0),    # Bus 21
    21: (10.0, 3.5),   # Bus 22
    22: (12.5, 3.5),   # Bus 23
    23: (14.0, 4.5),   # Bus 24
    24: (7.0, 11.0),   # Bus 25
    25: (10.0, 11.5),  # Bus 26
    26: (12.0, 11.5),  # Bus 27
    27: (14.0, 12.0),  # Bus 28
    28: (16.0, 12.0),  # Bus 29
    # Generator buses (offset from main ring)
    29: (8.5, 12.0),   # Bus 30 (G1)
    30: (18.5, 10.5),  # Bus 31 (ext_grid / G10 area)
    31: (21.5, 4.5),   # Bus 32 (G3)
    32: (6.0, 3.0),    # Bus 33 (G4)
    33: (4.0, 3.0),    # Bus 34 (G5)
    34: (11.5, 1.5),   # Bus 35 (G6)
    35: (14.5, 2.0),   # Bus 36 (G7)
    36: (5.5, 12.5),   # Bus 37 (G2)
    37: (18.0, 13.0),  # Bus 38 (G9)
    38: (11.0, 7.5),   # Bus 39 (G10 / slack connected)
}

# Generator bus set (pandapower indices)
GEN_BUSES = {29, 30, 31, 32, 33, 34, 35, 36, 37, 38}
# Which pp bus index maps to which generator name
GEN_LABELS = {
    29: "G1", 30: "G2(ext)", 31: "G3", 32: "G4", 33: "G5",
    34: "G6", 35: "G7", 36: "G8", 37: "G9", 38: "G10"
}
# Mapping: pandapower bus index -> config.py GENERATOR_DATA bus key
PP_TO_CONFIG = {
    29: 30, 30: 31, 31: 32, 32: 33, 33: 34,
    34: 35, 35: 36, 36: 37, 37: 38, 38: 39
}


def build_graph(net):
    """Build a networkx graph from pandapower network."""
    G = nx.Graph()
    for idx in net.bus.index:
        G.add_node(idx)

    for idx in net.line.index:
        fb = int(net.line.at[idx, "from_bus"])
        tb = int(net.line.at[idx, "to_bus"])
        G.add_edge(fb, tb, etype="line")

    for idx in net.trafo.index:
        hv = int(net.trafo.at[idx, "hv_bus"])
        lv = int(net.trafo.at[idx, "lv_bus"])
        G.add_edge(hv, lv, etype="trafo")

    return G


def draw_topology_with_inertia(bus_inertia, bus_indices, generator_data,
                                title="", ax=None, show_values=True,
                                vmin=None, vmax=None, net=None):
    """
    Draw IEEE 39-bus topology with inertia overlay on a given axes.

    Args:
        bus_inertia: dict {pp_bus_index: H_eff}
        bus_indices: mapping from bus number to matrix index (from Y_bus)
        generator_data: current generator data dict
        title: subplot title
        ax: matplotlib axes
        show_values: whether to show H_eff values on nodes
        vmin, vmax: colorbar range
        net: pandapower network
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(16, 12))

    G = build_graph(net)

    # Map bus_inertia (keyed by Y_bus index) to pp bus index
    # bus_indices: {pp_bus_idx: matrix_idx}
    idx_to_pp = {v: k for k, v in bus_indices.items()}
    pp_bus_inertia = {}
    for mat_idx, H in bus_inertia.items():
        pp_idx = idx_to_pp.get(mat_idx, mat_idx)
        pp_bus_inertia[pp_idx] = H

    # Node colors based on inertia
    all_H = [pp_bus_inertia.get(n, 0) for n in G.nodes()]
    if vmin is None:
        vmin = min(all_H)
    if vmax is None:
        vmax = max(all_H)

    cmap = plt.cm.RdYlGn
    norm = Normalize(vmin=vmin, vmax=vmax)

    # Separate node lists
    gen_nodes = [n for n in G.nodes() if n in GEN_BUSES]
    load_nodes = [n for n in G.nodes() if n not in GEN_BUSES]

    # Draw edges
    line_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == "line"]
    trafo_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == "trafo"]

    nx.draw_networkx_edges(G, BUS_POS, edgelist=line_edges, ax=ax,
                            edge_color="#555555", width=1.5, alpha=0.7)
    nx.draw_networkx_edges(G, BUS_POS, edgelist=trafo_edges, ax=ax,
                            edge_color="#888888", width=1.0, alpha=0.5,
                            style="dashed")

    # Draw load buses (circles)
    load_colors = [cmap(norm(pp_bus_inertia.get(n, 0))) for n in load_nodes]
    load_sizes = [350 for _ in load_nodes]
    nx.draw_networkx_nodes(G, BUS_POS, nodelist=load_nodes, ax=ax,
                            node_color=load_colors, node_size=load_sizes,
                            node_shape="o", edgecolors="black", linewidths=0.8)

    # Draw generator buses (squares, larger)
    gen_colors = [cmap(norm(pp_bus_inertia.get(n, 0))) for n in gen_nodes]
    # Check which generators are IBR (H=0)
    gen_edge_colors = []
    for n in gen_nodes:
        config_bus = PP_TO_CONFIG.get(n)
        if config_bus and generator_data.get(config_bus, {}).get("H", 1) == 0:
            gen_edge_colors.append("#ff00ff")  # Magenta border for IBR
        else:
            gen_edge_colors.append("black")

    nx.draw_networkx_nodes(G, BUS_POS, nodelist=gen_nodes, ax=ax,
                            node_color=gen_colors, node_size=600,
                            node_shape="s", edgecolors=gen_edge_colors,
                            linewidths=2.0)

    # Labels
    if show_values:
        labels = {}
        for n in G.nodes():
            bus_num = n + 1  # pandapower 0-indexed -> 1-indexed display
            H = pp_bus_inertia.get(n, 0)
            if n in GEN_BUSES:
                gname = GEN_LABELS.get(n, "")
                config_bus = PP_TO_CONFIG.get(n)
                if config_bus and generator_data.get(config_bus, {}).get("H", 1) == 0:
                    labels[n] = f"{gname}\n(IBR)"
                else:
                    labels[n] = f"{gname}\n{H:.1f}"
            else:
                labels[n] = f"{bus_num}\n{H:.1f}"

        nx.draw_networkx_labels(G, BUS_POS, labels, ax=ax,
                                 font_size=6, font_weight="bold",
                                 font_color="black")
    else:
        labels = {}
        for n in G.nodes():
            if n in GEN_BUSES:
                labels[n] = GEN_LABELS.get(n, "")
            else:
                labels[n] = str(n + 1)
        nx.draw_networkx_labels(G, BUS_POS, labels, ax=ax,
                                 font_size=7, font_weight="bold")

    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlim(2.5, 23.0)
    ax.set_ylim(0.5, 14.5)
    ax.set_aspect("equal")
    ax.axis("off")

    return norm, cmap


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Building IEEE 39-bus network...")
    net = create_ieee39()
    Y_bus, bus_indices = get_admittance_matrix(net)
    Z_bus = get_impedance_matrix(Y_bus)
    D_elec = compute_electrical_distance(Z_bus)

    gen_bus_indices = [bus_indices[b] for b in GENERATOR_DATA.keys()
                       if b in bus_indices]

    # ========================================================================
    # Figure 7: Base case topology with inertia overlay
    # ========================================================================
    print("Generating Fig 7: Base case topology...")
    bus_inertia, idi = compute_bus_inertia_distribution(
        D_elec, gen_bus_indices, bus_indices
    )
    weak_buses = identify_weak_buses(bus_inertia, threshold_percentile=25)

    fig, ax = plt.subplots(figsize=(18, 13))
    norm, cmap = draw_topology_with_inertia(
        bus_inertia, bus_indices, GENERATOR_DATA,
        title="IEEE 39-Bus System: Bus Inertia Distribution (Base Case)",
        ax=ax, show_values=True, net=net
    )

    # Colorbar
    sm = ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical", shrink=0.6, pad=0.02)
    cbar.set_label("Effective Inertia $H_{eff}$ (s)", fontsize=12)

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="gray",
               markersize=12, markeredgecolor="black", markeredgewidth=2,
               label="Synchronous Generator"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="gray",
               markersize=10, markeredgecolor="black", label="Load / Tie Bus"),
        Line2D([0], [0], color="#555555", linewidth=1.5, label="Transmission Line"),
        Line2D([0], [0], color="#888888", linewidth=1.0, linestyle="--",
               label="Transformer"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", fontsize=10,
              framealpha=0.9)

    H_sys, E_total = compute_system_inertia()
    ax.text(0.02, 0.98,
            f"$H_{{sys}}$ = {H_sys:.3f} s\n$E_{{kin}}$ = {E_total:.0f} MWs",
            transform=ax.transAxes, fontsize=11, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow",
                      edgecolor="gray", alpha=0.9))

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"fig7_topology_base.png")
    fig.savefig(path, dpi=FIG_DPI)
    plt.close(fig)
    print(f"  Saved: {path}")

    # ========================================================================
    # Figure 8: Comparison across penetration levels (2x2 grid)
    # ========================================================================
    print("Generating Fig 8: Penetration comparison topology...")
    pen_levels = [0.0, 0.20, 0.40, 0.60, 0.80]

    # Compute global min/max for consistent colorbar
    all_bus_inertias = []
    scenarios = []
    for pen in pen_levels:
        mod_data, replaced = compute_inertia_with_renewables(pen, REPLACEMENT_ORDER)
        mod_bus_inertia, _ = compute_bus_inertia_distribution(
            D_elec, gen_bus_indices, bus_indices, mod_data
        )
        H_sys_mod, E_kin_mod = compute_system_inertia(mod_data)
        all_bus_inertias.extend(mod_bus_inertia.values())
        scenarios.append({
            "pen": pen,
            "bus_inertia": mod_bus_inertia,
            "mod_data": mod_data,
            "replaced": replaced,
            "H_sys": H_sys_mod,
            "E_kin": E_kin_mod,
        })

    global_vmin = min(all_bus_inertias)
    global_vmax = max(all_bus_inertias)

    # 2x3 layout for 5 scenarios + colorbar
    fig, axes = plt.subplots(2, 3, figsize=(30, 20))

    for i, sc in enumerate(scenarios):
        row, col = divmod(i, 3)
        ax = axes[row][col]

        n_sync = sum(1 for g in sc["mod_data"].values() if g["H"] > 0)
        n_ibr = sum(1 for g in sc["mod_data"].values() if g["H"] == 0)

        norm, cmap = draw_topology_with_inertia(
            sc["bus_inertia"], bus_indices, sc["mod_data"],
            title=(f"RES Penetration: {sc['pen']*100:.0f}%  |  "
                   f"$H_{{sys}}$ = {sc['H_sys']:.2f} s  |  "
                   f"Sync: {n_sync}, IBR: {n_ibr}"),
            ax=ax, show_values=True,
            vmin=global_vmin, vmax=global_vmax, net=net
        )

    # Last subplot: colorbar + legend
    ax_cb = axes[1][2]
    ax_cb.axis("off")

    sm = ScalarMappable(norm=Normalize(vmin=global_vmin, vmax=global_vmax), cmap=plt.cm.RdYlGn)
    cbar = fig.colorbar(sm, ax=ax_cb, orientation="vertical", shrink=0.8,
                         aspect=20, pad=0.05)
    cbar.set_label("Effective Inertia $H_{eff}$ (s)", fontsize=14)

    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#2ca02c",
               markersize=14, markeredgecolor="black", markeredgewidth=2,
               label="Synchronous Gen (high H)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#d62728",
               markersize=14, markeredgecolor="black", markeredgewidth=2,
               label="Synchronous Gen (low H)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="lightgray",
               markersize=14, markeredgecolor="#ff00ff", markeredgewidth=3,
               label="IBR (H = 0, magenta border)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="gray",
               markersize=12, markeredgecolor="black", label="Load / Tie Bus"),
        Line2D([0], [0], color="#555555", linewidth=2, label="Transmission Line"),
        Line2D([0], [0], color="#888888", linewidth=1.5, linestyle="--",
               label="Transformer"),
    ]
    ax_cb.legend(handles=legend_elements, loc="center", fontsize=13,
                  framealpha=0.9, title="Legend", title_fontsize=14)

    fig.suptitle("IEEE 39-Bus System: Bus Inertia Distribution Under Increasing Renewable Penetration",
                  fontsize=18, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = os.path.join(OUTPUT_DIR, "fig8_topology_penetration.png")
    fig.savefig(path, dpi=FIG_DPI)
    plt.close(fig)
    print(f"  Saved: {path}")

    # ========================================================================
    # Figure 9: Zoomed single diagram with detailed annotations
    # ========================================================================
    print("Generating Fig 9: Annotated base case topology...")
    fig, ax = plt.subplots(figsize=(20, 15))
    norm, cmap = draw_topology_with_inertia(
        bus_inertia, bus_indices, GENERATOR_DATA,
        title="IEEE 39-Bus New England System: Inertia Distribution with Weak Bus Identification",
        ax=ax, show_values=True, net=net
    )

    # Highlight weak buses with red circles
    weak_bus_pp = set()
    idx_to_pp = {v: k for k, v in bus_indices.items()}
    for mat_idx, _ in weak_buses:
        pp_idx = idx_to_pp.get(mat_idx, mat_idx)
        weak_bus_pp.add(pp_idx)

    for n in weak_bus_pp:
        if n in BUS_POS:
            x, y = BUS_POS[n]
            circle = plt.Circle((x, y), 0.55, fill=False, color="red",
                                 linewidth=2.5, linestyle="-", zorder=5)
            ax.add_patch(circle)

    # Colorbar
    sm = ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical", shrink=0.5, pad=0.02)
    cbar.set_label("Effective Inertia $H_{eff}$ (s)", fontsize=13)

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="gray",
               markersize=14, markeredgecolor="black", markeredgewidth=2,
               label="Synchronous Generator"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="gray",
               markersize=12, markeredgecolor="black", label="Load / Tie Bus"),
        Line2D([0], [0], color="#555555", linewidth=2, label="Transmission Line"),
        Line2D([0], [0], color="#888888", linewidth=1.5, linestyle="--",
               label="Transformer"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="none",
               markersize=16, markeredgecolor="red", markeredgewidth=2.5,
               label="Inertia-Weak Bus (bottom 25%)"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", fontsize=11,
              framealpha=0.9)

    # Info box
    ax.text(0.02, 0.98,
            f"System Inertia: $H_{{sys}}$ = {H_sys:.3f} s\n"
            f"Total Kinetic Energy: {E_total:.0f} MWs\n"
            f"Weak Buses: {len(weak_buses)} (bottom 25th percentile)\n"
            f"Green = High Inertia, Red = Low Inertia",
            transform=ax.transAxes, fontsize=11, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow",
                      edgecolor="gray", alpha=0.95))

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "fig9_topology_annotated.png")
    fig.savefig(path, dpi=FIG_DPI)
    plt.close(fig)
    print(f"  Saved: {path}")

    print("\nDone. Topology figures saved to results/")


if __name__ == "__main__":
    main()
