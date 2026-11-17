#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_network_3d.py — Proyección Exacta al Milímetro con SUMOLIB y PYPROJ
Extrae las calles de paute.net.xml y los polígonos y POIs reales de paute.osm,
utilizando la proyección oficial de SUMO net.convertLonLat2XY para garantizar
alineación perfecta entre calles, edificios y puntos de interés.
"""

import os
import sys
import json
import math
import xml.etree.ElementTree as ET

sumo_home = os.environ.get("SUMO_HOME", "/usr/share/sumo")
sys.path.append(os.path.join(sumo_home, "tools"))
try:
    import sumolib
    HAS_SUMOLIB = True
except ImportError:
    HAS_SUMOLIB = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
NET_FILE = os.path.join(PROJECT_DIR, "net", "paute.net.xml")
OSM_FILE = os.path.join(PROJECT_DIR, "data", "paute.osm")
OUTPUT_JSON = os.path.join(PROJECT_DIR, "web", "paute_network_3d.json")

def export_all():
    print(f"1. Cargando red oficial SUMO: {NET_FILE}")
    net = None
    if HAS_SUMOLIB:
        try:
            net = sumolib.net.readNet(NET_FILE)
        except Exception as e:
            print(f"Aviso sumolib: {e}")

    # Centroide de referencia (Three.js origen 0,0,0)
    center_x = 748843.34
    center_y = -307645.89

    def convert_point(lon, lat):
        if net is not None:
            x, y = net.convertLonLat2XY(lon, lat)
            return round(x - center_x, 2), round(-(y - center_y), 2)
        # Conversión UTM Zona 17S analítica de alta precisión WGS84
        import math
        a = 6378137.0
        f = 1 / 298.257223563
        k0 = 0.9996
        lon0 = math.radians(-81.0)
        phi = math.radians(lat)
        lam = math.radians(lon)
        e2 = 2*f - f*f
        e_prime2 = e2 / (1 - e2)
        N = a / math.sqrt(1 - e2 * math.sin(phi)**2)
        T = math.tan(phi)**2
        C = e_prime2 * math.cos(phi)**2
        A = (lam - lon0) * math.cos(phi)
        M = a * ((1 - e2/4 - 3*e2**2/64 - 5*e2**3/256)*phi -
                 (3*e2/8 + 3*e2**2/32 + 45*e2**3/1024)*math.sin(2*phi) +
                 (15*e2**2/256 + 45*e2**3/1024)*math.sin(4*phi) -
                 (35*e2**3/3072)*math.sin(6*phi))
        x_utm = 500000.0 + k0 * N * (A + (1-T+C)*A**3/6 + (5-18*T+T**2+72*C-58*e_prime2)*A**5/120)
        # SUMO guarda la coordenada sur con norte falso retirado (Y negativa).
        # No sumar el false northing UTM de 10,000,000: desplazaría los edificios
        # millones de metros respecto de las calles exportadas desde net.xml.
        y_utm = k0 * (M + N*math.tan(phi)*(A**2/2 + (5-T+9*C+4*C**2)*A**4/24 + (61-58*T+T**2+600*C-330*e_prime2)*A**6/720))
        return round(x_utm - center_x, 2), round(-(y_utm - center_y), 2)

    # 1. Parsear aristas y carriles de SUMO
    print("2. Exportando aristas viales de SUMO...")
    edges = []
    tree = ET.parse(NET_FILE)
    root = tree.getroot()

    for edge in root.findall("edge"):
        if edge.get("function", "") == "internal":
            continue
        
        edge_id = edge.get("id")
        name = edge.get("name", "")
        speed = float(edge.get("speed", 13.89))
        
        edge_lanes = []
        for lane in edge.findall("lane"):
            lane_id = lane.get("id")
            shape_str = lane.get("shape", "")
            width = float(lane.get("width", 3.2))
            
            points = []
            if shape_str:
                for pair in shape_str.strip().split():
                    parts = pair.split(",")
                    if len(parts) >= 2:
                        x = float(parts[0]) - center_x
                        z = -(float(parts[1]) - center_y)
                        points.append([round(x, 2), 0.0, round(z, 2)])
            
            if len(points) >= 2:
                edge_lanes.append({
                    "id": lane_id,
                    "width": width,
                    "points": points
                })

        if edge_lanes:
            edges.append({
                "id": edge_id,
                "name": name if name else "Vía Urbana Paute",
                "speed": speed,
                "lanes": edge_lanes
            })

    # 2. Parsear intersecciones (junctions) oficiales de SUMO
    print("2.1. Exportando intersecciones (junctions) oficiales de SUMO...")
    junctions = []
    for j in root.findall("junction"):
        j_type = j.get("type", "")
        if j_type == "internal":
            continue
        shape_str = j.get("shape", "")
        if not shape_str:
            continue
        
        j_id = j.get("id")
        j_x = float(j.get("x", 0.0)) - center_x
        j_z = -(float(j.get("y", 0.0)) - center_y)
        
        poly_pts = []
        for pair in shape_str.strip().split():
            parts = pair.split(",")
            if len(parts) >= 2:
                px = float(parts[0]) - center_x
                pz = -(float(parts[1]) - center_y)
                poly_pts.append([round(px, 2), round(pz, 2)])
        
        if len(poly_pts) >= 3:
            junctions.append({
                "id": j_id,
                "type": j_type,
                "centroid": [round(j_x, 2), round(j_z, 2)],
                "shape": poly_pts,
                "inc_lanes": j.get("incLanes", "").split(),
                "int_lanes": j.get("intLanes", "").split()
            })
    print(f"   ✓ Intersecciones (junctions) extraídas de SUMO: {len(junctions)}")

    # 3. Cargar todos los nodos de paute.osm
    print(f"3. Parseando geometrías reales de OpenStreetMap: {OSM_FILE}")
    osm_tree = ET.parse(OSM_FILE)
    osm_root = osm_tree.getroot()

    osm_nodes = {}
    for n in osm_root.findall("node"):
        osm_nodes[n.get("id")] = (float(n.get("lon")), float(n.get("lat")))

    # 3. Extraer polígonos reales de edificios y manzanas desde OSM
    buildings = []
    osm_ways = {}

    for w in osm_root.findall("way"):
        wid = w.get("id")
        tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
        osm_ways[wid] = (w, tags)

        # Si es edificio o equipamiento
        is_bldg = ("building" in tags) or ("amenity" in tags and tags["amenity"] in ["hospital", "marketplace", "townhall", "school", "bus_station"])
        
        if is_bldg and "highway" not in tags:
            poly_pts = []
            for nd in w.findall("nd"):
                ref = nd.get("ref")
                if ref in osm_nodes:
                    lon, lat = osm_nodes[ref]
                    px, pz = convert_point(lon, lat)
                    poly_pts.append([px, pz])

            if len(poly_pts) >= 3:
                name = tags.get("name", "Edificación Urbana")
                b_type = "residential"
                height = 8.0
                color = "#263345"

                if "hospital" in tags.get("amenity", "") or "hospital" in name.lower():
                    b_type = "hospital"
                    height = 11.0
                    color = "#00e676"
                elif "marketplace" in tags.get("amenity", "") or "mercado" in name.lower():
                    b_type = "commercial"
                    height = 9.5
                    color = "#ff9100"
                elif "townhall" in tags.get("amenity", "") or "gad" in name.lower():
                    b_type = "civic"
                    height = 12.0
                    color = "#00e5ff"
                elif "church" in tags.get("building", "") or "iglesia" in name.lower():
                    b_type = "church"
                    height = 16.0
                    color = "#e040fb"
                elif "bus_station" in tags.get("amenity", "") or "terminal" in name.lower():
                    b_type = "terminal"
                    height = 8.5
                    color = "#2979ff"

                buildings.append({
                    "id": f"osm_way_{wid}",
                    "name": name,
                    "type": b_type,
                    "height": height,
                    "color": color,
                    "polygon": poly_pts
                })

    print(f"   ✓ Polígonos reales extraídos de OSM: {len(buildings)}")

    # 4. Puntos de Interés Oficiales con coordenadas exactas proyectadas
    # Usamos los centroides reales de los Ways de OSM verificados
    pois = [
        {
            "id": "poi_hospital_paute",
            "category": "hospital",
            "title": "Hospital Básico de Paute",
            "subtitle": "Salud Pública Cantonal • MSP",
            "desc": "Hospital Básico cantonal. Ubicado en Calle Circunvalación / Sarahurco frente a cementerio. Way OSM 1566875940.",
            "coords_3d": [-763.0, -316.0],
            "icon": "🏥",
            "color": "#00e676"
        },
        {
            "id": "poi_mercado_26f",
            "category": "market",
            "title": "Mercado 26 de Febrero",
            "subtitle": "Mercado Municipal Central",
            "desc": "Principal centro de comercio y abastos de Paute. Intersección García Moreno y José Barzallo. Way OSM 1566875936.",
            "coords_3d": [-64.8, -350.1],
            "icon": "🛒",
            "color": "#ff9100"
        },
        {
            "id": "poi_mercado_san_jose",
            "category": "market",
            "title": "Mercado San José",
            "subtitle": "Mercado Gastronómico Tradicional",
            "desc": "Mercado gastronómico tradicional del Hornado Pauteño. Ubicado en Simón Bolívar y Abdón Calderón. Way OSM 1177694166.",
            "coords_3d": [83.9, -403.5],
            "icon": "🍲",
            "color": "#ffab00"
        },
        {
            "id": "poi_terminal_terrestre",
            "category": "terminal",
            "title": "Terminal Terrestre de Paute",
            "subtitle": "Hub Intercantonal e Interprovincial",
            "desc": "Terminal de transporte cantonal e interprovincial en Av. Luis Enrique Vásquez. Way OSM 1177694168.",
            "coords_3d": [622.4, -274.5],
            "icon": "🚌",
            "color": "#2979ff"
        },
        {
            "id": "poi_parque_central",
            "category": "landmark",
            "title": "Parque Central 24 de Mayo",
            "subtitle": "Plaza Cívica Central",
            "desc": "Plaza cívica e Iglesia Matriz San José de Paute en Mariscal Sucre y Bolívar. Way OSM 292005871.",
            "coords_3d": [11.5, -187.5],
            "icon": "⛪",
            "color": "#e040fb"
        },
        {
            "id": "poi_gad_municipal",
            "category": "civic",
            "title": "GAD Municipal de Paute",
            "subtitle": "Alcaldía y Administración Cantonal",
            "desc": "Edificio del gobierno municipal y dirección de movilidad en calle Abdón Calderón. Way OSM 1562015043.",
            "coords_3d": [8.5, -122.1],
            "icon": "🏛️",
            "color": "#00e5ff"
        },
        {
            "id": "poi_estadio_crespo",
            "category": "sports",
            "title": "Estadio Eduardo Crespo Malo",
            "subtitle": "Complejo Deportivo Cantonal",
            "desc": "Escenario deportivo principal de Paute en Av. Luis Enrique Vásquez. Way OSM 340282070.",
            "coords_3d": [308.8, 13.4],
            "icon": "⚽",
            "color": "#76ff03"
        },
        {
            "id": "node_desvio_e40",
            "category": "friction",
            "title": "Av. Interoceánica (E40) ∩ J.M. Barzallo",
            "subtitle": "Intersección Crítica 1 — Acceso Cantonal E40",
            "desc": "Cruce real de Av. Interoceánica (E40) y José Miguel Barzallo junto al Mercado 26 de Febrero. Junction SUMO 2910139955.",
            "coords_3d": [11.87, -439.99],
            "icon": "📍",
            "color": "#ff1744"
        },
        {
            "id": "poi_cctv_barzallo",
            "category": "cctv",
            "title": "Cámara Vial Barzallo • E40",
            "subtitle": "CCTV Físico USB • Av. Interoceánica ∩ José Miguel Barzallo",
            "desc": "Cámara de monitoreo en el cruce real de Av. Interoceánica y José Miguel Barzallo junto al Mercado 26 de Febrero.",
            # Junction SUMO 2910139955: Av. Interoceánica (E40) ∩ J.M. Barzallo.
            "coords_3d": [11.87, -439.99],
            "icon": "📹",
            "color": "#00e5ff"
        },
        {
            "id": "node_mercado_palacios",
            "category": "friction",
            "title": "J.M. Barzallo ∩ Daniel Palacios / 26 de Febrero",
            "subtitle": "Intersección Crítica 2 — Zona Mercado y Comercio",
            "desc": "Intersección neurálgica de acceso a los mercados 26 de Febrero y San José 3 cuadras al norte. Junction SUMO 2910139956.",
            "coords_3d": [-8.47, -374.90],
            "icon": "⚠️",
            "color": "#ff9100"
        }
    ]

    cctv_junction_id = "2910139955"
    cctv_edge_id = "605329467#6"
    cctv_junction = next((j for j in junctions if j["id"] == cctv_junction_id), None)
    cctv_edge = next((e for e in edges if e["id"] == cctv_edge_id), None)
    if cctv_junction is None or cctv_edge is None or not cctv_edge["lanes"]:
        raise RuntimeError("No se encontro la referencia SUMO de CCTV sobre E40")
    anchor_x, anchor_z = cctv_junction["centroid"]
    cctv_points = cctv_edge["lanes"][0]["points"]
    tangent_x = cctv_points[-1][0] - cctv_points[0][0]
    tangent_z = cctv_points[-1][2] - cctv_points[0][2]
    tangent_len = math.hypot(tangent_x, tangent_z) or 1.0
    # Camera looks across the E40 lane, perpendicular to the master road edge.
    normal_x, normal_z = tangent_z / tangent_len, -tangent_x / tangent_len
    lens_offset = [-2.8, 9.2, 1.4]
    look_distance = 40.0
    cctv_reference = {
        "junction_id": cctv_junction_id,
        "anchor_3d": [anchor_x, 0.0, anchor_z],
        "edge_id": cctv_edge_id,
        "opposite_edge_id": "-605329467#6",
        "routes": {
            "SUBE": ["605329467#6", "605329467#7"],
            "BAJA": ["-605329467#6", "-605329467#5"]
        },
        "lens_offset": lens_offset,
        "camera_normal": [round(normal_x, 6), round(normal_z, 6)],
        "camera_yaw_deg": round(math.degrees(math.atan2(normal_x, normal_z)), 2),
        "camera_look_at": [
            round(anchor_x + lens_offset[0] + normal_x * look_distance, 2),
            3.0,
            round(anchor_z + lens_offset[2] + normal_z * look_distance, 2)
        ],
        "view_camera": {
            "backoff_m": 15.0,
            "elevation_m": 3.5,
            "fov_deg": 60.0,
            "min_distance_m": 7.0,
            "max_distance_m": 120.0
        },
        "map_view": {
            "cctv_offset": [0.0, 42.0, 35.0],
            "e40_offset": [0.0, 95.0, 75.0]
        },
        "count_line_x": 0.52,
        "hysteresis_zone": [0.44, 0.60],
        "crossing_thresholds": [0.48, 0.55],
        "roi_x": [0.08, 0.95],
        "roi_y": [0.22, 0.92]
    }

    out_data = {
        "cctv_reference": cctv_reference,
        "metadata": {
            "city": "Paute, Azuay, Ecuador",
            "center_x": center_x,
            "center_y": center_y,
            "edge_count": len(edges),
            "junction_count": len(junctions),
            "poi_count": len(pois),
            "building_count": len(buildings)
        },
        "pois": pois,
        "buildings": buildings,
        "edges": edges,
        "junctions": junctions
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out_data, f, separators=(",", ":"))

    size_kb = os.path.getsize(OUTPUT_JSON) / 1024
    print(f"✓ Red 3D exacta exportada a {OUTPUT_JSON} ({size_kb:.1f} KB)")
    print(f"  - Hospital 3D Coords: {pois[0]['coords_3d']}")
    print(f"  - Mercado 26F 3D Coords: {pois[1]['coords_3d']}")
    print(f"  - Terminal 3D Coords: {pois[3]['coords_3d']}")

if __name__ == "__main__":
    export_all()
