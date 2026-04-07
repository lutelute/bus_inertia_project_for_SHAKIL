"""
Configuration for Bus Inertia Analysis on IEEE 39-Bus New England System.

References:
    [1] P. Kundur, Power System Stability and Control, McGraw-Hill, 1994.
    [2] A. Ulbig et al., "Impact of Low Rotational Inertia on Power System
        Stability and Operation," IFAC Proc. Volumes, vol. 47, no. 3, 2014.
    [3] F. Milano et al., "Foundations and Challenges of Low-Inertia Systems,"
        Proc. 20th PSCC, 2018.
"""

# =============================================================================
# IEEE 39-Bus Generator Inertia Constants (H in seconds)
# Standard values from Kundur [1] and related literature
# =============================================================================
# Generator bus: inertia constant H (s), MVA rating
GENERATOR_DATA = {
    30: {"H": 4.20, "S_mva": 350, "name": "G1"},
    31: {"H": 3.03, "S_mva": 830, "name": "G2"},
    32: {"H": 3.58, "S_mva": 620, "name": "G3"},
    33: {"H": 2.86, "S_mva": 750, "name": "G4"},
    34: {"H": 2.60, "S_mva": 560, "name": "G5"},
    35: {"H": 3.48, "S_mva": 680, "name": "G6"},
    36: {"H": 2.64, "S_mva": 580, "name": "G7"},
    37: {"H": 2.43, "S_mva": 890, "name": "G8"},
    38: {"H": 3.45, "S_mva": 1040, "name": "G9"},
    39: {"H": 5.00, "S_mva": 1400, "name": "G10"},  # Slack / large plant
}

# =============================================================================
# Simulation Parameters
# =============================================================================
F_NOMINAL = 60.0          # Nominal frequency (Hz)
OMEGA_NOMINAL = 2 * 3.14159265 * F_NOMINAL  # Nominal angular freq (rad/s)
S_BASE = 100.0            # System base MVA
D_COEFF = 2.0             # Damping coefficient (pu)
T_GOV = 0.2               # Governor time constant (s)
R_DROOP = 0.05            # Governor droop (pu)

# Time-domain simulation
T_START = 0.0
T_END = 20.0              # Simulation duration (s)
DT = 0.001                # Time step (s)
T_DISTURBANCE = 1.0       # Time of disturbance (s)

# =============================================================================
# Renewable Penetration Scenarios
# =============================================================================
# Each scenario: fraction of synchronous generation replaced by IBR
PENETRATION_LEVELS = [0.0, 0.20, 0.40, 0.60, 0.80]

# Generators to replace (in order of priority, smallest H first)
REPLACEMENT_ORDER = [37, 34, 36, 33, 31, 32, 35, 30, 38, 39]

# =============================================================================
# Disturbance Scenarios
# =============================================================================
# Generator trip scenarios (bus number of tripped generator)
# P_loss_mw: power lost in MW (converted to pu on total generation in simulation)
DISTURBANCE_SCENARIOS = {
    "trip_G8": {"bus": 37, "P_loss_mw": 540},    # 540 MW loss
    "trip_G10": {"bus": 39, "P_loss_mw": 1000},   # 1000 MW loss (largest)
    "trip_G2": {"bus": 31, "P_loss_mw": 573},     # 573 MW loss
}

# =============================================================================
# Thresholds (based on grid codes)
# =============================================================================
ROCOF_LIMIT = 1.0         # Maximum allowable RoCoF (Hz/s)
FREQ_NADIR_LIMIT = 59.5   # Minimum allowable frequency (Hz)
FREQ_DEADBAND = 0.036     # Governor deadband (Hz)

# =============================================================================
# Output
# =============================================================================
OUTPUT_DIR = "results"
FIG_DPI = 300
FIG_FORMAT = "png"
