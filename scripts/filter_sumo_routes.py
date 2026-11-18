#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build SUMO demand without synthetic vehicles on the camera-controlled block."""
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "net" / "paute_test.rou.xml"
NETWORK = ROOT / "web" / "paute_network_3d.json"
DESTINATION = ROOT / "net" / "paute_camera_excluded.rou.xml"
CAMERA_CLEARANCE_M = 14.0


def main():
    network = json.loads(NETWORK.read_text(encoding="utf-8"))
    reference = network["cctv_reference"]
    anchor_x, _, anchor_z = reference["anchor_3d"]
    reserved_edges = {
        edge for route in reference["routes"].values() for edge in route
    }
    edge_points = {
        edge["id"]: [point for lane in edge.get("lanes", []) for point in lane.get("points", [])]
        for edge in network.get("edges", [])
    }

    tree = ET.parse(SOURCE)
    root = tree.getroot()
    removed = 0
    for vehicle in list(root.findall("vehicle")):
        route = vehicle.find("route")
        edge_ids = route.get("edges", "").split() if route is not None else []
        touches_camera_route = bool(reserved_edges.intersection(edge_ids))
        enters_camera_clearance = any(
            math.hypot(point[0] - anchor_x, point[2] - anchor_z) < CAMERA_CLEARANCE_M
            for edge_id in edge_ids
            for point in edge_points.get(edge_id, [])
        )
        if touches_camera_route or enters_camera_clearance:
            root.remove(vehicle)
            removed += 1

    tree.write(DESTINATION, encoding="UTF-8", xml_declaration=True)
    kept = len(root.findall("vehicle"))
    print(f"SUMO routes: {kept} retained, {removed} removed near CCTV.")
    print(f"Wrote {DESTINATION.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
