import json
import xml.etree.ElementTree as ET
import os
import math

net_json_path = os.path.join(os.path.dirname(__file__), "..", "web", "paute_network_3d.json")
rou_path = os.path.join(os.path.dirname(__file__), "..", "net", "paute_test.rou.xml")

with open(net_json_path, "r", encoding="utf-8") as f:
    net_data = json.load(f)

edges_map = {}
for e in net_data["edges"]:
    if e.get("lanes") and len(e["lanes"]) > 0:
        edges_map[e["id"]] = e["lanes"][0]["points"]

tree = ET.parse(rou_path)
root = tree.getroot()

big_jumps = 0
total_transitions = 0
jump_samples = []

for v in root.findall("vehicle")[:200]:
    r = v.find("route")
    if r is not None and r.get("edges"):
        eids = r.get("edges").split()
        for i in range(len(eids) - 1):
            total_transitions += 1
            e1 = eids[i]
            e2 = eids[i+1]
            if e1 in edges_map and e2 in edges_map:
                p1_end = edges_map[e1][-1]
                p2_start = edges_map[e2][0]
                d = math.hypot(p2_start[0] - p1_end[0], p2_start[2] - p1_end[2])
                if d > 30.0:
                    big_jumps += 1
                    if len(jump_samples) < 5:
                        jump_samples.append((e1, e2, d, p1_end, p2_start))

print(f"Total transitions checked: {total_transitions}")
print(f"Big jumps (>30m): {big_jumps} ({big_jumps/total_transitions*100:.1f}%)")
for s in jump_samples:
    print(f"Jump: {s[0]} -> {s[1]}: dist={s[2]:.1f}m")

