"""
Publication-quality figures for the SAR ablation experiment.

Run Set 1 (nominal):  3 configs × scenario A, N=40 each
  Files: nominal_full_a.csv, nominal_no_gate_a.csv, nominal_llm_only_a.csv
  (Falls back to results_full_a/no_gate/text_only CSVs if nominal files absent)

Run Set 2 (fault):    3 configs × scenario A, N=40 each (mixed fault modes)
  Files: fault_full_a.csv, fault_no_gate_a.csv, fault_llm_only_a.csv

Generalization (nominal, all 3 scenarios × full config):
  Files: results_full_{a,b,c}.csv  (or nominal_full_{a,b,c}.csv)

Output: sar_ws/figures/
Run from sar_ws/src/sar_crew/ with the project venv activated.
"""
import csv
import math
import os
import statistics

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── style ──────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family':       'serif',
    'font.size':         11,
    'axes.labelsize':    12,
    'axes.titlesize':    12,
    'axes.spines.top':   False,
    'axes.spines.right': False,
    'xtick.labelsize':   10,
    'ytick.labelsize':   10,
    'legend.fontsize':   10,
    'legend.framealpha': 0.9,
    'figure.dpi':        150,
    'savefig.dpi':       300,
    'savefig.bbox':      'tight',
})

BASE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.environ.get('SAR_FIG_OUT', os.path.join(BASE, 'figures'))
os.makedirs(OUT, exist_ok=True)

COLORS = {
    'full':     '#2196F3',
    'no_gate':  '#FF9800',
    'llm_only': '#F44336',
    # scenario colours
    'A': '#2196F3', 'B': '#4CAF50', 'C': '#FF9800',
    # timing colours
    'search':   '#42A5F5',
    'navigate': '#66BB6A',
    'planning': '#FFA726',
}
CONFIG_LABELS = {
    'full':     'Full System (Ours)',
    'no_gate':  'Skill-List (No Gate)',
    'llm_only': 'LLM-Only',
}
SCENARIO_LABELS = {
    'a': 'Scenario A\n(Baseline)',
    'b': 'Scenario B\n(Near-field)',
    'c': 'Scenario C\n(Far-field)',
}

# ── helpers ────────────────────────────────────────────────────────────────
def _try_load(paths: list, n: int = 40):
    """Try each path in order, return first that exists (up to n valid rows)."""
    for p in paths:
        if os.path.exists(p):
            with open(p) as f:
                rows = list(csv.DictReader(f))
            # drop anomalous rows (stuck drone)
            rows = [r for r in rows
                    if r.get('search_duration_s', '') in ('', 'nan')
                    or float(r['search_duration_s']) < 1000]
            print(f"  Loaded {len(rows[:n])} rows from {os.path.basename(p)}")
            return rows[:n]
    print(f"  WARNING: none of {[os.path.basename(p) for p in paths]} found — cell empty")
    return []


def fv(row, key):
    v = row.get(key, '')
    try:
        x = float(v)
        return float('nan') if math.isnan(x) else x
    except (ValueError, TypeError):
        return float('nan')


def stat(rows, key):
    vals = [fv(r, key) for r in rows if not math.isnan(fv(r, key))]
    if not vals:
        return float('nan'), 0.0, []
    m = statistics.mean(vals)
    s = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return m, s, vals


def rate(rows, key):
    if not rows:
        return float('nan')
    return 100.0 * sum(1 for r in rows if fv(r, key) == 1.0) / len(rows)


def real_success(rows):
    if not rows:
        return float('nan')
    return 100.0 * sum(1 for r in rows
                       if not math.isnan(fv(r, 'delivery_error'))
                       and fv(r, 'delivery_error') < 1.0) / len(rows)


def plan_exec_rate(rows):
    """Rover actually dispatched AND coordinates were within 2 m of victim."""
    if not rows:
        return float('nan')
    return 100.0 * sum(
        1 for r in rows
        if r.get('navigate_duration_s', '') not in ('', 'nan')
        and fv(r, 'plan_executability') == 1.0
    ) / len(rows)


def hallu_rate(rows):
    """Mean tool hallucination rate across runs that had any tool references."""
    vals = [fv(r, 'tool_hallucination_rate') for r in rows]
    vals = [v * 100 for v in vals if not math.isnan(v)]
    return statistics.mean(vals) if vals else float('nan')


def false_dispatch_rate(rows):
    return rate(rows, 'false_dispatch')


# ── load nominal run set (Run Set 1) ──────────────────────────────────────
print("\n=== Loading nominal run set ===")
CONFIGS   = ['full', 'no_gate', 'llm_only']
SCENARIOS = ['a', 'b', 'c']

NOM = {}
# Config × scenario A (primary ablation)
for cfg in CONFIGS:
    NOM[cfg] = _try_load([
        f'{BASE}/nominal_{cfg}_a.csv',
        f'{BASE}/results_{cfg}_a.csv',
        f'{BASE}/results_{"text_only" if cfg == "llm_only" else cfg}_a.csv',
    ], n=40)

# Full system generalization across B and C
GEN = {}
for sc in SCENARIOS:
    GEN[sc] = _try_load([
        f'{BASE}/nominal_full_{sc}.csv',
        f'{BASE}/results_full_{sc}.csv',
    ], n=40)

# ── load fault-injection run set (Run Set 2) ──────────────────────────────
print("\n=== Loading fault-injection run set ===")
FAULT = {}
for cfg in CONFIGS:
    FAULT[cfg] = _try_load([
        f'{BASE}/fault_{cfg}_a.csv',
    ], n=40)

# ══════════════════════════════════════════════════════════════════════════
# FIG 1 — Nominal: Delivery error per config (Scenario A)
# ══════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

# Left: delivery error grouped bar
ax = axes[0]
x  = np.arange(len(CONFIGS))
w  = 0.55
means = [stat(NOM[c], 'delivery_error')[0] for c in CONFIGS]
stds  = [stat(NOM[c], 'delivery_error')[1] for c in CONFIGS]
cols  = [COLORS[c] for c in CONFIGS]
bars  = ax.bar(x, means, w, color=cols, edgecolor='white', linewidth=0.8)
ax.errorbar(x, means, yerr=stds, fmt='none',
            ecolor='#333', elinewidth=1.4, capsize=5)
ax.axhline(1.0, color='red', linestyle='--', linewidth=1.2, alpha=0.7,
           label='Effective-reach threshold (1 m)')
for xi, m in zip(x, means):
    if not math.isnan(m):
        ax.text(xi, m + 0.2, f'{m:.2f} m', ha='center', va='bottom',
                fontsize=9, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels([CONFIG_LABELS[c] for c in CONFIGS], fontsize=9)
ax.set_ylabel('Delivery error (m)')
ax.set_title('Delivery Error — Nominal (Scenario A)')
ax.set_ylim(0, 12)
ax.legend(fontsize=9)

# Right: rate bars — mission success / grounding / plan exec
ax = axes[1]
metric_labels = ['Rescue\nCompleted', 'Skill\nGrounding', 'Plan\nExecutable',
                 'Tool Halluc.\nRate']
xm = np.arange(len(metric_labels))
wm = 0.2
offsets = np.linspace(-wm * 1.1, wm * 1.1, len(CONFIGS))

for i, cfg in enumerate(CONFIGS):
    rows = NOM[cfg]
    vals = [
        real_success(rows),
        rate(rows, 'grounding_ok'),
        plan_exec_rate(rows),
        hallu_rate(rows),
    ]
    ax.bar(xm + offsets[i], vals, wm * 0.9,
           label=CONFIG_LABELS[cfg], color=COLORS[cfg],
           edgecolor='white', linewidth=0.8)
    for xi, v in zip(xm + offsets[i], vals):
        if not math.isnan(v):
            ax.text(xi, v + 1.5, f'{v:.0f}%', ha='center', va='bottom',
                    fontsize=7.5, fontweight='bold', color=COLORS[cfg])

ax.set_xticks(xm)
ax.set_xticklabels(metric_labels, fontsize=9)
ax.set_ylim(0, 125)
ax.set_ylabel('Rate (%)')
ax.set_title('Planning Config Comparison — Nominal (Scenario A)')
ax.legend(loc='upper right', fontsize=9)
ax.axhline(100, color='#bbb', linestyle=':', linewidth=0.8)

plt.tight_layout()
plt.savefig(f'{OUT}/fig1_nominal_comparison.pdf')
plt.savefig(f'{OUT}/fig1_nominal_comparison.png')
plt.close()
print("Saved fig1_nominal_comparison")


# ══════════════════════════════════════════════════════════════════════════
# FIG 2 — Fault injection: false-dispatch rate and delivery error
# ══════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

# Left: false dispatch rate — nominal vs fault
ax = axes[0]
x = np.arange(len(CONFIGS))
w = 0.35
nom_fd  = [false_dispatch_rate(NOM[c])   for c in CONFIGS]
fault_fd = [false_dispatch_rate(FAULT[c]) for c in CONFIGS]

b1 = ax.bar(x - w/2, nom_fd,   w * 0.9, label='Nominal',
            color=[COLORS[c] for c in CONFIGS], edgecolor='white',
            linewidth=0.8, alpha=0.5)
b2 = ax.bar(x + w/2, fault_fd, w * 0.9, label='Fault-injected',
            color=[COLORS[c] for c in CONFIGS], edgecolor='white',
            linewidth=0.8)

for xi, v in zip(x + w/2, fault_fd):
    if not math.isnan(v):
        ax.text(xi, v + 1, f'{v:.0f}%', ha='center', va='bottom',
                fontsize=9, fontweight='bold')

ax.set_xticks(x)
ax.set_xticklabels([CONFIG_LABELS[c] for c in CONFIGS], fontsize=9)
ax.set_ylabel('False-dispatch rate (%)')
ax.set_title('False Dispatch: Nominal vs. Fault-Injected')
ax.set_ylim(0, 115)
# custom legend: hatching shows nominal/fault
from matplotlib.patches import Patch
leg_handles = [Patch(facecolor='#999', alpha=0.5, label='Nominal'),
               Patch(facecolor='#999', label='Fault-injected')]
ax.legend(handles=leg_handles, fontsize=9)

# Right: delivery error — nominal vs fault
ax = axes[1]
nom_de   = [stat(NOM[c],   'delivery_error')[0] for c in CONFIGS]
fault_de = [stat(FAULT[c], 'delivery_error')[0] for c in CONFIGS]
nom_de_s   = [stat(NOM[c],   'delivery_error')[1] for c in CONFIGS]
fault_de_s = [stat(FAULT[c], 'delivery_error')[1] for c in CONFIGS]

b1 = ax.bar(x - w/2, nom_de,   w * 0.9,
            color=[COLORS[c] for c in CONFIGS], edgecolor='white',
            linewidth=0.8, alpha=0.5)
b2 = ax.bar(x + w/2, fault_de, w * 0.9,
            color=[COLORS[c] for c in CONFIGS], edgecolor='white',
            linewidth=0.8)
ax.errorbar(x - w/2, nom_de,   yerr=nom_de_s,   fmt='none',
            ecolor='#555', elinewidth=1.2, capsize=4, alpha=0.5)
ax.errorbar(x + w/2, fault_de, yerr=fault_de_s, fmt='none',
            ecolor='#333', elinewidth=1.2, capsize=4)
ax.axhline(1.0, color='red', linestyle='--', linewidth=1.2, alpha=0.7)
ax.set_xticks(x)
ax.set_xticklabels([CONFIG_LABELS[c] for c in CONFIGS], fontsize=9)
ax.set_ylabel('Delivery error (m)')
ax.set_title('Delivery Error: Nominal vs. Fault-Injected')
ax.set_ylim(0, 14)
ax.legend(handles=leg_handles, fontsize=9)

plt.tight_layout()
plt.savefig(f'{OUT}/fig2_fault_injection.pdf')
plt.savefig(f'{OUT}/fig2_fault_injection.png')
plt.close()
print("Saved fig2_fault_injection")


# ══════════════════════════════════════════════════════════════════════════
# FIG 3 — Safety gate recall: full vs no_gate on fault injection
# (false-dispatch rate breakdown by fault mode)
# ══════════════════════════════════════════════════════════════════════════
FAULT_MODES_NON_NONE = ['corrupted_coords', 'nan_transmission',
                        'missed_detection', 'blocked_corridor']
FAULT_LABELS = {
    'corrupted_coords': 'Corrupt\nCoords',
    'nan_transmission': 'NaN\nTransmit',
    'missed_detection': 'Missed\nDetect',
    'blocked_corridor': 'Blocked\nCorridor',
}

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

for ax_idx, (cfg, ax) in enumerate(zip(['full', 'no_gate'], axes)):
    rows = FAULT[cfg]
    by_mode = {m: [r for r in rows if r.get('fault') == m]
               for m in FAULT_MODES_NON_NONE}
    fd_rates = [false_dispatch_rate(by_mode[m]) for m in FAULT_MODES_NON_NONE]
    de_means = [stat(by_mode[m], 'delivery_error')[0] for m in FAULT_MODES_NON_NONE]

    x = np.arange(len(FAULT_MODES_NON_NONE))
    w = 0.35
    col = COLORS[cfg]

    b1 = ax.bar(x - w/2, fd_rates, w * 0.9, color=col, alpha=0.65,
                edgecolor='white', label='False-dispatch rate (%)')
    b2 = ax.bar(x + w/2, [min(d, 14) for d in de_means], w * 0.9,
                color=col, edgecolor='white', label='Delivery error (m, clipped 14)')

    ax.set_xticks(x)
    ax.set_xticklabels([FAULT_LABELS[m] for m in FAULT_MODES_NON_NONE], fontsize=9)
    ax.set_ylim(0, 16)
    ax.set_title(f'{CONFIG_LABELS[cfg]} — Per-Fault Breakdown')
    ax.legend(fontsize=9)
    if ax_idx == 0:
        ax.set_ylabel('Rate (%) or Error (m)')

plt.tight_layout()
plt.savefig(f'{OUT}/fig3_gate_recall_breakdown.pdf')
plt.savefig(f'{OUT}/fig3_gate_recall_breakdown.png')
plt.close()
print("Saved fig3_gate_recall_breakdown")


# ══════════════════════════════════════════════════════════════════════════
# FIG 4 — Timing breakdown per scenario (full config, generalization)
# ══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(7, 4.5))

sc_labels = [SCENARIO_LABELS[s] for s in SCENARIOS]

pl_m = [stat(GEN[sc], 'planning_latency_s')[0]  for sc in SCENARIOS]
sd_m = [stat(GEN[sc], 'search_duration_s')[0]   for sc in SCENARIOS]
nd_m = [stat(GEN[sc], 'navigate_duration_s')[0] for sc in SCENARIOS]
pl_s = [stat(GEN[sc], 'planning_latency_s')[1]  for sc in SCENARIOS]
sd_s = [stat(GEN[sc], 'search_duration_s')[1]   for sc in SCENARIOS]
nd_s = [stat(GEN[sc], 'navigate_duration_s')[1] for sc in SCENARIOS]

x = np.arange(len(SCENARIOS))
w = 0.45

ax.bar(x, pl_m, w, label='LLM Planning',    color=COLORS['planning'], edgecolor='white')
ax.bar(x, sd_m, w, bottom=pl_m,             label='Drone Search',     color=COLORS['search'],   edgecolor='white')
ax.bar(x, nd_m, w,
       bottom=[p+s for p,s in zip(pl_m, sd_m)],
       label='Rover Navigation', color=COLORS['navigate'], edgecolor='white')

totals    = [p+s+n for p,s,n in zip(pl_m, sd_m, nd_m)]
total_err = [math.sqrt(pe**2+se**2+ne**2) for pe,se,ne in zip(pl_s, sd_s, nd_s)]
ax.errorbar(x, totals, yerr=total_err, fmt='none',
            ecolor='#333', elinewidth=1.5, capsize=5)
for xi, tot in zip(x, totals):
    if not math.isnan(tot):
        ax.text(xi, tot + 4, f'{tot:.0f}s', ha='center', va='bottom',
                fontsize=9.5, fontweight='bold')

ax.set_xticks(x)
ax.set_xticklabels(sc_labels)
ax.set_ylabel('Time (s)')
ax.set_title('Mission Timing Breakdown per Scenario — Full System')
ax.legend(loc='upper left')
ax.set_ylim(0, 180)

plt.tight_layout()
plt.savefig(f'{OUT}/fig4_timing_breakdown.pdf')
plt.savefig(f'{OUT}/fig4_timing_breakdown.png')
plt.close()
print("Saved fig4_timing_breakdown")


# ══════════════════════════════════════════════════════════════════════════
# FIG 5 — Delivery error across 3 scenarios (full config, generalization)
# ══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(6, 4))

sc_colors = [COLORS['A'], COLORS['B'], COLORS['C']]
de_data   = [stat(GEN[sc], 'delivery_error')[2] for sc in SCENARIOS]

bp = ax.boxplot(de_data, patch_artist=True, widths=0.4,
                medianprops={'color': 'black', 'linewidth': 2},
                whiskerprops={'linewidth': 1.2},
                capprops={'linewidth': 1.2},
                flierprops={'marker': 'o', 'markersize': 4, 'alpha': 0.5})
for patch, col in zip(bp['boxes'], sc_colors):
    patch.set_facecolor(col)
    patch.set_alpha(0.75)

rng = np.random.default_rng(42)
for i, (vals, col) in enumerate(zip(de_data, sc_colors), start=1):
    if vals:
        jitter = rng.uniform(-0.12, 0.12, len(vals))
        ax.scatter([i+j for j in jitter], vals, color=col, alpha=0.7, s=22, zorder=3)

ax.set_xticks(range(1, 4))
ax.set_xticklabels(['Scenario A', 'Scenario B', 'Scenario C'])
ax.set_ylabel('Delivery error (m)')
ax.set_title('Rover Delivery Accuracy — Full System Across Scenarios')
ax.set_ylim(0.44, 0.56)

plt.tight_layout()
plt.savefig(f'{OUT}/fig5_delivery_box_full.pdf')
plt.savefig(f'{OUT}/fig5_delivery_box_full.png')
plt.close()
print("Saved fig5_delivery_box_full")


# ══════════════════════════════════════════════════════════════════════════
# FIG 6 — World maps (top-down 2D) for all 3 scenarios
# ══════════════════════════════════════════════════════════════════════════
SCENARIOS_GEO = {
    'a': {
        'rubble': [(4.0,3.0,1.0,0.75,0.4),(-3.0,5.0,0.75,0.75,-0.3),(2.0,-4.0,1.5,0.5,0.9)],
        'victim': (5.0, 5.0),
        'search': (-3, 8, -3, 8),
    },
    'b': {
        'rubble': [(-2.5,1.0,1.6,0.3,1.4),(1.0,2.0,0.5,0.5,0.0),(-5.0,-1.0,0.6,0.6,0.5)],
        'victim': (-3.0, 4.0),
        'search': (-8, 3, -3, 8),
    },
    'c': {
        'rubble': [(2.0,-1.0,1.0,1.0,0.2),(4.0,-3.0,1.3,0.6,1.0),
                   (6.0,-1.0,0.8,0.8,-0.5),(3.0,-5.0,1.5,0.5,0.3)],
        'victim': (8.0, -4.0),
        'search': (-2, 9, -9, 2),
    },
}
ROVER_SPAWN = (-2.0, -2.0)
DRONE_SPAWN = (1.01, 0.98)


def draw_rotated_box(ax, cx, cy, hlx, hly, yaw, color='#795548', alpha=0.75):
    c, s = math.cos(yaw), math.sin(yaw)
    corners = [(-hlx,-hly),(-hlx,hly),(hlx,hly),(hlx,-hly)]
    world = [(cx + c*lx - s*ly, cy + s*lx + c*ly) for lx,ly in corners]
    ax.add_patch(plt.Polygon(world, closed=True, facecolor=color,
                             edgecolor='#444', linewidth=0.8, alpha=alpha))


fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))
bounds_map = {'a':(-4,9,-4,9), 'b':(-9,4,-4,9), 'c':(-3,10,-10,3)}
titles = {
    'a': 'Scenario A — Baseline',
    'b': 'Scenario B — Near-field',
    'c': 'Scenario C — Far-field',
}

for ax, sc in zip(axes, SCENARIOS):
    geo = SCENARIOS_GEO[sc]
    xmin,xmax,ymin,ymax = bounds_map[sc]
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect('equal')
    ax.set_facecolor('#F5F5F5')
    ax.grid(True, linestyle=':', linewidth=0.4, color='#CCC')

    for obs in geo['rubble']:
        draw_rotated_box(ax, *obs)

    sb = geo['search']
    ax.add_patch(mpatches.Rectangle(
        (sb[0], sb[2]), sb[1]-sb[0], sb[3]-sb[2],
        linewidth=1.4, edgecolor='#2196F3', facecolor='#2196F3',
        alpha=0.07, linestyle='--'))

    vx, vy = geo['victim']
    ax.scatter([vx], [vy], marker='*', s=250, color='red', zorder=5)
    ax.annotate(f'Victim\n({vx},{vy})', (vx, vy),
                textcoords='offset points', xytext=(6,6), fontsize=8, color='red')

    ax.scatter(*ROVER_SPAWN, marker='s', s=90, color=COLORS['navigate'], zorder=5)
    ax.annotate('TurtleBot3', ROVER_SPAWN,
                textcoords='offset points', xytext=(4,-13), fontsize=8,
                color=COLORS['navigate'])

    ax.scatter(*DRONE_SPAWN, marker='^', s=90, color=COLORS['search'], zorder=5)
    ax.annotate('IRIS', DRONE_SPAWN,
                textcoords='offset points', xytext=(4,5), fontsize=8,
                color=COLORS['search'])

    ax.set_xlabel('x (m)')
    if sc == 'a':
        ax.set_ylabel('y (m)')
    ax.set_title(titles[sc], fontweight='bold')

legend_els = [
    mpatches.Patch(facecolor='#795548', alpha=0.75, label='Obstacle'),
    plt.Line2D([0],[0], marker='*', color='w', markerfacecolor='red', markersize=11, label='Victim'),
    plt.Line2D([0],[0], marker='s', color='w', markerfacecolor=COLORS['navigate'], markersize=9, label='Rover spawn'),
    plt.Line2D([0],[0], marker='^', color='w', markerfacecolor=COLORS['search'], markersize=9, label='Drone spawn'),
    mpatches.Patch(facecolor='#2196F3', alpha=0.15, edgecolor='#2196F3',
                   linestyle='--', linewidth=1.4, label='Search zone'),
]
fig.legend(handles=legend_els, loc='lower center', ncol=5,
           bbox_to_anchor=(0.5,-0.07), framealpha=0.9)
plt.tight_layout()
plt.savefig(f'{OUT}/fig6_scenario_maps.pdf', bbox_inches='tight')
plt.savefig(f'{OUT}/fig6_scenario_maps.png', bbox_inches='tight')
plt.close()
print("Saved fig6_scenario_maps")


# ══════════════════════════════════════════════════════════════════════════
# FIG 7 — Gantt mission timeline (full system, Scenario A)
# ══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(10, 3))

rows_a = GEN['a'] or NOM['full']
rep_plan   = stat(rows_a, 'planning_latency_s')[0] or 1.8
rep_search = stat(rows_a, 'search_duration_s')[0] or 18.9
rep_nav    = stat(rows_a, 'navigate_duration_s')[0] or 72.4

phases    = ['LLM Planning', 'Drone Takeoff & Search', 'Perception Confirm', 'Fly-to Overhead', 'Rover Navigation']
starts    = [0, rep_plan, rep_plan+rep_search, rep_plan+rep_search+1.5, rep_plan+rep_search+3.5]
durations = [rep_plan, rep_search, 1.5, 2.0, rep_nav]
y_pos     = [0.7, 0.3, 0.3, 0.3, 0.7]
colors_g  = [COLORS['planning'], COLORS['search'], '#AB47BC', COLORS['search'], COLORS['navigate']]

for ph, st, du, col, yp in zip(phases, starts, durations, colors_g, y_pos):
    ax.barh(yp, du, left=st, height=0.28, color=col, edgecolor='white',
            linewidth=0.8, alpha=0.88)
    if du > 3:
        ax.text(st+du/2, yp, ph, ha='center', va='center',
                fontsize=8.5, color='white', fontweight='bold')

gate_x = rep_plan + rep_search + 3.5
ax.axvline(gate_x, color='red', linestyle='--', linewidth=1.8, alpha=0.8)
ax.text(gate_x+1, 0.5, '← Workflow gate\n  rover released', fontsize=8.5,
        color='red', va='center')

ax.set_yticks([0.3, 0.7])
ax.set_yticklabels(['IRIS Drone', 'Ground Rover'])
ax.set_xlabel('Time (s)')
ax.set_xlim(0, rep_plan+rep_search+3.5+rep_nav+8)
ax.set_title('Mission Execution Timeline — Full System, Scenario A (mean values)')

legend_els = [mpatches.Patch(color=COLORS['planning'], label='LLM planning'),
              mpatches.Patch(color=COLORS['search'],   label='Drone operation'),
              mpatches.Patch(color='#AB47BC',          label='Perception'),
              mpatches.Patch(color=COLORS['navigate'], label='Rover navigation')]
ax.legend(handles=legend_els, loc='lower right', fontsize=9)
plt.tight_layout()
plt.savefig(f'{OUT}/fig7_mission_timeline.pdf')
plt.savefig(f'{OUT}/fig7_mission_timeline.png')
plt.close()
print("Saved fig7_mission_timeline")


# ══════════════════════════════════════════════════════════════════════════
# FIG 8 — Euclidean vs A* path length per scenario (full system)
# ══════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(6, 4))

SPAWN = (-2.0, -2.0)
victims = {'a':(5,5), 'b':(-3,4), 'c':(8,-4)}
euclid  = {sc: math.hypot(v[0]-SPAWN[0], v[1]-SPAWN[1]) for sc,v in victims.items()}
# A* path length estimated from nav time × 0.15 m/s
astar_est = {}
for sc in SCENARIOS:
    nd, _, _ = stat(GEN[sc], 'navigate_duration_s')
    astar_est[sc] = nd * 0.15 if not math.isnan(nd) else float('nan')
ratios = {sc: euclid[sc]/astar_est[sc] if not math.isnan(astar_est[sc]) else float('nan')
          for sc in SCENARIOS}

x = np.arange(3)
w = 0.32
sc_labels_short = ['Scenario A', 'Scenario B', 'Scenario C']

ax.bar(x-w/2, [euclid[s] for s in SCENARIOS], w,
       label='Euclidean distance', color='#90CAF9', edgecolor='white')
ax.bar(x+w/2, [astar_est[s] for s in SCENARIOS], w,
       label='A* path length (est.)', color=COLORS['navigate'], edgecolor='white')

for xi, sc in zip(x, SCENARIOS):
    if not math.isnan(ratios[sc]):
        ax.text(xi+w/2, astar_est[sc]+0.3, f'ratio\n{ratios[sc]:.2f}',
                ha='center', va='bottom', fontsize=8.5)

ax.set_xticks(x)
ax.set_xticklabels(sc_labels_short)
ax.set_ylabel('Distance (m)')
ax.set_title('Euclidean vs. A* Path Length per Scenario')
ax.legend()
plt.tight_layout()
plt.savefig(f'{OUT}/fig8_path_comparison.pdf')
plt.savefig(f'{OUT}/fig8_path_comparison.png')
plt.close()
print("Saved fig8_path_comparison")


print(f"\nAll figures saved to {OUT}/")
print("Files:", sorted(os.listdir(OUT)))
