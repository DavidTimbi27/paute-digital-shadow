import json
import xml.etree.ElementTree as ET
import math
import random
import os

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
net_json_path = os.path.join(project_dir, "web", "paute_network_3d.json")
rou_path = os.path.join(project_dir, "net", "paute_test.rou.xml")
net_xml_path = os.path.join(project_dir, "net", "paute.net.xml")

with open(net_json_path, "r", encoding="utf-8") as f:
    net_data = json.load(f)

edges_map = {}
for e in net_data["edges"]:
    if e.get("lanes") and len(e["lanes"]) > 0:
        edges_map[e["id"]] = {
            "name": e.get("name", ""),
            "points": e["lanes"][0]["points"]
        }

tree = ET.parse(net_xml_path)
root = tree.getroot()
connections = {}
for conn in root.findall("connection"):
    frm = conn.get("from")
    to = conn.get("to")
    if frm in edges_map and to in edges_map:
        connections.setdefault(frm, []).append(to)

def chain_points(edge_ids):
    pts = []
    for eid in edge_ids:
        if eid not in edges_map: continue
        e_pts = edges_map[eid]["points"]
        if not e_pts: continue
        if not pts:
            pts.extend(e_pts)
        else:
            d = math.hypot(e_pts[0][0] - pts[-1][0], e_pts[0][2] - pts[-1][2])
            if d > 0.05:
                pts.extend(e_pts)
            else:
                pts.extend(e_pts[1:])
    return pts

def compute_cum_dists(pts):
    cd = [0.0]
    for i in range(len(pts) - 1):
        d = math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][2] - pts[i][2])
        cd.append(cd[-1] + max(d, 0.001))
    return cd

rou_tree = ET.parse(rou_path)
rou_root = rou_tree.getroot()
routes = []
for v in rou_root.findall("vehicle")[:500]:
    r = v.find("route")
    if r is not None and r.get("edges"):
        eids = r.get("edges").split()
        if len(eids) >= 2:
            pts = chain_points(eids)
            if len(pts) >= 4:
                routes.append({"edges": eids, "points": pts, "cum_dists": compute_cum_dists(pts)})

print(f"Loaded {len(routes)} test routes.")

vehicles = {}
counter = 0
jumps_detected = 0

for step in range(500):
    if len(vehicles) < 70 and random.random() < 0.5:
        counter += 1
        r = random.choice(routes)
        vehicles[f"v_{counter}"] = {
            "id": f"v_{counter}",
            "edges": list(r["edges"]),
            "points": list(r["points"]),
            "cum_dists": list(r["cum_dists"]),
            "traveled": 0.0,
            "speed": random.uniform(8.0, 12.0),
            "prev_pos": None
        }

    finished = []
    for vid, v in list(vehicles.items()):
        v["traveled"] += v["speed"] * 0.05
        total_len = v["cum_dists"][-1]

        if v["traveled"] >= total_len:
            # Try to extend route
            last_edge = v["edges"][-1]
            if last_edge in connections and len(v["points"]) < 200:
                next_edge = random.choice(connections[last_edge])
                next_pts = edges_map[next_edge]["points"]
                v["edges"].append(next_edge)
                # Append points and update cum_dists
                for pt in next_pts:
                    d = math.hypot(pt[0] - v["points"][-1][0], pt[2] - v["points"][-1][2])
                    if d > 0.05:
                        v["points"].append(pt)
                        v["cum_dists"].append(v["cum_dists"][-1] + d)
            else:
                finished.append(vid)
                continue

        # Find current segment
        cd = v["cum_dists"]
        dist = v["traveled"]
        seg_idx = 0
        while seg_idx < len(cd) - 2 and dist >= cd[seg_idx + 1]:
            seg_idx += 1

        d0 = cd[seg_idx]
        d1 = cd[seg_idx + 1]
        frac = (dist - d0) / max(d1 - d0, 0.001)
        p0 = v["points"][seg_idx]
        p1 = v["points"][seg_idx + 1]
        x = p0[0] + (p1[0] - p0[0]) * frac
        z = p0[2] + (p1[2] - p0[2]) * frac

        # Check for backwards jump
        if v["prev_pos"] is not None:
            move_d = math.hypot(x - v["prev_pos"][0], z - v["prev_pos"][1])
            # In 0.05s at 12 m/s, max expected distance is ~0.6m
            if move_d > 2.0:
                jumps_detected += 1
        v["prev_pos"] = (x, z)

    for vid in finished:
        del vehicles[vid]

print(f"Simulation test of 500 steps complete.")
print(f"Jumps / backward glitches detected: {jumps_detected}")
print(f"Active vehicles at end: {len(vehicles)}")

