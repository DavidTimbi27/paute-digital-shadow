#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server_web.py — Servidor Web & Telemetría en Tiempo Real (Coordenadas Exactas)
Sombra Digital de Paute, Azuay
- Confinamiento topológico y parque automotor de Paute.
- Concentración real en Mercados 26 de Febrero y San José (X=-64.8, Z=-350.1).
- Tránsito fluido y continuo en Av. Interoceánica y José Miguel Barzallo (Cámara USB).
- Rutas multicarretera continuas a través de intersecciones (elimina desaparición en esquinas).
- Soporte dual aiohttp / FastAPI para máxima portabilidad (WSL o Windows nativo).
"""

import os
import sys
import importlib.util
import ipaddress
import json
import asyncio
import logging
import random
import math
import socket
import base64
import io
import time
import threading
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image
from collections import deque

try:
    import cv2
except Exception:
    cv2 = None

try:
    HAS_BYTETRACK = importlib.util.find_spec("lap") is not None
except (ImportError, ValueError):
    HAS_BYTETRACK = False

# Configuración de entorno para Ultralytics YOLOv11 en sandbox
os.environ["YOLO_CONFIG_DIR"] = os.path.join(tempfile.gettempdir(), "yolo_cfg")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
try:
    import torch
    torch.set_num_threads(2)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    from ultralytics import YOLO
    HAS_YOLO = True
except Exception as _e:
    HAS_YOLO = False

# Configuración de rutas
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
WEB_DIR = os.path.join(PROJECT_DIR, "web")
NET_JSON_FILE = os.path.join(WEB_DIR, "paute_network_3d.json")
NET_XML_FILE = os.path.join(PROJECT_DIR, "net", "paute.net.xml")
ROU_XML_FILE = os.path.join(PROJECT_DIR, "net", "paute_test.rou.xml")

sumo_home = os.environ.get("SUMO_HOME", "/usr/share/sumo")
os.environ["SUMO_HOME"] = sumo_home
tools_dir = os.path.join(sumo_home, "tools")
if os.path.isdir(tools_dir) and tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WebBridge")

connected_websockets = set()
traci_client = None

class RTSPCamera:
    """OpenCV RTSP reader; credentials are kept in memory and never returned by the API."""
    def __init__(self):
        self.url = ""
        self.lock = threading.Lock()
        self.frame = None
        self.running = False
        self.thread = None
        self.reconfigure_event = threading.Event()

    def configure(self, ip, username, password):
        from urllib.parse import quote
        safe_user = quote(username.strip(), safe="")
        safe_password = quote(password, safe="")
        self.url = f"rtsp://{safe_user}:{safe_password}@{ip.strip()}:554/H.264"
        with self.lock:
            self.frame = None
        self.reconfigure_event.set()
        return self.start()

    def start(self):
        if not self.url or cv2 is None:
            return False
        if self.thread and self.thread.is_alive():
            return True
        self.running = True
        self.thread = threading.Thread(target=self._read, daemon=True, name="ezviz-rtsp")
        self.thread.start()
        return True

    def _read(self):
        while self.running:
            self.reconfigure_event.clear()
            url = self.url
            if not url:
                time.sleep(0.25)
                continue
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                if self.reconfigure_event.is_set():
                    continue
                time.sleep(3)
                continue
            while self.running and not self.reconfigure_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                with self.lock:
                    self.frame = frame
            cap.release()
            if not self.reconfigure_event.is_set():
                time.sleep(1)

    def jpeg(self):
        with self.lock:
            frame = None if self.frame is None else self.frame.copy()
        if frame is None:
            return None
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return encoded.tobytes() if ok else None

rtsp_camera = RTSPCamera()

# Parque automotor calibrado para Paute, Azuay
FLEET_CONFIG = {
    "moto": {
        "sumo_vtype": "vtype_moto",
        "name": "Motocicleta 150cc",
        "category": "Dos Ruedas",
        "fuel": "Gasolina Extra",
        "co2_base_g_km": 42.0,
        "consumption_l_100": 2.8,
        "nominal_speed": 10.5,
        "accel": 3.2,
        "weight": 0.18
    },
    "car": {
        "sumo_vtype": "vtype_car_gasoline",
        "name": "Sedán / Taxi",
        "category": "Particular / Taxi",
        "fuel": "Gasolina Extra/Súper",
        "co2_base_g_km": 138.0,
        "consumption_l_100": 7.4,
        "nominal_speed": 11.2,
        "accel": 2.6,
        "weight": 0.44
    },
    "pickup": {
        "sumo_vtype": "vtype_pickup_diesel",
        "name": "Camioneta D-Max/Hilux",
        "category": "Transporte Mixto / Rural",
        "fuel": "Diésel Premium",
        "co2_base_g_km": 182.0,
        "consumption_l_100": 8.9,
        "nominal_speed": 11.0,
        "accel": 2.2,
        "weight": 0.22
    },
    "bus": {
        "sumo_vtype": "vtype_bus_diesel",
        "name": "Autobús Urbano/Intercantonal",
        "category": "Transporte Público",
        "fuel": "Diésel",
        "co2_base_g_km": 590.0,
        "consumption_l_100": 24.5,
        "nominal_speed": 8.5,
        "accel": 1.2,
        "weight": 0.06
    },
    "truck": {
        "sumo_vtype": "vtype_truck_delivery",
        "name": "Camión Abastos / Mercado",
        "category": "Carga Liviana/Mediana",
        "fuel": "Diésel",
        "co2_base_g_km": 460.0,
        "consumption_l_100": 19.0,
        "nominal_speed": 7.8,
        "accel": 1.0,
        "weight": 0.07
    },
    "trailer": {
        "sumo_vtype": "vtype_trailer_heavy",
        "name": "Tráiler Interprovincial E40",
        "category": "Transporte Pesado Interprovincial",
        "fuel": "Diésel",
        "co2_base_g_km": 860.0,
        "consumption_l_100": 34.0,
        "nominal_speed": 7.2,
        "accel": 0.7,
        "weight": 0.03
    }
}

FLEET_KEYS = list(FLEET_CONFIG.keys())
FLEET_WEIGHTS = [FLEET_CONFIG[k]["weight"] for k in FLEET_KEYS]

def check_traci_port(host="127.0.0.1", port=8813):
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def try_connect_traci():
    global traci_client
    if check_traci_port("127.0.0.1", 8813):
        try:
            import traci
            traci.init(port=8813)
            traci_client = traci
            logger.info("✓ Conectado exitosamente a TraCI en puerto 8813.")
            return True
        except Exception as e:
            logger.info("TraCI falló al inicializar: %s", e)
    traci_client = None
    return False

# Coordenadas exactas clave de Paute (Milimétricas SUMO / OSM)
MARKET_CENTER_X = -64.8
MARKET_CENTER_Z = -350.1
# Junction 2910139955: the actual E40/Barzallo crossing beside Mercado 26 de Febrero.
BARZALLO_CAM_X = 11.87
BARZALLO_CAM_Z = -439.99
CCTV_REFERENCE = {
    "junction_id": "2910139955", "anchor_3d": [11.87, 0.0, -439.99],
    "edge_id": "605329467#6", "opposite_edge_id": "-605329467#6",
    "routes": {"SUBE": ["605329467#6", "605329467#7"], "BAJA": ["-605329467#6", "-605329467#5"]},
    "lens_offset": [-2.8, 9.2, 1.4], "camera_normal": [0.26269, 0.96488],
    "camera_yaw_deg": 15.23, "camera_look_at": [19.58, 3.0, -399.99],
    "count_line_x": 0.52, "hysteresis_zone": [0.44, 0.60],
    "crossing_thresholds": [0.48, 0.55], "roi_x": [0.08, 0.95], "roi_y": [0.22, 0.92]
}
BARZALLO_CAM_X = CCTV_REFERENCE["anchor_3d"][0]
BARZALLO_CAM_Z = CCTV_REFERENCE["anchor_3d"][2]
CCTV_RESERVED_EDGES = {
    edge_id
    for route in CCTV_REFERENCE["routes"].values()
    for edge_id in route
}
E40_DESVIO_X = BARZALLO_CAM_X
E40_DESVIO_Z = BARZALLO_CAM_Z

class SyntheticTrafficGenerator:
    """
    Generador topológico continuo de tráfico urbano para Paute.
    - Carga la red completa y las conexiones entre aristas para que los vehículos
      crucen las intersecciones con total continuidad y nunca desaparezcan en una esquina.
    - Utiliza rutas multicarretera de paute_test.rou.xml y extiende trayectorias dinámicamente.
    """
    def __init__(self, net_json_path, net_xml_path=NET_XML_FILE, rou_xml_path=ROU_XML_FILE):
        global CCTV_REFERENCE, CCTV_RESERVED_EDGES, BARZALLO_CAM_X, BARZALLO_CAM_Z, E40_DESVIO_X, E40_DESVIO_Z
        self.cctv_reference = CCTV_REFERENCE
        self.vehicles = {}
        self.counter = 0
        self.total_co2_kg = 0.0
        
        self.edges_map = {}
        self.connections = {}
        self.routes = []
        self.market_routes = []
        self.barzallo_routes = []
        self.inter_routes = []

        # 1. Cargar aristas desde paute_network_3d.json
        if os.path.isfile(net_json_path):
            try:
                with open(net_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.cctv_reference = data.get("cctv_reference", CCTV_REFERENCE)
                    CCTV_REFERENCE = self.cctv_reference
                    CCTV_RESERVED_EDGES = {
                        edge_id
                        for route in self.cctv_reference.get("routes", {}).values()
                        for edge_id in route
                    }
                    BARZALLO_CAM_X = self.cctv_reference["anchor_3d"][0]
                    BARZALLO_CAM_Z = self.cctv_reference["anchor_3d"][2]
                    E40_DESVIO_X, E40_DESVIO_Z = BARZALLO_CAM_X, BARZALLO_CAM_Z
                    for edge in data.get("edges", []):
                        if edge.get("lanes") and len(edge["lanes"]) > 0:
                            self.edges_map[edge["id"]] = {
                                "name": edge.get("name", ""),
                                "speed": edge.get("speed", 13.89),
                                "points": edge["lanes"][0]["points"]
                            }
            except Exception as e:
                logger.error("Error leyendo %s: %s", net_json_path, e)

        # 2. Cargar conexiones de intersecciones desde paute.net.xml
        if os.path.isfile(net_xml_path):
            try:
                tree = ET.parse(net_xml_path)
                root = tree.getroot()
                for conn in root.findall("connection"):
                    frm = conn.get("from")
                    to = conn.get("to")
                    if frm in self.edges_map and to in self.edges_map:
                        self.connections.setdefault(frm, []).append(to)
            except Exception as e:
                logger.warning("No se pudo parsear conexiones de %s: %s", net_xml_path, e)

        # 3. Cargar rutas multicarretera reales desde paute_test.rou.xml
        if os.path.isfile(rou_xml_path):
            try:
                tree = ET.parse(rou_xml_path)
                root = tree.getroot()
                for v in root.findall("vehicle"):
                    r = v.find("route")
                    if r is not None and r.get("edges"):
                        eids = r.get("edges").split()
                        if len(eids) >= 2:
                            pts = self._chain_edges_points(eids)
                            if len(pts) >= 4:
                                cd = self._compute_cum_dists(pts)
                                r_obj = {"edges": eids, "points": pts, "cum_dists": cd}
                                # Reserve the CCTV block for detections from the physical camera.
                                if (any(eid in CCTV_RESERVED_EDGES for eid in eids)
                                        or any(math.hypot(p[0] - BARZALLO_CAM_X,
                                                          p[2] - BARZALLO_CAM_Z) < 14.0 for p in pts)):
                                    continue
                                self.routes.append(r_obj)

                                # Clasificar por áreas clave
                                names = [self.edges_map[eid]["name"].lower() for eid in eids if eid in self.edges_map]
                                is_barzallo = any("barzallo" in n or "miguel" in n for n in names)
                                is_inter = any("interoc" in n for n in names)
                                is_market = any(
                                    math.hypot(p[0] - MARKET_CENTER_X, p[2] - MARKET_CENTER_Z) < 220.0
                                    for p in pts[::max(1, len(pts)//5)]
                                )

                                if is_barzallo:
                                    self.barzallo_routes.append(r_obj)
                                if is_inter:
                                    self.inter_routes.append(r_obj)
                                if is_market:
                                    self.market_routes.append(r_obj)
            except Exception as e:
                logger.warning("No se pudieron cargar rutas de %s: %s", rou_xml_path, e)

        # Fallback si no hay rutas de rou.xml: generar cadenas a partir de aristas y conexiones
        if not self.routes and self.edges_map:
            logger.info("Generando rutas continuas por grafo de conexiones...")
            for eid, edata in self.edges_map.items():
                chain_eids = [eid]
                curr = eid
                for _ in range(6):
                    next_opts = self.connections.get(curr, [])
                    next_opts = [edge for edge in next_opts if edge not in CCTV_RESERVED_EDGES]
                    if not next_opts:
                        break
                    curr = random.choice(next_opts)
                    chain_eids.append(curr)
                pts = self._chain_edges_points(chain_eids)
                if (len(pts) >= 4
                        and not any(edge in CCTV_RESERVED_EDGES for edge in chain_eids)
                        and not any(math.hypot(p[0] - BARZALLO_CAM_X,
                                               p[2] - BARZALLO_CAM_Z) < 14.0 for p in pts)):
                    cd = self._compute_cum_dists(pts)
                    r_obj = {"edges": chain_eids, "points": pts, "cum_dists": cd}
                    self.routes.append(r_obj)

        if not self.market_routes:
            self.market_routes = self.routes
        if not self.inter_routes:
            self.inter_routes = self.routes

        # Confinamiento puro de cuadra: la cuadra de la cámara (1445998233) queda reservada exclusivamente
        # para los vehículos detectados por el sistema de visión computacional
        self.barzallo_routes = [r for r in self.barzallo_routes
                                if not any(e in CCTV_RESERVED_EDGES for e in r.get("edges", []))]
        logger.info(
            "✓ Generador de Tráfico Continuo listo: %d rutas multicarretera (%d en J.M. Barzallo, %d en Interoceánica, %d en Mercados).",
            len(self.routes), len(self.barzallo_routes), len(self.inter_routes), len(self.market_routes)
        )

    def inject_cctv_vehicle(self, vtype, direction, speed_kmh=26.0, progress=0.0):
        """
        Inyecta una entidad 3D fidedigna en la cuadra de José Miguel Barzallo
        correspondiente exactamente al vehículo detectado por la cámara USB.
        """
        self.counter += 1
        cfg = FLEET_CONFIG.get(vtype, FLEET_CONFIG["car"])
        speed = max(speed_kmh / 3.6, 3.5)

        # Geometría milimétrica del tramo José Miguel Barzallo entre Junction 2910139955 (E40) y 2910139953 (Bolívar)
        # Vector longitudinal: dx = 16.90, dz = -45.14. Perpendicular: (0.9365, 0.3506)
        # Routes, junction and camera anchor come from one master reference in the exported network.
        edges = list(self.cctv_reference["routes"][direction])
        pts = self._chain_edges_points(edges)
        if len(pts) < 2:
            logger.warning("No se inyecta veh??culo CCTV: falta geometr??a SUMO de la E40")
            return None
        # Anclar la trayectoria al tramo de la E40 que pasa frente a la c?mara.
        anchor_x, anchor_z = self.cctv_reference["anchor_3d"][0], self.cctv_reference["anchor_3d"][2]
        nearest = min(range(len(pts)), key=lambda i: math.hypot(
            pts[i][0] - anchor_x, pts[i][2] - anchor_z))
        pts = pts[nearest:]
        if len(pts) < 2:
            return None

        pts = [[p[0], 0.5, p[2]] for p in pts]
        if len(pts) < 2:
            return None

        cd = self._compute_cum_dists(pts)
        first_segment_length = cd[1]
        traveled = first_segment_length * min(max(float(progress), 0.0), 1.0)
        segment_fraction = traveled / max(first_segment_length, 0.001)
        start_x = pts[0][0] + (pts[1][0] - pts[0][0]) * segment_fraction
        start_z = pts[0][2] + (pts[1][2] - pts[0][2]) * segment_fraction
        dx = pts[1][0] - pts[0][0]
        dz = pts[1][2] - pts[0][2]
        heading = (math.degrees(math.atan2(dx, dz)) + 360) % 360

        vid = f"CAM-{direction[:3]}-{self.counter:03d}"
        veh_obj = {
            "id": vid,
            "type": vtype,
            "vtype_id": cfg["sumo_vtype"],
            "name": cfg["name"],
            "fuel": cfg["fuel"],
            "edges": edges,
            "points": pts,
            "cum_dists": cd,
            "traveled": traveled,
            "base_speed": speed,
            "current_speed": speed,
            "co2_accum_g": 0.0,
            "x": start_x,
            "y": 0.5,
            "z": start_z,
            "heading": heading,
            "source": "CCTV_USB_YOLO",
            "cctv_tracked": True,
            "direction": direction,
            "edge_id": self.cctv_reference["edge_id"],
            "junction_id": self.cctv_reference["junction_id"]
        }
        self.vehicles[vid] = veh_obj
        logger.info("CCTV spawn %s class=%s direction=%s edge=%s junction=%s X=%.2f Z=%.2f speed=%.1f km/h",
                    vid, cfg["name"], direction, self.cctv_reference["edge_id"],
                    self.cctv_reference["junction_id"], start_x, start_z, speed_kmh)
        return veh_obj

    def _compute_cum_dists(self, pts):
        cd = [0.0]
        for i in range(len(pts) - 1):
            d = math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][2] - pts[i][2])
            cd.append(cd[-1] + max(d, 0.001))
        return cd

    def _chain_edges_points(self, edge_ids):
        """Une secuencialmente los puntos de múltiples aristas a través de las intersecciones."""
        pts = []
        for eid in edge_ids:
            if eid not in self.edges_map:
                continue
            e_pts = self.edges_map[eid]["points"]
            if not e_pts:
                continue
            if not pts:
                pts.extend(e_pts)
            else:
                last_p = pts[-1]
                first_p = e_pts[0]
                d = math.hypot(first_p[0] - last_p[0], first_p[2] - last_p[2])
                if d > 0.05:
                    pts.extend(e_pts)
                else:
                    pts.extend(e_pts[1:])
        return pts

    def update(self, dt=0.05):
        # Inyectar vehículos de forma continua hasta 75 activos
        if len(self.vehicles) < 40 and random.random() < 0.10 and self.routes:
            self.counter += 1
            vtype = random.choices(FLEET_KEYS, weights=FLEET_WEIGHTS)[0]
            cfg = FLEET_CONFIG[vtype]
            
            # Prioridad de distribución: Barzallo/Cámara (30%), Mercados (35%), Interoceánica (25%), General (10%)
            dice = random.random()
            if dice < 0.30 and self.barzallo_routes:
                route_data = random.choice(self.barzallo_routes)
            elif dice < 0.65 and self.market_routes:
                route_data = random.choice(self.market_routes)
            elif dice < 0.90 and self.inter_routes:
                route_data = random.choice(self.inter_routes)
            else:
                route_data = random.choice(self.routes)

            points = list(route_data["points"])
            edges = list(route_data["edges"])
            cum_dists = list(route_data["cum_dists"])
            route_speed_limit = min(
                (self.edges_map.get(edge_id, {}).get("speed", float("inf")) for edge_id in edges),
                default=float("inf")
            )
            varied_speed = cfg["nominal_speed"] * random.uniform(0.70, 1.30)
            base_speed = min(varied_speed, route_speed_limit * random.uniform(0.82, 0.98))
            
            # Orientación inicial calculada del primer segmento
            init_dx = points[1][0] - points[0][0] if len(points) > 1 else 1.0
            init_dz = points[1][2] - points[0][2] if len(points) > 1 else 0.0
            init_heading = (math.degrees(math.atan2(init_dx, init_dz)) + 360) % 360

            self.vehicles[f"veh_{self.counter:05d}"] = {
                "id": f"PAUTE-{self.counter:04d}",
                "type": vtype,
                "name": cfg["name"],
                "fuel": cfg["fuel"],
                "edges": edges,
                "points": points,
                "cum_dists": cum_dists,
                "traveled": 0.0,
                "base_speed": base_speed,
                "current_speed": base_speed,
                "co2_accum_g": 0.0,
                "x": points[0][0],
                "y": 0.5,
                "z": points[0][2],
                "heading": init_heading
            }

        finished = []
        step_co2_total_g = 0.0

        for vid, v in list(self.vehicles.items()):
            # Fricción real en el mercado exacto (-64.8, -350.1)
            dist_to_market = math.hypot(v["x"] - MARKET_CENTER_X, v["z"] - MARKET_CENTER_Z)
            if dist_to_market < 150.0:
                friction = 0.55 + 0.35 * (dist_to_market / 150.0)
            else:
                friction = 1.0

            speed = v["base_speed"] * friction
            v["current_speed"] = speed
            
            cfg = FLEET_CONFIG[v["type"]]
            speed_kmh = speed * 3.6
            co2_factor = 1.3 if speed_kmh < 15 else 1.0
            co2_gps = (cfg["co2_base_g_km"] / 1000.0) * speed * co2_factor
            
            v["co2_accum_g"] += co2_gps * dt
            v["co2_instant_gps"] = round(co2_gps, 2)
            step_co2_total_g += co2_gps * dt

            v["traveled"] += speed * dt
            total_len = v["cum_dists"][-1]

            # Si el vehículo llega al final de la ruta programada
            if v["traveled"] >= total_len:
                # Extender suavemente la ruta a través de la intersección
                last_edge = v["edges"][-1] if v["edges"] else None
                if last_edge in self.connections and len(v["points"]) < 250:
                    next_opts = [edge for edge in self.connections[last_edge]
                                 if edge not in CCTV_RESERVED_EDGES]
                    if not next_opts:
                        finished.append(vid)
                        continue
                    next_edge = random.choice(next_opts)
                    if next_edge in self.edges_map:
                        next_pts = self.edges_map[next_edge]["points"]
                        if next_pts:
                            v["edges"].append(next_edge)
                            for pt in next_pts:
                                d = math.hypot(pt[0] - v["points"][-1][0], pt[2] - v["points"][-1][2])
                                if d > 0.05:
                                    v["points"].append(pt)
                                    v["cum_dists"].append(v["cum_dists"][-1] + d)
                            total_len = v["cum_dists"][-1]
                else:
                    finished.append(vid)
                    continue

            # Interpolación continua y suave (sin saltos ni teletransportaciones)
            cd = v["cum_dists"]
            dist = v["traveled"]
            seg_idx = 0
            while seg_idx < len(cd) - 2 and dist >= cd[seg_idx + 1]:
                seg_idx += 1

            d0 = cd[seg_idx]
            d1 = cd[seg_idx + 1]
            seg_len = max(d1 - d0, 0.001)
            frac = (dist - d0) / seg_len
            p0 = v["points"][seg_idx]
            p1 = v["points"][seg_idx + 1]

            dx = p1[0] - p0[0]
            dz = p1[2] - p0[2]

            v["x"] = p0[0] + dx * frac
            v["z"] = p0[2] + dz * frac
            v["heading"] = (math.degrees(math.atan2(dx, dz)) + 360) % 360

            # Mantener despejada la intersección CCTV: solo los vehículos
            # generados por un cruce real de la cámara pueden ocupar este radio.
            if (not v.get("cctv_tracked") and
                    math.hypot(v["x"] - BARZALLO_CAM_X, v["z"] - BARZALLO_CAM_Z) < 14.0):
                finished.append(vid)

        for vid in finished:
            del self.vehicles[vid]

        self.total_co2_kg += (step_co2_total_g / 1000.0)

        active_list = []
        total_speed = 0.0
        for vid, v in self.vehicles.items():
            total_speed += v["current_speed"]
            cfg = FLEET_CONFIG[v["type"]]
            active_list.append({
                "id": v["id"],
                "type": v["type"],
                "name": v["name"],
                "fuel": v["fuel"],
                "x": round(v["x"], 2),
                "y": 0.5,
                "z": round(v["z"], 2),
                "speed": round(v["current_speed"], 2),
                "speed_kmh": round(v["current_speed"] * 3.6, 1),
                "heading": round(v["heading"], 1),
                "co2_gps": v.get("co2_instant_gps", 0.5),
                "co2_accum_g": round(v["co2_accum_g"], 1),
                "consumption_l": cfg["consumption_l_100"],
                "source": v.get("source", "SYNTHETIC"),
                "cctv_tracked": v.get("cctv_tracked", False),
                "direction": v.get("direction", "")
            })

        avg_speed = (total_speed / max(len(active_list), 1)) * 3.6
        return active_list, avg_speed, self.total_co2_kg

synthetic_gen = SyntheticTrafficGenerator(NET_JSON_FILE)

class YOLOVehicleDetector:
    """
    Detector vehicular en tiempo real con YOLOv11 y Tracking de Centroides.
    Mapeo a los 6 vTypes de Paute (moto, car, pickup, bus, truck, trailer).
    Detección de sentido (SUBE vs BAJA) mediante dos líneas virtuales de cruce
    sobre la calzada de José Miguel Barzallo.
    Inyección instantánea en el Gemelo Digital 3D (Digital Shadow).
    """
    ROI_X_MIN = 0.08
    ROI_X_MAX = 0.95
    ROI_Y_MIN = 0.22
    ROI_Y_MAX = 0.92
    COUNT_LINE_X = 0.52
    HYSTERESIS_ZONE_LEFT = 0.44
    HYSTERESIS_ZONE_RIGHT = 0.60
    CROSS_LEFT = 0.48
    CROSS_RIGHT = 0.55
    MIN_FRAME_DELTA = 0.035

    def __init__(self, model_path=None):
        if model_path is None:
            model_path = os.path.join(PROJECT_DIR, "yolo11n.pt")
        self.model_path = model_path
        reference = CCTV_REFERENCE
        self.roi_x_min, self.roi_x_max = reference.get("roi_x", [self.ROI_X_MIN, self.ROI_X_MAX])
        self.roi_y_min, self.roi_y_max = reference.get("roi_y", [self.ROI_Y_MIN, self.ROI_Y_MAX])
        self.count_line_x = reference.get("count_line_x", self.COUNT_LINE_X)
        self.hysteresis_zone = reference.get("hysteresis_zone", [self.HYSTERESIS_ZONE_LEFT, self.HYSTERESIS_ZONE_RIGHT])
        self.cross_left, self.cross_right = reference.get("crossing_thresholds", [self.CROSS_LEFT, self.CROSS_RIGHT])
        self.inference_lock = threading.Lock()
        self.bytetrack_available = HAS_BYTETRACK
        if not self.bytetrack_available:
            logger.warning("lap no esta instalado; usando el tracker local de centroides")
        self.model = None
        self.next_track_id = 1
        self.tracks = {}
        self.detected_co2_kg = 0.0
        self.history_window = []
        self.recent_crossings = deque(maxlen=300)
        self.recent_motion_observations = deque(maxlen=4000)
        self.counts = {
            "total": 0, "sube": 0, "baja": 0, "motos": 0,
            "sedanes": 0, "camionetas": 0, "buses": 0,
            "camiones": 0, "trailers": 0
        }
        self.last_crossing = None
        self.init_model()

    def init_model(self):
        if HAS_YOLO and os.path.isfile(self.model_path):
            try:
                self.model = YOLO(self.model_path)
                logger.info("YOLOv11 listo en CPU (%s)", self.model_path)
            except Exception as e:
                logger.warning("No se pudo cargar modelo YOLO: %s", e)
                self.model = None

    def get_flow_per_min(self):
        now = time.time()
        self.history_window = [t for t in self.history_window if now - t <= 60.0]
        return len(self.history_window)

    def get_stats(self):
        return {
            "total": self.counts["total"], "flow_per_min": self.get_flow_per_min(),
            "sube": self.counts["sube"], "baja": self.counts["baja"],
            "motos": self.counts["motos"], "sedanes": self.counts["sedanes"],
            "camionetas": self.counts["camionetas"], "buses": self.counts["buses"],
            "camiones": self.counts["camiones"], "trailers": self.counts["trailers"],
            "co2_detected_kg": round(self.detected_co2_kg, 4),
            "active_tracks": len(self.tracks), "last_crossing": self.last_crossing,
            "lines": {"count_x": self.count_line_x,
                      "left": self.cross_left, "right": self.cross_right,
                      "zone_left": self.hysteresis_zone[0], "zone_right": self.hysteresis_zone[1]},
            "roi": {"x_min": self.roi_x_min, "x_max": self.roi_x_max,
                    "y_min": self.roi_y_min, "y_max": self.roi_y_max}
        }

    def process_frame_base64(self, b64_str):
        if not self.inference_lock.acquire(blocking=False):
            return {"type": "FRAME_INFERENCE_SKIPPED", "reason": "busy"}
        try:
            return self._process_frame_base64_locked(b64_str)
        finally:
            self.inference_lock.release()

    def _process_frame_base64_locked(self, b64_str):
        if not b64_str:
            return {"detections": [], "counts": self.get_stats(), "events": []}
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64_str)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            return self.process_image(img)
        except Exception as e:
            logger.error("Error decodificando imagen base64: %s", e)
            return {"detections": [], "counts": self.get_stats(), "events": []}

    def process_image(self, img):
        w, h = img.size
        detections = []
        if self.model is not None:
            try:
                options = {
                    "imgsz": 640, "device": "cpu", "verbose": False,
                    "conf": 0.18, "iou": 0.45, "max_det": 15,
                    "augment": False, "classes": [2, 3, 5, 7]
                }
                if self.bytetrack_available:
                    results = self.model.track(
                        img, persist=True,
                        tracker=os.path.join(PROJECT_DIR, "config", "bytetrack.yaml"),
                        **options
                    )
                else:
                    results = self.model.predict(img, **options)
                if results:
                    result = results[0]
                    track_ids = getattr(result.boxes, "id", None) if self.bytetrack_available else None
                    for index, box in enumerate(result.boxes):
                        class_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        x1n, x2n = max(0.0, x1 / w), min(1.0, x2 / w)
                        y1n, y2n = max(0.0, y1 / h), min(1.0, y2 / h)
                        box_w, box_h = x2n - x1n, y2n - y1n
                        if box_w <= 0 or box_h <= 0:
                            continue
                        cx, cy = (x1n + x2n) * 0.5, (y1n + y2n) * 0.5
                        if not (self.roi_x_min <= cx <= self.roi_x_max):
                            continue
                        overlap = max(0.0, min(y2n, self.roi_y_max) - max(y1n, self.roi_y_min)) / box_h
                        if overlap <= 0.25:
                            continue

                        aspect = box_w / max(box_h, 1e-6)
                        vtype = "car"
                        if class_id == 3:
                            vtype = "moto"
                        elif class_id == 5 or (class_id in (2, 7) and box_h > 0.24 and box_w > 0.28):
                            vtype = "bus"
                        elif class_id == 7:
                            vtype = "trailer" if box_w > 0.38 else "truck"
                        elif class_id == 2:
                            vtype = "pickup" if (box_w > 0.24 or aspect > 1.85) else "car"

                        detections.append({
                            "bbox": [round(x1n, 6), round(y1n, 6), round(x2n, 6), round(y2n, 6)],
                            "centroid": [round(cx, 6), round(cy, 6)],
                            "roi_overlap": round(overlap, 4), "conf": round(conf, 3),
                            "vtype": vtype, "class_id": class_id,
                            "tracker_id": int(track_ids[index].item()) if track_ids is not None else None
                        })
            except Exception as e:
                logger.error("Error inferencia YOLO: %s", e)

        events = self._update_tracker(detections, w, h)
        return {
            "type": "FRAME_INFERENCE_RESULT",
            "detections": [d for d in detections if d.get("state") in ("DETECTANDO", "MOVIENDO", "ESTACIONADO", "CONTADO")],
            "events": events, "counts": self.get_stats(),
            "lines": self.get_stats()["lines"], "roi": self.get_stats()["roi"]
        }

    @staticmethod
    def _class_family(class_id):
        return int(class_id) if class_id is not None else -1

    def _was_recently_counted(self, detection, direction, cy, now):
        family = self._class_family(detection.get("class_id"))
        self.recent_crossings = deque(
            [item for item in self.recent_crossings if now - item["time"] <= 0.40], maxlen=300
        )
        return any(item["class_family"] == family and item["direction"] == direction
                   and abs(item["cy"] - cy) <= 0.035 for item in self.recent_crossings)

    def _fast_crossing_direction(self, previous_x, current_x):
        if previous_x > 0.62 and current_x < 0.42:
            return "SUBE"  # derecha a izquierda hacia el mercado
        if previous_x < 0.42 and current_x > 0.62:
            return "BAJA"
        # Los vehículos pueden entrar en cámara ya dentro de la banda central.
        # Al salir de ella hacia un lado, el propio desplazamiento da el sentido.
        if (previous_x >= self.hysteresis_zone[0] and current_x < self.cross_left
                and previous_x - current_x >= self.MIN_FRAME_DELTA):
            return "SUBE"
        if (previous_x <= self.hysteresis_zone[1] and current_x > self.cross_right
                and current_x - previous_x >= self.MIN_FRAME_DELTA):
            return "BAJA"
        return None

    def _emit_fast_crossing(self, detection, direction, track_id, delta_x, elapsed, now, events):
        if not direction or self._was_recently_counted(detection, direction, detection["centroid"][1], now):
            return False
        speed_kmh = min(max(abs(delta_x) * 18.0 / max(elapsed, 0.05) * 3.6, 8.0), 90.0)
        event = self.record_crossing(detection["vtype"], direction, speed_kmh, track_id,
                                     detection["centroid"][0])
        events.append(event)
        self.recent_crossings.append({
            "time": now, "class_family": self._class_family(detection.get("class_id")),
            "direction": direction, "cy": detection["centroid"][1]
        })
        return True

    def _update_tracker(self, detections, frame_w, frame_h):
        now = time.time()
        events, assigned = [], set()
        self.recent_motion_observations = deque(
            [o for o in self.recent_motion_observations if now - o["time"] <= 2.5], maxlen=4000
        )

        for detection in detections:
            cx, cy = detection["centroid"]
            overlap = detection.get("roi_overlap", 0.0)
            if not (self.roi_x_min <= cx <= self.roi_x_max) or overlap <= 0.25:
                continue
            track_id = detection.get("tracker_id")
            best_id = None
            min_dist = 0.45
            if track_id is not None:
                for tid, track in self.tracks.items():
                    if tid not in assigned and track.get("bytetrack_id") == track_id:
                        best_id = tid
                        break
            for tid, track in self.tracks.items():
                if best_id is not None:
                    break
                if tid in assigned:
                    continue
                elapsed = min(max(now - track.get("last_seen", now), 0.0), 1.25)
                px = track["cx"] + track.get("vx", 0.0) * elapsed
                py = track["cy"] + track.get("vy", 0.0) * elapsed
                horizontal_dist = abs(cx - px)
                same_road_band = abs(cy - py) <= 0.12
                classes_match = (detection.get("class_id") == track.get("class_id")
                                 or detection["vtype"] == track["vtype"])
                if classes_match and same_road_band and horizontal_dist < min_dist:
                    min_dist, best_id = horizontal_dist, tid

            # ByteTrack puede dar otro ID tras un salto grande: recupera cruces
            # completos por clase/franja vertical aunque el delta supere el radio normal.
            fast_prior = next((o for o in reversed(self.recent_motion_observations)
                               if o["class_family"] == self._class_family(detection.get("class_id"))
                               and now - o["time"] <= 1.0 and abs(o["cy"] - cy) <= 0.12
                               and not o.get("counted")
                               and self._fast_crossing_direction(o["cx"], cx)), None)

            if best_id is None:
                tid = self.next_track_id
                self.next_track_id += 1
                current_side = ("right" if cx >= self.hysteresis_zone[1]
                                else ("left" if cx <= self.hysteresis_zone[0] else None))
                family = self._class_family(detection.get("class_id"))
                prior = fast_prior or next((o for o in reversed(self.recent_motion_observations)
                              if o["track_id"] != tid and o["class_family"] == family
                              and now - o["time"] <= 2.5 and abs(o["cy"] - cy) <= 0.09
                              and o["motion_frames"] >= 1 and o["side"] is not None
                              and current_side is not None and o["side"] != current_side
                              and not o["counted"]), None)
                direction = None
                initial_cx, motion_frames, motion_anchor = cx, 0, cx
                old_side = current_side
                if prior:
                    direction = self._fast_crossing_direction(prior["cx"], cx)
                    if direction is None:
                        direction = "SUBE" if prior["side"] == "right" else "BAJA"
                    initial_cx, motion_frames, motion_anchor = prior["cx"], 1, cx
                    old_side = prior["side"]
                fast_cross = bool(fast_prior)
                if fast_cross:
                    motion_frames = 2
                track = {
                    "cx": cx, "cy": cy, "initial_cx": initial_cx, "motion_anchor_x": motion_anchor,
                    "motion_frames": motion_frames, "max_horizontal_shift": abs(cx-initial_cx),
                    "vx": 0.0, "vy": 0.0, "last_seen": now, "first_seen": now,
                    "bbox": detection["bbox"], "vtype": detection["vtype"],
                    "class_id": detection.get("class_id"), "bytetrack_id": track_id,
                    "confidence": detection.get("conf", 0.0),
                    "gate_side": old_side, "crossing_direction": direction,
                    "counted": False, "disappeared": 0
                }
                self.tracks[tid] = track
                assigned.add(tid)
                if fast_cross:
                    prior["counted"] = True
                    track["counted"] = True
                    self._emit_fast_crossing(detection, direction, tid,
                                             cx - prior["cx"], now - prior["time"], now, events)
                detection["state"] = "CONTADO" if track["counted"] else "DETECTANDO"
                self.recent_motion_observations.append({
                    "time": now, "track_id": tid, "class_family": family,
                    "cx": cx, "cy": cy, "side": old_side,
                    "motion_frames": motion_frames, "counted": track["counted"]
                })
                continue

            track = self.tracks[best_id]
            prev_cx, prev_cy = track["cx"], track["cy"]
            dt = max(now - track["last_seen"], 0.05)
            track["vx"] = track.get("vx", 0.0) * 0.30 + ((cx - prev_cx) / dt) * 0.70
            track["vy"] = track.get("vy", 0.0) * 0.30 + ((cy - prev_cy) / dt) * 0.70
            if abs(cx - track.get("motion_anchor_x", prev_cx)) >= self.MIN_FRAME_DELTA:
                track["motion_frames"] += 1
                track["motion_anchor_x"] = cx
            track["max_horizontal_shift"] = max(track.get("max_horizontal_shift", 0.0), abs(cx-track["initial_cx"]))
            side = ("right" if cx >= self.hysteresis_zone[1]
                    else ("left" if cx <= self.hysteresis_zone[0] else None))
            fast_direction = self._fast_crossing_direction(prev_cx, cx)
            if fast_direction and not track["counted"]:
                self._emit_fast_crossing(detection, fast_direction, best_id,
                                         cx - prev_cx, dt, now, events)
                track["crossing_direction"] = fast_direction
                track["counted"] = True
            if track["crossing_direction"] is None:
                if track["gate_side"] == "right" and cx < self.cross_left:
                    track["crossing_direction"] = "SUBE"
                elif track["gate_side"] == "left" and cx > self.cross_right:
                    track["crossing_direction"] = "BAJA"
            if side is not None and track["gate_side"] is None:
                track["gate_side"] = side
            track.update({
                "cx": cx, "cy": cy, "last_seen": now, "bbox": detection["bbox"],
                "vtype": detection["vtype"], "class_id": detection.get("class_id"),
                "bytetrack_id": track_id, "confidence": detection.get("conf", 0.0),
                "disappeared": 0
            })
            assigned.add(best_id)

            if not track["counted"] and track["crossing_direction"] and track["motion_frames"] >= 2 and track["max_horizontal_shift"] > self.MIN_FRAME_DELTA:
                direction = track["crossing_direction"]
                if not self._was_recently_counted(detection, direction, cy, now):
                    speed_kmh = min(max(abs(track["vx"]) * 18.0 * 3.6, 8.0), 90.0)
                    event = self.record_crossing(detection["vtype"], direction, speed_kmh, best_id, cx)
                    events.append(event)
                    self.recent_crossings.append({
                        "time": now, "class_family": self._class_family(detection.get("class_id")),
                        "direction": direction, "cy": cy
                    })
                track["counted"] = True

            parked = now - track["first_seen"] > 0.9 and track["max_horizontal_shift"] < 0.06 and track["motion_frames"] == 0
            detection["state"] = "CONTADO" if track["counted"] else ("ESTACIONADO" if parked else ("MOVIENDO" if track["motion_frames"] else "DETECTANDO"))
            family = self._class_family(detection.get("class_id"))
            self.recent_motion_observations.append({
                "time": now, "track_id": best_id, "class_family": family,
                "cx": cx, "cy": cy, "side": side or track["gate_side"],
                "motion_frames": track["motion_frames"], "counted": track["counted"]
            })

        for tid, track in list(self.tracks.items()):
            if tid not in assigned:
                track["disappeared"] += 1
                elapsed = min(max(now - track.get("last_seen", now), 0.0), 1.0)
                predicted_x = track["cx"] + track.get("vx", 0.0) * elapsed
                exits_roi = ((track.get("vx", 0.0) < 0 and predicted_x < self.roi_x_min)
                             or (track.get("vx", 0.0) > 0 and predicted_x > self.roi_x_max))
                if (track["disappeared"] == 1 and not track.get("counted")
                        and track.get("confidence", 0.0) >= 0.35 and exits_roi
                        and 0.25 <= track.get("initial_cx", track["cx"]) <= 0.75
                        and track.get("motion_frames", 0) >= 1):
                    direction = "SUBE" if track["vx"] < 0 else "BAJA"
                    detection = {"class_id": track.get("class_id"), "vtype": track["vtype"],
                                 "centroid": [track["cx"], track["cy"]]}
                    if not self._was_recently_counted(detection, direction, track["cy"], now):
                        speed_kmh = min(max(abs(track["vx"]) * 18.0 * 3.6, 8.0), 90.0)
                        event = self.record_crossing(track["vtype"], direction, speed_kmh, tid, track["cx"])
                        events.append(event)
                        self.recent_crossings.append({
                            "time": now, "class_family": self._class_family(track.get("class_id")),
                            "direction": direction, "cy": track["cy"]
                        })
                    track["counted"] = True
                if track["disappeared"] > 45:
                    del self.tracks[tid]
        return events

    def record_crossing(self, vtype, direction, speed_kmh=26.0, track_id=None, progress=0.0):
        now = time.time()
        self.counts["total"] += 1
        if direction == "SUBE":
            self.counts["sube"] += 1
        else:
            self.counts["baja"] += 1

        tk_map = {
            "moto": "motos", "car": "sedanes", "pickup": "camionetas",
            "bus": "buses", "truck": "camiones", "trailer": "trailers"
        }
        tk = tk_map.get(vtype, "sedanes")
        self.counts[tk] = self.counts.get(tk, 0) + 1
        self.history_window.append(now)

        cfg = FLEET_CONFIG.get(vtype, FLEET_CONFIG["car"])
        segment_km = 0.062
        co2_g = cfg["co2_base_g_km"] * segment_km * (1.25 if speed_kmh < 20 else 1.0)
        self.detected_co2_kg += (co2_g / 1000.0)

        ev = {
            "track_id": track_id or random.randint(100, 999),
            "vtype": vtype,
            "vtype_id": cfg["sumo_vtype"],
            "type_name": cfg["name"],
            "direction": direction,
            "speed_kmh": round(speed_kmh, 1),
            "co2_g": round(co2_g, 2),
            "timestamp": now
        }
        vehicle = synthetic_gen.inject_cctv_vehicle(vtype, direction, speed_kmh, progress)
        if vehicle:
            ev.update({
                "spawn_x": round(vehicle["x"], 2), "spawn_z": round(vehicle["z"], 2),
                "edge_id": vehicle["edge_id"], "junction_id": vehicle["junction_id"]
            })
            logger.info("CCTV crossing class=%s dir=%s track=%s edge=%s junction=%s X=%.2f Z=%.2f",
                        cfg["name"], direction, ev["track_id"], vehicle["edge_id"],
                        vehicle["junction_id"], vehicle["x"], vehicle["z"])
        self.last_crossing = ev
        return ev

cctv_detector = YOLOVehicleDetector()

async def simulation_loop():
    step = 0
    cx = 748843.34
    cy = -307645.89

    while True:
        try:
            step += 1
            vehicles_data = []
            avg_speed_kmh = 0.0
            total_co2_kg = 0.0
            
            if traci_client is not None:
                try:
                    veh_ids = traci_client.vehicle.getIDList()
                    total_speed = 0.0
                    for vid in veh_ids:
                        px, py = traci_client.vehicle.getPosition(vid)
                        angle = traci_client.vehicle.getAngle(vid)
                        speed = traci_client.vehicle.getSpeed(vid)
                        vclass = traci_client.vehicle.getTypeID(vid)
                        
                        vtype = "car"
                        if "moto" in vclass: vtype = "moto"
                        elif "pickup" in vclass: vtype = "pickup"
                        elif "bus" in vclass: vtype = "bus"
                        elif "trailer" in vclass: vtype = "trailer"
                        elif "truck" in vclass: vtype = "truck"
                        
                        cfg = FLEET_CONFIG.get(vtype, FLEET_CONFIG["car"])
                        co2_gps = (cfg["co2_base_g_km"] / 1000.0) * speed
                        map_x = round(px - cx, 2)
                        map_z = round(-(py - cy), 2)
                        # Keep the CCTV block/intersection clear; only the vision
                        # pipeline may place a vehicle inside this reserved radius.
                        if math.hypot(map_x - BARZALLO_CAM_X, map_z - BARZALLO_CAM_Z) < 14.0:
                            continue
                        
                        total_speed += speed
                        vehicles_data.append({
                            "id": vid,
                            "type": vtype,
                            "name": cfg["name"],
                            "fuel": cfg["fuel"],
                            "x": map_x,
                            "y": 0.5,
                            "z": map_z,
                            "speed": round(speed, 2),
                            "speed_kmh": round(speed * 3.6, 1),
                            "heading": round(angle, 1),
                            "co2_gps": round(co2_gps, 2),
                            "co2_accum_g": round(co2_gps * step * 0.05, 1),
                            "consumption_l": cfg["consumption_l_100"]
                        })
                    avg_speed_kmh = (total_speed / max(len(veh_ids), 1)) * 3.6
                    total_co2_kg = sum(v["co2_gps"] for v in vehicles_data) * (step * 0.05) / 1000.0
                except Exception:
                    vehicles_data, avg_speed_kmh, total_co2_kg = synthetic_gen.update(0.05)
            else:
                vehicles_data, avg_speed_kmh, total_co2_kg = synthetic_gen.update(0.05)

            # Densidad en el Mercado 26F exacto (-64.8, -350.1)
            market_count = sum(1 for v in vehicles_data if math.hypot(v["x"] - MARKET_CENTER_X, v["z"] - MARKET_CENTER_Z) < 160.0)
            e40_count = sum(1 for v in vehicles_data if math.hypot(v["x"] - E40_DESVIO_X, v["z"] - E40_DESVIO_Z) < 160.0)
            barzallo_cam_count = sum(1 for v in vehicles_data if math.hypot(v["x"] - BARZALLO_CAM_X, v["z"] - BARZALLO_CAM_Z) < 130.0)
            
            market_state = "Fluido" if market_count < 8 else ("Congestión Moderada" if market_count < 18 else "Fricción Alta (Mercado)")
            e40_state = "Fluido" if e40_count < 8 else ("Moderado" if e40_count < 16 else "Lento (Desvío E40)")

            payload = {
                "type": "TELEMETRY_UPDATE",
                "step": step,
                "time_s": round(step * 0.05, 1),
                "vehicles": vehicles_data,
                "metrics": {
                    "active_vehicles": len(vehicles_data),
                    "avg_speed_kmh": round(avg_speed_kmh, 1),
                    "total_co2_kg": round(total_co2_kg, 2),
                    "co2_rate_kgh": round((sum(v.get("co2_gps", 0.5) for v in vehicles_data) * 3600.0) / 1000.0, 1),
                    "market_density": market_state,
                    "market_veh_count": market_count,
                    "e40_density": e40_state,
                    "barzallo_cam_count": barzallo_cam_count,
                    "teleport_count": 0,
                    "source": "TraCI SUMO 1.18" if traci_client else "Sombra Digital Confinada (Paute)"
                },
                "vision_stats": cctv_detector.get_stats()
            }

            if connected_websockets:
                message = json.dumps(payload)
                for ws in list(connected_websockets):
                    try:
                        if hasattr(ws, "send_str"):
                            await ws.send_str(message)
                        elif hasattr(ws, "send_text"):
                            await ws.send_text(message)
                    except Exception:
                        connected_websockets.discard(ws)

        except Exception as e:
            logger.error("Error en loop: %s", e)

        await asyncio.sleep(0.05)


# ─── SERVIDORES (AIOHTTP / FASTAPI DUAL BACKEND) ──────────────────────

try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


if HAS_AIOHTTP:
    async def aiohttp_websocket_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        connected_websockets.add(ws)
        logger.info("Cliente WebSocket conectado desde %s (Total: %d)", request.remote, len(connected_websockets))

        await ws.send_json({
            "type": "INIT_ACK",
            "message": "Sombra Digital Paute 3D Conectada (Coordenadas Exactas)",
            "city": "Paute, Azuay, Ecuador"
        })

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        mtype = data.get("type", "")
                        if mtype == "FRAME_INFERENCE":
                            loop = asyncio.get_running_loop()
                            res = await loop.run_in_executor(
                                None, cctv_detector.process_frame_base64, data.get("image", "")
                            )
                            await ws.send_str(json.dumps(res))
                        elif mtype == "INJECT_TEST_VEHICLE":
                            vtype = data.get("vtype", "car")
                            direction = data.get("direction", "SUBE")
                            speed = float(data.get("speed_kmh", 25.0))
                            ev = cctv_detector.record_crossing(vtype, direction, speed)
                            await ws.send_str(json.dumps({
                                "type": "TEST_VEHICLE_INJECTED",
                                "event": ev,
                                "counts": cctv_detector.get_stats()
                            }))
                    except Exception:
                        pass
        finally:
            connected_websockets.discard(ws)

        return ws

    async def aiohttp_start_background_tasks(app):
        app['sim_task'] = asyncio.create_task(simulation_loop())

    async def aiohttp_cleanup_background_tasks(app):
        app['sim_task'].cancel()
        try:
            await app['sim_task']
        except asyncio.CancelledError:
            pass

    def create_aiohttp_app():
        app = web.Application()
        app.router.add_get("/ws/telemetry", aiohttp_websocket_handler)
        async def health(_req):
            return web.json_response({"status": "ok", "yolo_loaded": cctv_detector.model is not None,
                                      "vision": cctv_detector.get_stats()})
        async def vision_stats(_req):
            return web.json_response(cctv_detector.get_stats())
        app.router.add_get("/health", health)
        app.router.add_get("/api/vision/stats", vision_stats)

        async def rtsp_stream(_req):
            if not rtsp_camera.start():
                return web.json_response({"error": "Ingresa las credenciales locales de la cámara y verifica OpenCV."}, status=503)
            response = web.StreamResponse(headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=frame",
                "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"
            })
            await response.prepare(_req)
            try:
                while True:
                    frame = rtsp_camera.jpeg()
                    if frame:
                        await response.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                    await asyncio.sleep(0.05)
            except (ConnectionResetError, asyncio.CancelledError):
                pass
            return response
        app.router.add_get("/api/camera/stream", rtsp_stream)
        async def configure_camera(req):
            try:
                data = await req.json()
                ip = str(data.get("ip", "192.168.0.11"))
                username = str(data.get("username", "admin"))
                password = str(data.get("password", ""))
                if not ipaddress.ip_address(ip).is_private or not username or not password:
                    return web.json_response({"error": "Ingresa IP privada, usuario y código de verificación."}, status=400)
                if not rtsp_camera.configure(ip, username, password):
                    return web.json_response({"error": "OpenCV no está disponible en el servidor."}, status=503)
                return web.json_response({"status": "connecting"})
            except ValueError:
                return web.json_response({"error": "La dirección IP no es válida."}, status=400)
        app.router.add_post("/api/camera/config", configure_camera)
        
        async def index(req):
            return web.FileResponse(os.path.join(WEB_DIR, "index.html"))
        app.router.add_get("/", index)
        
        app.router.add_static("/", WEB_DIR, show_index=True)
        app.on_startup.append(aiohttp_start_background_tasks)
        app.on_cleanup.append(aiohttp_cleanup_background_tasks)
        return app


if HAS_FASTAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(simulation_loop())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    fastapi_app = FastAPI(title="Sombra Digital Paute", lifespan=lifespan)

    @fastapi_app.websocket("/ws/telemetry")
    async def fastapi_websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        connected_websockets.add(websocket)
        logger.info("Cliente WebSocket conectado (Total: %d)", len(connected_websockets))
        await websocket.send_json({
            "type": "INIT_ACK",
            "message": "Sombra Digital Paute 3D Conectada (Coordenadas Exactas)",
            "city": "Paute, Azuay, Ecuador"
        })
        try:
            while True:
                data_text = await websocket.receive_text()
                try:
                    data = json.loads(data_text)
                    mtype = data.get("type", "")
                    if mtype == "FRAME_INFERENCE":
                        loop = asyncio.get_running_loop()
                        res = await loop.run_in_executor(
                            None, cctv_detector.process_frame_base64, data.get("image", "")
                        )
                        await websocket.send_text(json.dumps(res))
                    elif mtype == "INJECT_TEST_VEHICLE":
                        vtype = data.get("vtype", "car")
                        direction = data.get("direction", "SUBE")
                        speed = float(data.get("speed_kmh", 25.0))
                        ev = cctv_detector.record_crossing(vtype, direction, speed)
                        await websocket.send_text(json.dumps({
                            "type": "TEST_VEHICLE_INJECTED",
                            "event": ev,
                            "counts": cctv_detector.get_stats()
                        }))
                except Exception as ex:
                    logger.debug("Error procesando ws msg: %s", ex)
        except WebSocketDisconnect:
            pass
        finally:
            connected_websockets.discard(websocket)

    @fastapi_app.post("/api/vision/detect")
    async def api_vision_detect(data: dict):
        img_b64 = data.get("image", "")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, cctv_detector.process_frame_base64, img_b64)

    @fastapi_app.post("/api/vision/inject")
    async def api_vision_inject(data: dict):
        vtype = data.get("vtype", "car")
        direction = data.get("direction", "SUBE")
        speed = float(data.get("speed_kmh", 25.0))
        ev = cctv_detector.record_crossing(vtype, direction, speed)
        return {"status": "ok", "event": ev, "counts": cctv_detector.get_stats()}

    @fastapi_app.get("/api/vision/stats")
    async def api_vision_stats():
        return cctv_detector.get_stats()

    @fastapi_app.get("/api/camera/stream")
    async def api_camera_stream():
        from fastapi.responses import StreamingResponse, JSONResponse
        if not rtsp_camera.start():
            return JSONResponse({"error": "Ingresa las credenciales locales de la cámara y verifica OpenCV."}, status_code=503)
        async def frames():
            while True:
                frame = rtsp_camera.jpeg()
                if frame:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
                await asyncio.sleep(0.05)
        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @fastapi_app.post("/api/camera/config")
    async def api_camera_config(data: dict):
        from fastapi.responses import JSONResponse
        try:
            ip = str(data.get("ip", "192.168.0.11"))
            username = str(data.get("username", "admin"))
            password = str(data.get("password", ""))
            if not ipaddress.ip_address(ip).is_private or not username or not password:
                return JSONResponse({"error": "Ingresa IP privada, usuario y código de verificación."}, status_code=400)
            if not rtsp_camera.configure(ip, username, password):
                return JSONResponse({"error": "OpenCV no está disponible en el servidor."}, status_code=503)
            return {"status": "connecting"}
        except ValueError:
            return JSONResponse({"error": "La dirección IP no es válida."}, status_code=400)

    @fastapi_app.get("/health")
    async def health():
        return {"status": "ok", "yolo_loaded": cctv_detector.model is not None,
                "vision": cctv_detector.get_stats()}

    @fastapi_app.get("/")
    async def fastapi_index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))

    fastapi_app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="static")


def run_server(port=None):
    if port is None:
        port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8085))
    try_connect_traci()
    if HAS_AIOHTTP:
        app = create_aiohttp_app()
        logger.info("Iniciando servidor (Aiohttp) en http://localhost:%d ...", port)
        web.run_app(app, host="0.0.0.0", port=port)
    elif HAS_FASTAPI:
        logger.info("Iniciando servidor (FastAPI/Uvicorn) en http://localhost:%d ...", port)
        uvicorn.run(fastapi_app, host="0.0.0.0", port=port)
    else:
        logger.error("No se encontró 'aiohttp' ni 'fastapi'/'uvicorn'. Instala uno de ellos con pip.")

if __name__ == "__main__":
    run_server()
