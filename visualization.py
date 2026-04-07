"""
Visualization module for Bus Inertia Analysis.

Generates publication-quality figures for:
    1. Bus inertia distribution heatmap
    2. Frequency response after disturbance
    3. RoCoF vs renewable penetration
    4. Inertia-weak bus identification
    5. Multi-machine frequency responses
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from config import OUTPUT_DIR, FIG_DPI, FIG_FORMAT, F_NOMINAL, ROCOF_LIMIT, FREQ_NADIR_LIMIT

# Publication style
plt.rcParams.update({
    "font.size": 11,
    "font.family": "serif",
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9,
    "figure.figsize": (8, 5),
    "figure.dpi": FIG_DPI,
    "savefig.dpi": FIG_DPI,
    "savefig.bbox": "tight",
    "lines.linewidth": 1.5,
    "grid.alpha": 0.3,
})


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def plot_bus_inertia_bar(bus_inertia, weak_buses=None, title="Bus Inertia Distribution",
                          filename="fig1_bus_inertia_distribution"):
    """
    Fig 1: Bar chart of effective inertia at each bus.
    Weak buses highlighted in red.
    """
    ensure_output_dir()

    buses = sorted(bus_inertia.keys())
    H_values = [bus_inertia[b] for b in buses]

    weak_set = set()
    if weak_buses:
        weak_set = {b for b, _ in weak_buses}

    colors = ["#d62728" if b in weak_set else "#1f77b4" for b in buses]

    fig, ax = plt.subplots(figsize=(14, 5))
    x = np.arange(len(buses))
    ax.bar(x, H_values, color=colors, edgecolor="black", linewidth=0.3)
    ax.set_xticks(x)
    ax.set_xticklabels([str(b) for b in buses], rotation=45, fontsize=8)
    ax.set_xlabel("Bus Number")
    ax.set_ylabel("Effective Inertia Constant $H_{eff}$ (s)")
    ax.set_title(title)
    ax.grid(axis="y")

    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#1f77b4", edgecolor="black", label="Normal Bus"),
        Patch(facecolor="#d62728", edgecolor="black", label="Inertia-Weak Bus"),
    ]
    ax.legend(handles=legend_elements, loc="upper right")

    filepath = os.path.join(OUTPUT_DIR, f"{filename}.{FIG_FORMAT}")
    fig.savefig(filepath)
    plt.close(fig)
    print(f"  Saved: {filepath}")
    return filepath


def plot_frequency_response(t, freq, metrics, title="Frequency Response",
                             filename="fig2_frequency_response"):
    """
    Fig 2: Frequency vs time after disturbance.
    Shows nadir, RoCoF, and threshold lines.
    """
    ensure_output_dir()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})

    # Frequency plot
    ax1.plot(t, freq, "b-", label="System Frequency")
    ax1.axhline(y=F_NOMINAL, color="gray", linestyle="--", alpha=0.5, label=f"Nominal ({F_NOMINAL} Hz)")
    ax1.axhline(y=FREQ_NADIR_LIMIT, color="r", linestyle="--", alpha=0.7,
                label=f"Nadir Limit ({FREQ_NADIR_LIMIT} Hz)")

    # Mark nadir
    ax1.plot(metrics["t_nadir_s"], metrics["nadir_hz"], "rv", markersize=10,
             label=f"Nadir = {metrics['nadir_hz']:.3f} Hz")

    ax1.set_ylabel("Frequency (Hz)")
    ax1.set_title(title)
    ax1.legend(loc="lower right")
    ax1.grid(True)
    ax1.set_ylim([min(freq.min() - 0.1, FREQ_NADIR_LIMIT - 0.2), F_NOMINAL + 0.1])

    # RoCoF plot
    rocof = np.gradient(freq, t)
    ax2.plot(t, rocof, "r-", label="RoCoF")
    ax2.axhline(y=-ROCOF_LIMIT, color="k", linestyle="--", alpha=0.5,
                label=f"RoCoF Limit ({ROCOF_LIMIT} Hz/s)")
    ax2.axhline(y=0, color="gray", linestyle="-", alpha=0.3)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("RoCoF (Hz/s)")
    ax2.legend(loc="lower right")
    ax2.grid(True)

    plt.tight_layout()
    filepath = os.path.join(OUTPUT_DIR, f"{filename}.{FIG_FORMAT}")
    fig.savefig(filepath)
    plt.close(fig)
    print(f"  Saved: {filepath}")
    return filepath


def plot_penetration_study(penetration_results,
                            filename="fig3_penetration_study"):
    """
    Fig 3: Impact of renewable penetration on RoCoF and frequency nadir.
    Dual y-axis: RoCoF (left) and nadir (right).
    """
    ensure_output_dir()

    levels = [r["penetration"] * 100 for r in penetration_results]
    rocofs = [abs(r["metrics"]["rocof_analytical_hz_s"]) for r in penetration_results]
    nadirs = [r["metrics"]["nadir_hz"] for r in penetration_results]
    H_values = [r["metrics"]["H_sys"] for r in penetration_results]

    fig, ax1 = plt.subplots(figsize=(10, 6))

    color1 = "#d62728"
    color2 = "#1f77b4"
    color3 = "#2ca02c"

    ax1.set_xlabel("Renewable Penetration Level (%)")

    # RoCoF
    ln1 = ax1.plot(levels, rocofs, "o-", color=color1, label="Initial RoCoF (Hz/s)",
                    markersize=8)
    ax1.set_ylabel("RoCoF (Hz/s)", color=color1)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.axhline(y=ROCOF_LIMIT, color=color1, linestyle="--", alpha=0.4,
                label=f"RoCoF Limit ({ROCOF_LIMIT} Hz/s)")

    # Nadir (right axis)
    ax2 = ax1.twinx()
    ln2 = ax2.plot(levels, nadirs, "s-", color=color2, label="Frequency Nadir (Hz)",
                    markersize=8)
    ax2.set_ylabel("Frequency Nadir (Hz)", color=color2)
    ax2.tick_params(axis="y", labelcolor=color2)
    ax2.axhline(y=FREQ_NADIR_LIMIT, color=color2, linestyle="--", alpha=0.4,
                label=f"Nadir Limit ({FREQ_NADIR_LIMIT} Hz)")

    # H_sys annotation
    ax3 = ax1.twinx()
    ax3.spines["right"].set_position(("axes", 1.12))
    ln3 = ax3.plot(levels, H_values, "^-", color=color3, label="System Inertia H_sys (s)",
                    markersize=8)
    ax3.set_ylabel("$H_{sys}$ (s)", color=color3)
    ax3.tick_params(axis="y", labelcolor=color3)

    # Combined legend
    lns = ln1 + ln2 + ln3
    labs = [l.get_label() for l in lns]
    ax1.legend(lns, labs, loc="upper left")

    ax1.set_title("Impact of Renewable Penetration on Frequency Stability")
    ax1.grid(True, alpha=0.3)

    plt.tight_layout()
    filepath = os.path.join(OUTPUT_DIR, f"{filename}.{FIG_FORMAT}")
    fig.savefig(filepath)
    plt.close(fig)
    print(f"  Saved: {filepath}")
    return filepath


def plot_multi_machine_frequency(t, gen_freqs, coi_freq, generator_data,
                                  tripped_bus, filename="fig4_multi_machine"):
    """
    Fig 4: Individual generator frequencies and COI frequency.
    """
    ensure_output_dir()

    fig, ax = plt.subplots(figsize=(12, 6))

    cmap = plt.cm.tab10
    for i, (bus, freq) in enumerate(sorted(gen_freqs.items())):
        name = generator_data.get(bus, {}).get("name", f"G{bus}")
        ax.plot(t, freq, color=cmap(i % 10), alpha=0.6, linewidth=1.0,
                label=f"{name} (Bus {bus})")

    ax.plot(t, coi_freq, "k-", linewidth=2.5, label="COI Frequency")
    ax.axhline(y=F_NOMINAL, color="gray", linestyle="--", alpha=0.4)
    ax.axhline(y=FREQ_NADIR_LIMIT, color="r", linestyle="--", alpha=0.4,
               label=f"Nadir Limit ({FREQ_NADIR_LIMIT} Hz)")

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title(f"Multi-Machine Frequency Response (Generator at Bus {tripped_bus} Tripped)")
    ax.legend(loc="lower right", fontsize=8, ncol=2)
    ax.grid(True)

    plt.tight_layout()
    filepath = os.path.join(OUTPUT_DIR, f"{filename}.{FIG_FORMAT}")
    fig.savefig(filepath)
    plt.close(fig)
    print(f"  Saved: {filepath}")
    return filepath


def plot_inertia_comparison(scenarios, filename="fig5_inertia_comparison"):
    """
    Fig 5: Compare bus inertia distribution across penetration scenarios.
    """
    ensure_output_dir()

    fig, ax = plt.subplots(figsize=(14, 6))

    n_scenarios = len(scenarios)
    buses = sorted(scenarios[0]["bus_inertia"].keys())
    x = np.arange(len(buses))
    width = 0.8 / n_scenarios

    cmap = plt.cm.viridis
    for i, scenario in enumerate(scenarios):
        H_vals = [scenario["bus_inertia"].get(b, 0) for b in buses]
        offset = (i - n_scenarios / 2 + 0.5) * width
        color = cmap(i / max(n_scenarios - 1, 1))
        ax.bar(x + offset, H_vals, width, label=f"{scenario['label']}",
               color=color, edgecolor="black", linewidth=0.2)

    ax.set_xticks(x)
    ax.set_xticklabels([str(b) for b in buses], rotation=45, fontsize=7)
    ax.set_xlabel("Bus Number")
    ax.set_ylabel("Effective Inertia $H_{eff}$ (s)")
    ax.set_title("Bus Inertia Distribution Under Different Renewable Penetration Levels")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    filepath = os.path.join(OUTPUT_DIR, f"{filename}.{FIG_FORMAT}")
    fig.savefig(filepath)
    plt.close(fig)
    print(f"  Saved: {filepath}")
    return filepath


def plot_heatmap_inertia(bus_inertia, filename="fig6_inertia_heatmap"):
    """
    Fig 6: Heatmap-style visualization of bus inertia.
    """
    ensure_output_dir()

    buses = sorted(bus_inertia.keys())
    H_values = np.array([bus_inertia[b] for b in buses])

    fig, ax = plt.subplots(figsize=(14, 3))

    norm = Normalize(vmin=H_values.min(), vmax=H_values.max())
    sm = ScalarMappable(norm=norm, cmap="RdYlGn")

    for i, (bus, H) in enumerate(zip(buses, H_values)):
        color = sm.to_rgba(H)
        ax.barh(0, 1, left=i, color=color, edgecolor="white", linewidth=0.5)
        ax.text(i + 0.5, 0, f"{bus}\n{H:.1f}", ha="center", va="center",
                fontsize=7, fontweight="bold")

    ax.set_xlim(0, len(buses))
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title("Bus Inertia Heatmap (Green=High, Red=Low)")

    cbar = fig.colorbar(sm, ax=ax, orientation="horizontal", pad=0.3,
                         label="$H_{eff}$ (s)", aspect=40)

    plt.tight_layout()
    filepath = os.path.join(OUTPUT_DIR, f"{filename}.{FIG_FORMAT}")
    fig.savefig(filepath)
    plt.close(fig)
    print(f"  Saved: {filepath}")
    return filepath
