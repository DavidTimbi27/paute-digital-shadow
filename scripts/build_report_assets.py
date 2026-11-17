#!/usr/bin/env python3
"""Create report illustrations from the checked-in network export (no fake observations)."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
data = json.loads((ROOT / "web" / "paute_network_3d.json").read_text(encoding="utf-8"))

fig, ax = plt.subplots(figsize=(8, 5), dpi=180)
for edge in data.get("edges", []):
    for lane in edge.get("lanes", []):
        points = lane.get("points", [])
        if len(points) > 1:
            ax.plot([p[0] for p in points], [p[2] for p in points], color="#91a4b7", lw=.65, zorder=1)
for building in data.get("buildings", []):
    points = building.get("points", building.get("polygon", []))
    if len(points) > 2:
        ax.fill([p[0] for p in points], [p[-1] for p in points], color="#d5c8ad", ec="#968c79", lw=.35, zorder=2)
ref = data["cctv_reference"]
x, _, z = ref["anchor_3d"]
ax.scatter([x], [z], s=55, c="#e63946", marker="*", zorder=5, label="CCTV / SUMO 2910139955")
ax.set_xlim(x-190, x+190); ax.set_ylim(z-190, z+190)
ax.set_aspect("equal", adjustable="box"); ax.set_xlabel("Este local (m)"); ax.set_ylabel("Norte local (m)")
ax.set_title("Red 3D exportada y referencia CCTV — entorno del cruce")
ax.grid(alpha=.18); ax.legend(loc="best", fontsize=8); fig.tight_layout()
fig.savefig(OUT / "network_junction.png", bbox_inches="tight"); plt.close(fig)

fig, ax = plt.subplots(figsize=(9, 3.3), dpi=180); ax.axis("off")
boxes = [(0.03, "Cámara USB\nvideo en vivo"), (0.23, "YOLOv11\nclase y cajas"), (0.43, "Seguimiento\nByteTrack / centroide"), (0.63, "Dirección\nSUBE / BAJA"), (0.83, "Sombra 3D\nweb + SUMO")]
for x, label in boxes:
    p = FancyBboxPatch((x, .38), .145, .30, boxstyle="round,pad=0.015", fc="#e9f5f7", ec="#187c8a", lw=1.4)
    ax.add_patch(p); ax.text(x+.0725, .53, label, ha="center", va="center", fontsize=9)
for i in range(len(boxes)-1):
    ax.annotate("", xy=(boxes[i+1][0]-.008,.53), xytext=(boxes[i][0]+.153,.53), arrowprops=dict(arrowstyle="->", lw=1.5, color="#425466"))
ax.text(.5, .16, "WebSocket /ws/telemetry · HTTP :8085 · estimación de emisiones HBEFA3", ha="center", fontsize=9, color="#425466")
ax.set_xlim(0,1); ax.set_ylim(0,1); fig.tight_layout(); fig.savefig(OUT/"pipeline.png", bbox_inches="tight", transparent=False); plt.close(fig)
print(f"Figuras generadas desde el JSON de red: {OUT}")
