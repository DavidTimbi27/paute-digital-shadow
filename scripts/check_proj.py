import sys
sys.path.append("/usr/share/sumo/tools")
import sumolib
import xml.etree.ElementTree as ET

net = sumolib.net.readNet("/mnt/c/Users/User/.gemini/antigravity-ide/scratch/paute-digital-shadow/net/paute.net.xml")
cx = 748843.34
cy = -307645.89

osm_tree = ET.parse("/mnt/c/Users/User/.gemini/antigravity-ide/scratch/paute-digital-shadow/data/paute.osm")
osm_root = osm_tree.getroot()

nodes = {}
for n in osm_root.findall("node"):
    nodes[n.get("id")] = (float(n.get("lon")), float(n.get("lat")))

targets = {
    "Hospital Basico": "1566875940",
    "Mercado 26F": "1566875936",
    "Mercado San Jose": "1177694166",
    "Terminal Terrestre": "1177694168",
    "GAD Paute": "1562015043",
    "Iglesia Matriz": "292005873",
    "Parque Central": "292005871",
    "Estadio": "340282070"
}

for name, way_id in targets.items():
    way = osm_root.find(f".//way[@id='{way_id}']")
    if way is not None:
        poly_3d = []
        for nd in way.findall("nd"):
            ref = nd.get("ref")
            if ref in nodes:
                lon, lat = nodes[ref]
                x, y = net.convertLonLat2XY(lon, lat)
                poly_3d.append((round(x - cx, 1), round(-(y - cy), 1)))
        
        # Centroide del polígono
        avg_x = sum(p[0] for p in poly_3d) / len(poly_3d)
        avg_z = sum(p[1] for p in poly_3d) / len(poly_3d)
        print(f"✓ {name:20} (Way {way_id}): Centro 3D: X={avg_x:.1f}, Z={avg_z:.1f} ({len(poly_3d)} vértices)")
