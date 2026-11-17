import xml.etree.ElementTree as ET
import json
import os

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
net_json_path = os.path.join(project_dir, "web", "paute_network_3d.json")
net_xml_path = os.path.join(project_dir, "net", "paute.net.xml")

center_x = 748843.34
center_y = -307645.89

with open(net_json_path, "r", encoding="utf-8") as f:
    net_data = json.load(f)

tree = ET.parse(net_xml_path)
root = tree.getroot()

# Map junctions
junctions = {}
for j in root.findall("junction"):
    jid = j.get("id")
    x = float(j.get("x")) - center_x
    z = -(float(j.get("y")) - center_y)
    junctions[jid] = {"x": round(x, 2), "z": round(z, 2), "type": j.get("type"), "incLanes": j.get("incLanes", "")}

# Find edges
edges_by_name = {}
for e in net_data["edges"]:
    name = e.get("name", "")
    edges_by_name.setdefault(name, []).append(e)

print("Key street names in network:")
for n in sorted(edges_by_name.keys()):
    if any(k in n.lower() for k in ["barzallo", "interoc", "palacios", "bolivar", "garcia"]):
        print(f"  '{n}': {len(edges_by_name[n])} edges")

# Check where Barzallo intersects with other streets
# Edges of Barzallo:
barzallo_eids = [e["id"] for e in net_data["edges"] if "barzallo" in e.get("name", "").lower() or "miguel" in e.get("name", "").lower()]
print(f"\nBarzallo edge IDs: {barzallo_eids}")

for e in root.findall("edge"):
    eid = e.get("id")
    if eid in barzallo_eids:
        frm = e.get("from")
        to = e.get("to")
        print(f"Edge {eid} ({e.get('name')}): from {frm} ({junctions.get(frm)}) to {to} ({junctions.get(to)})")

# Check Daniel Palacios
palacios_eids = [e["id"] for e in net_data["edges"] if "palacios" in e.get("name", "").lower()]
print(f"\nPalacios edge IDs: {palacios_eids}")
for e in root.findall("edge"):
    eid = e.get("id")
    if eid in palacios_eids:
        frm = e.get("from")
        to = e.get("to")
        print(f"Palacios Edge {eid} ({e.get('name')}): from {frm} ({junctions.get(frm)}) to {to} ({junctions.get(to)})")

