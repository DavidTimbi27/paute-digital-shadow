import xml.etree.ElementTree as ET
import os

net_path = os.path.join(os.path.dirname(__file__), "..", "net", "paute.net.xml")
tree = ET.parse(net_path)
root = tree.getroot()

center_x = 748843.34
center_y = -307645.89

# Find edges related to Barzallo and Interoceanica
barzallo_edges = {}
for e in root.findall("edge"):
    name = e.get("name", "")
    if "barzallo" in name.lower() or "miguel" in name.lower():
        barzallo_edges[e.get("id")] = (e.get("from"), e.get("to"), name)

print("Barzallo edges and their from/to junctions:")
for eid, (frm, to, name) in barzallo_edges.items():
    print(f"Edge {eid} ('{name}'): from junction {frm} to junction {to}")

# Find coordinates of these junctions
junction_ids = set()
for frm, to, _ in barzallo_edges.values():
    junction_ids.add(frm)
    junction_ids.add(to)

print("\nJunction coordinates:")
for j in root.findall("junction"):
    jid = j.get("id")
    if jid in junction_ids:
        x = float(j.get("x")) - center_x
        z = -(float(j.get("y")) - center_y)
        print(f"Junction {jid}: x={x:.2f}, z={z:.2f}, type={j.get('type')}, incLanes={j.get('incLanes')}")

