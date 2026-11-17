import xml.etree.ElementTree as ET
import json
import os

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
net_json_path = os.path.join(project_dir, "web", "paute_network_3d.json")
net_xml_path = os.path.join(project_dir, "net", "paute.net.xml")

center_x = 748843.34
center_y = -307645.89

# 1. Parse junctions from paute.net.xml
tree = ET.parse(net_xml_path)
root = tree.getroot()

junctions_list = []
for j in root.findall("junction"):
    j_type = j.get("type", "")
    if j_type == "internal":
        continue
    jid = j.get("id")
    x = float(j.get("x")) - center_x
    z = -(float(j.get("y")) - center_y)
    shape_str = j.get("shape", "")
    shape_pts = []
    if shape_str:
        for pair in shape_str.strip().split():
            parts = pair.split(",")
            if len(parts) >= 2:
                shape_pts.append([
                    round(float(parts[0]) - center_x, 2),
                    round(-(float(parts[1]) - center_y), 2)
                ])
    junctions_list.append({
        "id": jid,
        "type": j_type,
        "x": round(x, 2),
        "z": round(z, 2),
        "shape": shape_pts
    })

print(f"Parsed {len(junctions_list)} junctions from {net_xml_path}")

# 2. Update paute_network_3d.json
with open(net_json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

data["junctions"] = junctions_list

# Update POIs with EXACT, CORRECT coordinates:
# - Desvío E40 ∩ J.M. Barzallo is at junction 10940710592: [-78.05, -180.10]
# - J.M. Barzallo ∩ Daniel Palacios is at junction 2910139956: [-8.47, -374.90]
# - Cámara USB is on Barzallo right next to E40: [-76.0, -188.0]
for p in data.get("pois", []):
    if p["id"] == "node_desvio_e40":
        p["coords_3d"] = [-78.05, -180.10]
        p["title"] = "Desvío E40 ∩ J.M. Barzallo"
        p["desc"] = "Intersección exacta de Av. Interoceánica (E40) y José Miguel Barzallo."
    elif p["id"] == "node_mercado_palacios":
        p["id"] = "node_barzallo_palacios"
        p["coords_3d"] = [-8.47, -374.90]
        p["title"] = "J.M. Barzallo ∩ Daniel Palacios"
        p["desc"] = "Intersección neurálgica de José Miguel Barzallo y Daniel Palacios (acceso a Mercado 26F)."
    elif p["id"] == "poi_cctv_barzallo":
        p["coords_3d"] = [-76.0, -188.0]
        p["title"] = "Cámara USB: E40 ∩ J.M. Barzallo"
        p["desc"] = "Cámara USB en la esquina de Av. Interoceánica y José Miguel Barzallo."

with open(net_json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("paute_network_3d.json updated successfully with junctions and corrected POI coordinates!")

