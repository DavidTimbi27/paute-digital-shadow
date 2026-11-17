import xml.etree.ElementTree as ET
import os

net_path = os.path.join(os.path.dirname(__file__), "..", "net", "paute.net.xml")
tree = ET.parse(net_path)
root = tree.getroot()

center_x = 748843.34
center_y = -307645.89

junctions = []
for j in root.findall("junction"):
    j_type = j.get("type", "")
    if j_type == "internal":
        continue
    jid = j.get("id")
    x = float(j.get("x")) - center_x
    y = -(float(j.get("y")) - center_y) # z in three.js
    shape_str = j.get("shape", "")
    shape_pts = []
    if shape_str:
        for pair in shape_str.strip().split():
            parts = pair.split(",")
            if len(parts) >= 2:
                shape_pts.append([round(float(parts[0]) - center_x, 2), round(-(float(parts[1]) - center_y), 2)])
    junctions.append({
        "id": jid,
        "type": j_type,
        "x": round(x, 2),
        "z": round(y, 2),
        "shape": shape_pts
    })

print(f"Total non-internal junctions: {len(junctions)}")
print(f"Junctions with shape: {sum(1 for j in junctions if len(j['shape']) >= 3)}")
if junctions:
    print(f"Sample junction: {junctions[0]}")

