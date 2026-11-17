#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║  orquestador.py — Motor de Sombra Digital para Paute, Azuay        ║
║  ──────────────────────────────────────────────────────────────────  ║
║  Simulación vehicular orquestada con TraCI (SUMO).                 ║
║                                                                    ║
║  Fase 2: Inyección programática + Confinamiento topológico         ║
║  Fase 3: Placeholders para Algoritmo Húngaro, V2X (ETSI), visor   ║
╚══════════════════════════════════════════════════════════════════════╝

Uso:
    python3 orquestador.py [--nogui] [--steps N] [--port P]

Dependencias:
    - SUMO (>= 1.18) con soporte TraCI
    - Python >= 3.8
    - (Futuro) scipy, numpy para Algoritmo Húngaro
"""

from __future__ import annotations

import os
import sys
import time
import random
import logging
import argparse
import math
from dataclasses import dataclass, field
from typing import (
    Dict, List, Optional, Tuple, Any, Callable, Set
)
from enum import Enum, auto
from abc import ABC, abstractmethod

# ═══════════════════════════════════════════════════════════════════════
# Validación de SUMO_HOME y carga de TraCI
# ═══════════════════════════════════════════════════════════════════════

def _bootstrap_sumo() -> None:
    """Configura el path de SUMO y valida la instalación."""
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home is None:
        # Intentar rutas por defecto en Ubuntu/WSL
        default_paths = [
            "/usr/share/sumo",
            "/usr/local/share/sumo",
            "/opt/sumo",
        ]
        for path in default_paths:
            if os.path.isdir(path):
                os.environ["SUMO_HOME"] = path
                sumo_home = path
                break

    if sumo_home is None:
        raise EnvironmentError(
            "SUMO_HOME no está definido. Configure con:\n"
            "  export SUMO_HOME=/usr/share/sumo"
        )

    tools_dir = os.path.join(sumo_home, "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)

_bootstrap_sumo()

import traci  # noqa: E402
import traci.constants as tc  # noqa: E402
from sumolib import checkBinary  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════
# Configuración de Logging
# ═══════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SombraDigital")


# ═══════════════════════════════════════════════════════════════════════
# Constantes y Enums
# ═══════════════════════════════════════════════════════════════════════

class VehicleClass(Enum):
    """Clases vehiculares del modelo de Paute."""
    CAR = "vtype_car"
    BUS = "vtype_bus"
    TRUCK = "vtype_truck"


# Distribución de tráfico: (clase, probabilidad acumulada)
TRAFFIC_DISTRIBUTION: List[Tuple[VehicleClass, float]] = [
    (VehicleClass.CAR, 0.70),     # 70% automóviles
    (VehicleClass.BUS, 0.88),     # 18% autobuses
    (VehicleClass.TRUCK, 1.00),   # 12% transporte pesado
]

# Parámetros de inyección
DEFAULT_INJECTION_RATE = 0.15      # Probabilidad de inyección por step
MAX_VEHICLES_CONCURRENT = 120      # Máximo de vehículos simultáneos
TRACI_PORT = 8813                  # Puerto TraCI
SIMULATION_STEPS = 36000           # 36000 steps × 0.1s = 1 hora

# Nodos de fricción críticos (coordenadas UTM aproximadas tras reproyección)
# Estos se actualizarán automáticamente al leer la red
FRICTION_NODES: Dict[str, Tuple[float, float]] = {
    "desvio_interoceanica": (0.0, 0.0),   # E40 ∩ J.M. Barzallo
    "zona_mercado": (0.0, 0.0),           # J.M. Barzallo ∩ Daniel Palacios
}


# ═══════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class VehicleState:
    """Estado interno de un vehículo en la sombra digital."""
    veh_id: str
    vtype: VehicleClass
    route_id: str
    depart_step: int
    current_edge: str = ""
    current_lane: int = 0
    position_xy: Tuple[float, float] = (0.0, 0.0)
    speed: float = 0.0
    heading: float = 0.0
    is_telematic: bool = False  # True si viene de fuente V2X
    telematic_id: Optional[str] = None  # ID externo (GPS/V2X)


@dataclass
class SimulationMetrics:
    """Métricas agregadas de la simulación por step."""
    step: int = 0
    time_s: float = 0.0
    vehicles_active: int = 0
    vehicles_injected_total: int = 0
    vehicles_arrived_total: int = 0
    avg_speed_ms: float = 0.0
    total_waiting_time_s: float = 0.0
    vehicles_at_friction_1: int = 0  # desvío interoceánica
    vehicles_at_friction_2: int = 0  # zona mercado


@dataclass
class TelematicMessage:
    """
    Mensaje telemático V2X (placeholder para ETSI ITS-G5/C-V2X).
    Estructura basada en ETSI EN 302 637-2 (CAM) y EN 302 637-3 (DENM).
    """
    station_id: str             # ITS Station ID
    message_type: str           # "CAM" | "DENM" | "SPATEM" | "MAPEM"
    timestamp_ms: int           # Tiempo en ms (TAI)
    latitude: float             # WGS84 × 10^7
    longitude: float            # WGS84 × 10^7
    altitude: float             # Metros sobre WGS84
    heading: float              # 0.1° unidades
    speed: float                # 0.01 m/s unidades
    vehicle_length: float       # Metros
    vehicle_width: float        # Metros
    station_type: int = 5       # 5 = passengerCar (ETSI)
    raw_payload: bytes = b""    # Payload ASN.1 crudo


# ═══════════════════════════════════════════════════════════════════════
# Fase 3 — Placeholder: Algoritmo Húngaro para Asignación de IDs
# ═══════════════════════════════════════════════════════════════════════

class HungarianAssigner:
    """
    Asignador de IDs basado en el Algoritmo Húngaro.
    
    Evalúa la MATRIZ DE COSTOS entre:
      - Vehículos simulados (SUMO IDs)
      - Vehículos telemáticos reales (Station IDs / GPS)
    
    El costo se calcula como distancia euclidiana ponderada:
      C(i,j) = w₁·Δpos + w₂·Δvel + w₃·Δheading
    
    Minimiza el costo total de asignación para fusionar el gemelo
    digital con los datos reales.
    
    ┌──────────────────────────────────────────────────────────────┐
    │  PLACEHOLDER — Requiere: scipy.optimize.linear_sum_assignment │
    │  Se implementará en la Fase 4 (Fusión Digital-Real)          │
    └──────────────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        weight_position: float = 1.0,
        weight_velocity: float = 0.5,
        weight_heading: float = 0.3,
        max_assignment_cost: float = 50.0,
    ):
        self.w_pos = weight_position
        self.w_vel = weight_velocity
        self.w_head = weight_heading
        self.max_cost = max_assignment_cost
        self._assignments: Dict[str, str] = {}  # sim_id → telematic_id
        logger.info(
            "HungarianAssigner inicializado (placeholder). "
            "Pesos: pos=%.1f vel=%.1f head=%.1f",
            self.w_pos, self.w_vel, self.w_head,
        )

    def compute_cost_matrix(
        self,
        sim_vehicles: List[VehicleState],
        telematic_vehicles: List[TelematicMessage],
    ) -> Any:
        """
        Calcula la matriz de costos M×N entre vehículos simulados
        y observaciones telemáticas.
        
        Returns:
            np.ndarray de forma (M, N) con costos.
        
        TODO (Fase 4):
            import numpy as np
            from scipy.optimize import linear_sum_assignment
            
            M = len(sim_vehicles)
            N = len(telematic_vehicles)
            cost_matrix = np.zeros((M, N))
            
            for i, sv in enumerate(sim_vehicles):
                for j, tv in enumerate(telematic_vehicles):
                    dx = sv.position_xy[0] - tv.longitude
                    dy = sv.position_xy[1] - tv.latitude
                    d_pos = math.sqrt(dx**2 + dy**2)
                    d_vel = abs(sv.speed - tv.speed * 0.01)
                    d_head = abs(sv.heading - tv.heading * 0.1)
                    d_head = min(d_head, 360 - d_head)
                    
                    cost_matrix[i, j] = (
                        self.w_pos * d_pos +
                        self.w_vel * d_vel +
                        self.w_head * d_head
                    )
            
            return cost_matrix
        """
        raise NotImplementedError(
            "compute_cost_matrix — Pendiente de implementación (Fase 4). "
            "Requiere numpy y scipy."
        )

    def solve_assignment(
        self,
        sim_vehicles: List[VehicleState],
        telematic_vehicles: List[TelematicMessage],
    ) -> Dict[str, str]:
        """
        Resuelve la asignación óptima usando el Algoritmo Húngaro.
        
        Returns:
            Dict[sim_id, telematic_station_id]: Asignación óptima.
        
        TODO (Fase 4):
            cost_matrix = self.compute_cost_matrix(
                sim_vehicles, telematic_vehicles
            )
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            
            assignments = {}
            for r, c in zip(row_ind, col_ind):
                if cost_matrix[r, c] <= self.max_cost:
                    sim_id = sim_vehicles[r].veh_id
                    tel_id = telematic_vehicles[c].station_id
                    assignments[sim_id] = tel_id
            
            self._assignments = assignments
            return assignments
        """
        raise NotImplementedError(
            "solve_assignment — Pendiente de implementación (Fase 4). "
            "Requiere scipy.optimize.linear_sum_assignment."
        )

    def get_current_assignments(self) -> Dict[str, str]:
        """Retorna las asignaciones activas sim_id → telematic_id."""
        return dict(self._assignments)


# ═══════════════════════════════════════════════════════════════════════
# Fase 3 — Placeholder: Lector de Mensajes V2X (ETSI)
# ═══════════════════════════════════════════════════════════════════════

class V2XMessageReader(ABC):
    """
    Interfaz abstracta para lectores de mensajes V2X.
    
    Soportará múltiples backends:
      • MQTT (Mosquitto / HiveMQ)
      • AMQP (RabbitMQ)
      • DDS (OMG Data Distribution Service)
      • Socket UDP/TCP directo
    
    Formato de mensajes: ETSI EN 302 637-2 (CAM) y EN 302 637-3 (DENM)
    Codificación: ASN.1 UPER (Unaligned Packed Encoding Rules)
    
    ┌──────────────────────────────────────────────────────────────┐
    │  PLACEHOLDER — Se implementará en Fase 5 (Conectividad V2X)  │
    └──────────────────────────────────────────────────────────────┘
    """

    @abstractmethod
    def connect(self, endpoint: str, **kwargs) -> bool:
        """Establece conexión con el broker/fuente de mensajes V2X."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Cierra la conexión."""
        ...

    @abstractmethod
    def poll_messages(
        self, timeout_ms: int = 100
    ) -> List[TelematicMessage]:
        """
        Lee mensajes pendientes del canal V2X.
        
        Args:
            timeout_ms: Timeout de espera en milisegundos.
            
        Returns:
            Lista de mensajes telemáticos decodificados.
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Verifica si la conexión está activa."""
        ...


class MQTTv2XReader(V2XMessageReader):
    """
    Implementación MQTT para lectura de CAMs V2X.
    
    Tópicos esperados:
      • v2x/cam/{station_id}     — Cooperative Awareness Messages
      • v2x/denm/{station_id}    — Decentralized Environmental Notifications
      • v2x/spatem/{intersection} — Signal Phase and Timing Extended
    
    TODO (Fase 5):
        import paho.mqtt.client as mqtt
        
        self.client = mqtt.Client(client_id="sumo_shadow_paute")
        self.client.on_message = self._on_message
        self.client.connect(broker_host, broker_port)
        self.client.subscribe("v2x/cam/#")
        self.client.loop_start()
    """

    def __init__(self):
        self._connected = False
        self._message_buffer: List[TelematicMessage] = []
        logger.info("MQTTv2XReader inicializado (placeholder).")

    def connect(self, endpoint: str, **kwargs) -> bool:
        """Placeholder: Conexión MQTT."""
        logger.warning(
            "MQTTv2XReader.connect() — No implementado. "
            "Endpoint: %s", endpoint
        )
        return False

    def disconnect(self) -> None:
        """Placeholder: Desconexión MQTT."""
        self._connected = False

    def poll_messages(
        self, timeout_ms: int = 100
    ) -> List[TelematicMessage]:
        """Placeholder: Lectura de buffer MQTT."""
        return []

    def is_connected(self) -> bool:
        return self._connected

    def _decode_cam_asn1(self, raw_bytes: bytes) -> Optional[TelematicMessage]:
        """
        Decodifica un CAM en formato ASN.1 UPER (ETSI EN 302 637-2).
        
        Estructura del CAM:
          ├─ header
          │   ├─ protocolVersion (1)
          │   ├─ messageID (2 = CAM)
          │   └─ stationID (uint32)
          └─ cam
              ├─ generationDeltaTime (uint16, ms)
              └─ camParameters
                  ├─ basicContainer
                  │   ├─ stationType
                  │   └─ referencePosition (lat, lon, alt)
                  └─ highFrequencyContainer
                      ├─ heading
                      ├─ speed
                      └─ vehicleLength/Width
        
        TODO (Fase 5): Implementar decodificación ASN.1
        """
        raise NotImplementedError(
            "_decode_cam_asn1 — Requiere librería asn1tools "
            "con esquema ETSI ITS."
        )


# ═══════════════════════════════════════════════════════════════════════
# Fase 3 — Placeholder: Conexión a Visor Inmersivo
# ═══════════════════════════════════════════════════════════════════════

class ImmersiveViewerBridge:
    """
    Puente para conectar la simulación SUMO a un visor inmersivo online.
    
    Transmite el estado de la simulación a través de WebSocket para
    renderizado 3D en navegador (Three.js / CesiumJS / Unity WebGL).
    
    Protocolo:
      • Puerto: Configurable (default 8814)
      • Formato: JSON (comprimido con msgpack en producción)
      • Frecuencia: Cada N steps de simulación
    
    Mensaje tipo:
    {
        "type": "FRAME_UPDATE",
        "sim_time": 123.4,
        "vehicles": [
            {
                "id": "veh_42",
                "x": 500.0, "y": 300.0, "z": 0.0,
                "heading": 45.0,
                "speed": 8.5,
                "vtype": "car",
                "color": [102, 153, 230]
            },
            ...
        ],
        "traffic_lights": [...],
        "metrics": {...}
    }
    
    ┌──────────────────────────────────────────────────────────────┐
    │  PLACEHOLDER — Se implementará en Fase 6 (Visor Inmersivo)   │
    └──────────────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8814,
        broadcast_interval: int = 5,  # cada 5 steps
    ):
        self.host = host
        self.port = port
        self.broadcast_interval = broadcast_interval
        self._server = None
        self._clients: Set[Any] = set()
        logger.info(
            "ImmersiveViewerBridge configurado en %s:%d (placeholder). "
            "Intervalo de broadcast: %d steps.",
            host, port, broadcast_interval,
        )

    def start_server(self) -> bool:
        """
        Inicia el servidor WebSocket para el visor inmersivo.
        
        TODO (Fase 6):
            import asyncio
            import websockets
            
            async def handler(websocket, path):
                self._clients.add(websocket)
                try:
                    async for message in websocket:
                        await self._handle_viewer_command(message)
                finally:
                    self._clients.discard(websocket)
            
            self._server = websockets.serve(handler, self.host, self.port)
            asyncio.get_event_loop().run_until_complete(self._server)
        """
        logger.warning("ImmersiveViewerBridge.start_server() — No implementado.")
        return False

    def broadcast_frame(
        self,
        sim_time: float,
        vehicles: List[VehicleState],
        metrics: SimulationMetrics,
    ) -> None:
        """
        Transmite un frame de estado a todos los clientes conectados.
        
        TODO (Fase 6): Serializar a JSON/msgpack y enviar via WebSocket.
        """
        pass

    def stop_server(self) -> None:
        """Detiene el servidor WebSocket."""
        pass

    def get_connected_viewers(self) -> int:
        """Retorna el número de visores conectados."""
        return len(self._clients)


# ═══════════════════════════════════════════════════════════════════════
# Motor Principal de la Sombra Digital
# ═══════════════════════════════════════════════════════════════════════

class SombraDigitalEngine:
    """
    Motor orquestador de la Sombra Digital de Paute.
    
    Responsabilidades:
      1. Inicializar SUMO via TraCI
      2. Inyectar vehículos programáticamente (Fase 2)
      3. Aplicar confinamiento topológico con keepRoute=1
      4. Recopilar métricas de simulación
      5. (Futuro) Fusionar datos telemáticos V2X
      6. (Futuro) Transmitir a visor inmersivo
    """

    def __init__(
        self,
        sumocfg_path: str,
        use_gui: bool = True,
        port: int = TRACI_PORT,
        seed: int = 42,
        injection_rate: float = DEFAULT_INJECTION_RATE,
        max_vehicles: int = MAX_VEHICLES_CONCURRENT,
    ):
        self.sumocfg_path = os.path.abspath(sumocfg_path)
        self.use_gui = use_gui
        self.port = port
        self.seed = seed
        self.injection_rate = injection_rate
        self.max_vehicles = max_vehicles

        # Estado interno
        self._vehicles: Dict[str, VehicleState] = {}
        self._vehicle_counter: int = 0
        self._routes_cache: Dict[str, str] = {}
        self._edge_list: List[str] = []
        self._step: int = 0
        self._metrics = SimulationMetrics()
        self._rng = random.Random(seed)

        # Subsistemas (Fase 3 — placeholders activos)
        self.hungarian_assigner = HungarianAssigner()
        self.v2x_reader = MQTTv2XReader()
        self.viewer_bridge = ImmersiveViewerBridge(port=port + 1)

        # Callbacks de extensión
        self._pre_step_hooks: List[Callable[[int], None]] = []
        self._post_step_hooks: List[Callable[[int, SimulationMetrics], None]] = []

        logger.info(
            "SombraDigitalEngine inicializado. "
            "GUI=%s Puerto=%d Tasa=%.2f MaxVeh=%d",
            use_gui, port, injection_rate, max_vehicles,
        )

    # ─── Hooks de extensión ──────────────────────────────────────────

    def register_pre_step_hook(self, hook: Callable[[int], None]) -> None:
        """Registra un callback que se ejecuta ANTES de cada step."""
        self._pre_step_hooks.append(hook)

    def register_post_step_hook(
        self, hook: Callable[[int, SimulationMetrics], None]
    ) -> None:
        """Registra un callback que se ejecuta DESPUÉS de cada step."""
        self._post_step_hooks.append(hook)

    # ─── Inicialización de SUMO ──────────────────────────────────────

    def start(self) -> None:
        """Inicia SUMO y establece la conexión TraCI."""
        binary = checkBinary("sumo-gui" if self.use_gui else "sumo")

        sumo_cmd = [
            binary,
            "-c", self.sumocfg_path,
            "--start",
            "--quit-on-end", "false",
        ]

        logger.info("Iniciando SUMO: %s", " ".join(sumo_cmd))
        traci.start(sumo_cmd, port=self.port)
        logger.info("Conexión TraCI establecida en puerto %d.", self.port)

        # Cachear la lista de aristas (edges) para inyección
        self._edge_list = [
            e for e in traci.edge.getIDList()
            if not e.startswith(":")  # Excluir aristas internas
        ]

        if not self._edge_list:
            raise RuntimeError(
                "La red no contiene aristas válidas. "
                "Verifique el archivo .net.xml."
            )

        logger.info(
            "Red cargada: %d aristas, %d intersecciones.",
            len(self._edge_list),
            len(traci.junction.getIDList()),
        )

        # Detectar nodos de fricción por proximidad geográfica
        self._detect_friction_nodes()

    def _detect_friction_nodes(self) -> None:
        """
        Localiza los nodos de fricción en la red cargada
        basándose en proximidad a coordenadas conocidas.
        """
        junctions = traci.junction.getIDList()
        logger.info(
            "Buscando nodos de fricción entre %d intersecciones...",
            len(junctions),
        )

        # Actualizar FRICTION_NODES con las coordenadas reales
        for jid in junctions:
            pos = traci.junction.getPosition(jid)
            # Los nodos se identificarán manualmente o por nombre
            # tras la primera ejecución. Por ahora, registramos todos.
            pass

        logger.info("Nodos de fricción: detección pendiente de calibración.")

    # ─── Inyección de Vehículos ──────────────────────────────────────

    def _select_vehicle_class(self) -> VehicleClass:
        """Selecciona clase vehicular según distribución de tráfico."""
        r = self._rng.random()
        for vclass, threshold in TRAFFIC_DISTRIBUTION:
            if r <= threshold:
                return vclass
        return VehicleClass.CAR

    def _generate_route(self) -> Optional[Tuple[str, str, str]]:
        """
        Genera una ruta aleatoria origen→destino en la red.
        
        Returns:
            Tuple (route_id, edge_origen, edge_destino) o None si falla.
        """
        if len(self._edge_list) < 2:
            return None

        max_attempts = 10
        for _ in range(max_attempts):
            origin = self._rng.choice(self._edge_list)
            destination = self._rng.choice(self._edge_list)

            if origin == destination:
                continue

            route_id = f"route_{origin}_{destination}"

            # Verificar si la ruta ya existe en caché
            if route_id in self._routes_cache:
                return (route_id, origin, destination)

            # Intentar encontrar ruta válida via TraCI
            try:
                route_edges = traci.simulation.findRoute(
                    origin, destination
                ).edges

                if len(route_edges) >= 2:
                    traci.route.add(route_id, route_edges)
                    self._routes_cache[route_id] = route_id
                    return (route_id, origin, destination)
            except traci.TraCIException:
                continue

        return None

    def _inject_vehicle(self) -> Optional[str]:
        """
        Inyecta un vehículo en la simulación usando traci.vehicle.add().
        
        Implementa el patrón:
            1. traci.vehicle.add()     — Crear vehículo con ruta
            2. traci.vehicle.setSpeed() — Velocidad inicial
        
        Returns:
            ID del vehículo inyectado, o None si no fue posible.
        """
        # Verificar límite de vehículos concurrentes
        active_count = traci.vehicle.getIDCount()
        if active_count >= self.max_vehicles:
            return None

        # Generar ruta
        route_info = self._generate_route()
        if route_info is None:
            return None

        route_id, origin, destination = route_info

        # Seleccionar clase vehicular
        vclass = self._select_vehicle_class()

        # Generar ID único
        self._vehicle_counter += 1
        veh_id = f"veh_{self._vehicle_counter:06d}"

        try:
            # ┌─────────────────────────────────────────────────────┐
            # │  INYECCIÓN: traci.vehicle.add()                      │
            # │  Crea el vehículo con tipo y ruta asignados.         │
            # └─────────────────────────────────────────────────────┘
            traci.vehicle.add(
                vehID=veh_id,
                routeID=route_id,
                typeID=vclass.value,
                depart="now",
                departLane="best",
                departPos="random_free",
                departSpeed="random",
            )

            # ┌─────────────────────────────────────────────────────┐
            # │  VELOCIDAD INICIAL: traci.vehicle.setSpeed()         │
            # │  Establece velocidad coherente con el tipo vehicular │
            # └─────────────────────────────────────────────────────┘
            initial_speed = self._rng.uniform(3.0, 10.0)
            traci.vehicle.setSpeed(veh_id, initial_speed)

            # Registrar estado interno
            state = VehicleState(
                veh_id=veh_id,
                vtype=vclass,
                route_id=route_id,
                depart_step=self._step,
            )
            self._vehicles[veh_id] = state

            logger.debug(
                "Inyectado: %s [%s] en %s → %s (v=%.1f m/s)",
                veh_id, vclass.name, origin, destination, initial_speed,
            )
            return veh_id

        except traci.TraCIException as e:
            logger.warning("Fallo al inyectar %s: %s", veh_id, e)
            self._vehicle_counter -= 1
            return None

    # ─── Confinamiento Topológico ────────────────────────────────────

    def _apply_topological_confinement(self) -> None:
        """
        Aplica confinamiento topológico a TODOS los vehículos activos.
        
        Usa traci.vehicle.moveToXY() con keepRoute=1 para:
          • Obligar coherencia transversal (mantener carril)
          • Prevenir saltos entre aristas no conectadas
          • Mantener integridad de la topología de la red
        
        El parámetro keepRoute=1 es CRÍTICO:
          - keepRoute=0: El vehículo puede saltar a cualquier arista
          - keepRoute=1: El vehículo se mantiene en la ruta asignada ← USADO
          - keepRoute=2: Igual que 1, pero permite cambio de carril lateral
        
        En modo telemático (Fase 3+), este método fusionará las
        posiciones GPS/V2X con la topología de la red SUMO.
        """
        for veh_id in traci.vehicle.getIDList():
            try:
                # Obtener posición actual del vehículo
                x, y = traci.vehicle.getPosition(veh_id)
                heading = traci.vehicle.getAngle(veh_id)
                edge_id = traci.vehicle.getRoadID(veh_id)
                lane_idx = traci.vehicle.getLaneIndex(veh_id)

                # ┌─────────────────────────────────────────────────┐
                # │  CONFINAMIENTO TOPOLÓGICO:                       │
                # │  traci.vehicle.moveToXY(..., keepRoute=1)        │
                # │                                                  │
                # │  keepRoute=1 fuerza al vehículo a mantener       │
                # │  coherencia con la ruta asignada y el carril.    │
                # │  La posición XY se proyecta sobre la arista      │
                # │  más cercana que sea PARTE de su ruta.           │
                # └─────────────────────────────────────────────────┘
                traci.vehicle.moveToXY(
                    vehID=veh_id,
                    edgeID=edge_id,
                    lane=lane_idx,
                    x=x,
                    y=y,
                    angle=heading,
                    keepRoute=1,  # ← CRÍTICO: Confinamiento topológico
                )

                # Actualizar estado interno
                if veh_id in self._vehicles:
                    self._vehicles[veh_id].position_xy = (x, y)
                    self._vehicles[veh_id].current_edge = edge_id
                    self._vehicles[veh_id].current_lane = lane_idx
                    self._vehicles[veh_id].heading = heading
                    self._vehicles[veh_id].speed = traci.vehicle.getSpeed(
                        veh_id
                    )

            except traci.TraCIException as e:
                logger.debug(
                    "Confinamiento fallido para %s: %s", veh_id, e
                )

    def _apply_telematic_confinement(
        self,
        veh_id: str,
        telematic_x: float,
        telematic_y: float,
        telematic_heading: float,
        telematic_speed: float,
    ) -> None:
        """
        Aplica confinamiento topológico usando datos telemáticos V2X.
        
        Esta función es el PUENTE entre el mundo real (GPS/V2X)
        y la simulación (SUMO). Proyecta la posición GPS sobre
        la topología de la red para mantener coherencia.
        
        Args:
            veh_id: ID del vehículo en SUMO
            telematic_x: Coordenada X del GPS/V2X (UTM)
            telematic_y: Coordenada Y del GPS/V2X (UTM)
            telematic_heading: Rumbo del vehículo (grados)
            telematic_speed: Velocidad reportada (m/s)
        
        ┌──────────────────────────────────────────────────────────┐
        │  PREPARADO PARA FASE 4 — Fusión Digital-Real             │
        │  Se activará cuando HungarianAssigner esté implementado  │
        └──────────────────────────────────────────────────────────┘
        """
        try:
            edge_id = traci.vehicle.getRoadID(veh_id)
            lane_idx = traci.vehicle.getLaneIndex(veh_id)

            # Proyectar posición telemática sobre la red SUMO
            traci.vehicle.moveToXY(
                vehID=veh_id,
                edgeID=edge_id,
                lane=lane_idx,
                x=telematic_x,
                y=telematic_y,
                angle=telematic_heading,
                keepRoute=1,  # ← Mantener coherencia topológica
            )

            # Ajustar velocidad al valor telemático
            traci.vehicle.setSpeed(veh_id, telematic_speed)

            if veh_id in self._vehicles:
                self._vehicles[veh_id].position_xy = (
                    telematic_x, telematic_y
                )
                self._vehicles[veh_id].heading = telematic_heading
                self._vehicles[veh_id].speed = telematic_speed
                self._vehicles[veh_id].is_telematic = True

        except traci.TraCIException as e:
            logger.warning(
                "Confinamiento telemático fallido para %s: %s",
                veh_id, e,
            )

    # ─── Recopilación de Métricas ────────────────────────────────────

    def _collect_metrics(self) -> SimulationMetrics:
        """Recopila métricas agregadas del step actual."""
        veh_ids = traci.vehicle.getIDList()
        active = len(veh_ids)

        total_speed = 0.0
        total_waiting = 0.0

        for vid in veh_ids:
            try:
                total_speed += traci.vehicle.getSpeed(vid)
                total_waiting += traci.vehicle.getWaitingTime(vid)
            except traci.TraCIException:
                pass

        self._metrics = SimulationMetrics(
            step=self._step,
            time_s=traci.simulation.getTime(),
            vehicles_active=active,
            vehicles_injected_total=self._vehicle_counter,
            vehicles_arrived_total=traci.simulation.getArrivedNumber(),
            avg_speed_ms=total_speed / max(active, 1),
            total_waiting_time_s=total_waiting,
        )

        return self._metrics

    # ─── Bucle Principal de Simulación ───────────────────────────────

    def run(self, max_steps: int = SIMULATION_STEPS) -> None:
        """
        Ejecuta el bucle principal de la Sombra Digital.
        
        Estructura del bucle por step:
        
            ┌──────────────────────────────────────┐
            │  1. Pre-step hooks                    │
            │  2. (Futuro) Leer mensajes V2X        │
            │  3. (Futuro) Algoritmo Húngaro        │
            │  4. Inyectar vehículos simulados      │
            │  5. Aplicar confinamiento topológico  │
            │  6. Avanzar simulación (traci.step)   │
            │  7. Recopilar métricas                │
            │  8. (Futuro) Broadcast a visor        │
            │  9. Post-step hooks                   │
            │ 10. Limpiar vehículos que llegaron     │
            └──────────────────────────────────────┘
        """
        logger.info(
            "═══ Iniciando bucle de Sombra Digital ═══ "
            "(%d steps, %.1f segundos simulados)",
            max_steps, max_steps * 0.1,
        )

        start_wall = time.time()

        try:
            for step in range(max_steps):
                self._step = step

                # ── 1. Pre-step hooks ────────────────────────────
                for hook in self._pre_step_hooks:
                    hook(step)

                # ── 2. (Fase 3) Leer mensajes V2X ───────────────
                # telematic_msgs = self.v2x_reader.poll_messages()
                # if telematic_msgs:
                #     self._process_v2x_messages(telematic_msgs)

                # ── 3. (Fase 3) Algoritmo Húngaro ───────────────
                # if telematic_msgs and self._vehicles:
                #     assignments = self.hungarian_assigner.solve_assignment(
                #         list(self._vehicles.values()),
                #         telematic_msgs,
                #     )
                #     self._apply_assignments(assignments, telematic_msgs)

                # ── 4. Inyectar vehículos ────────────────────────
                if self._rng.random() < self.injection_rate:
                    self._inject_vehicle()

                # ── 5. Confinamiento topológico ──────────────────
                self._apply_topological_confinement()

                # ── 6. Avanzar simulación ────────────────────────
                traci.simulationStep()

                # ── 7. Recopilar métricas ────────────────────────
                metrics = self._collect_metrics()

                # ── 8. (Fase 3) Broadcast a visor ────────────────
                # if step % self.viewer_bridge.broadcast_interval == 0:
                #     self.viewer_bridge.broadcast_frame(
                #         metrics.time_s,
                #         list(self._vehicles.values()),
                #         metrics,
                #     )

                # ── 9. Post-step hooks ───────────────────────────
                for hook in self._post_step_hooks:
                    hook(step, metrics)

                # ── 10. Limpiar vehículos que llegaron ───────────
                arrived = traci.simulation.getArrivedIDList()
                for vid in arrived:
                    self._vehicles.pop(vid, None)

                # ── Log periódico ────────────────────────────────
                if step > 0 and step % 1000 == 0:
                    elapsed = time.time() - start_wall
                    rtf = (step * 0.1) / max(elapsed, 0.001)
                    logger.info(
                        "Step %d/%d │ t=%.1fs │ veh=%d │ "
                        "v̄=%.1f m/s │ inyectados=%d │ RTF=%.2fx",
                        step, max_steps,
                        metrics.time_s,
                        metrics.vehicles_active,
                        metrics.avg_speed_ms,
                        metrics.vehicles_injected_total,
                        rtf,
                    )

        except KeyboardInterrupt:
            logger.warning("Simulación interrumpida por el usuario.")

        except traci.FatalTraCIError as e:
            logger.error("Error fatal de TraCI: %s", e)

        finally:
            self._shutdown(start_wall)

    def _process_v2x_messages(
        self, messages: List[TelematicMessage]
    ) -> None:
        """
        Procesa mensajes V2X recibidos.
        
        TODO (Fase 5):
          1. Decodificar CAMs/DENMs
          2. Convertir coordenadas WGS84 → UTM (sistema de la red)
          3. Alimentar al Algoritmo Húngaro para asignación
          4. Actualizar posiciones telemáticas
        """
        pass

    def _apply_assignments(
        self,
        assignments: Dict[str, str],
        messages: List[TelematicMessage],
    ) -> None:
        """
        Aplica las asignaciones del Algoritmo Húngaro.
        
        Para cada par (sim_id → telematic_id):
          1. Buscar el mensaje telemático correspondiente
          2. Aplicar confinamiento telemático con moveToXY + keepRoute=1
          3. Marcar el vehículo como telemático
        
        TODO (Fase 4): Implementar tras HungarianAssigner.
        """
        pass

    def _shutdown(self, start_wall: float) -> None:
        """Cierre limpio de la simulación."""
        elapsed = time.time() - start_wall
        logger.info("═══ Simulación finalizada ═══")
        logger.info(
            "  Tiempo real:  %.1f s", elapsed,
        )
        logger.info(
            "  Simulado:     %.1f s", self._step * 0.1,
        )
        logger.info(
            "  Vehículos inyectados: %d", self._vehicle_counter,
        )
        logger.info(
            "  RTF (Real-Time Factor): %.2fx",
            (self._step * 0.1) / max(elapsed, 0.001),
        )

        try:
            traci.close()
            logger.info("  Conexión TraCI cerrada.")
        except Exception:
            pass

        # Cerrar subsistemas
        self.v2x_reader.disconnect()
        self.viewer_bridge.stop_server()


# ═══════════════════════════════════════════════════════════════════════
# Punto de Entrada
# ═══════════════════════════════════════════════════════════════════════

def parse_arguments() -> argparse.Namespace:
    """Parsea argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description=(
            "Orquestador de Sombra Digital — Paute, Azuay\n"
            "Simulación vehicular con SUMO + TraCI"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--nogui",
        action="store_true",
        help="Ejecutar sin interfaz gráfica (solo CLI).",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=SIMULATION_STEPS,
        help=f"Número de pasos de simulación (default: {SIMULATION_STEPS}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=TRACI_PORT,
        help=f"Puerto TraCI (default: {TRACI_PORT}).",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_INJECTION_RATE,
        help=f"Tasa de inyección por step (default: {DEFAULT_INJECTION_RATE}).",
    )
    parser.add_argument(
        "--max-vehicles",
        type=int,
        default=MAX_VEHICLES_CONCURRENT,
        help=f"Máx. vehículos simultáneos (default: {MAX_VEHICLES_CONCURRENT}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla para reproducibilidad (default: 42).",
    )
    parser.add_argument(
        "--sumocfg",
        type=str,
        default=None,
        help="Ruta al archivo .sumocfg (auto-detectado si no se especifica).",
    )

    return parser.parse_args()


def main() -> None:
    """Punto de entrada principal del orquestador."""
    args = parse_arguments()

    # Auto-detectar ruta de .sumocfg
    if args.sumocfg is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(script_dir)
        sumocfg = os.path.join(project_dir, "config", "paute.sumocfg")
    else:
        sumocfg = args.sumocfg

    if not os.path.isfile(sumocfg):
        logger.error("No se encontró: %s", sumocfg)
        logger.error("Ejecute primero los scripts de construcción de red.")
        sys.exit(1)

    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║     SOMBRA DIGITAL — PAUTE, AZUAY                      ║")
    logger.info("║     Simulación Vehicular con SUMO + TraCI               ║")
    logger.info("╚══════════════════════════════════════════════════════════╝")
    logger.info("")
    logger.info("  Configuración: %s", sumocfg)
    logger.info("  GUI:           %s", "Sí" if not args.nogui else "No")
    logger.info("  Puerto TraCI:  %d", args.port)
    logger.info("  Tasa inyección: %.2f", args.rate)
    logger.info("  Máx. vehículos: %d", args.max_vehicles)
    logger.info("  Steps:         %d (%.1f s simulados)", args.steps, args.steps * 0.1)
    logger.info("")

    # Crear y ejecutar el motor
    engine = SombraDigitalEngine(
        sumocfg_path=sumocfg,
        use_gui=not args.nogui,
        port=args.port,
        seed=args.seed,
        injection_rate=args.rate,
        max_vehicles=args.max_vehicles,
    )

    # Ejemplo de hook post-step (exportar a CSV cada 5000 steps)
    def csv_logger(step: int, metrics: SimulationMetrics) -> None:
        if step == 0:
            # Crear archivo CSV con headers
            csv_path = os.path.join(
                os.path.dirname(sumocfg), "..", "output", "metrics.csv"
            )
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            with open(csv_path, "w") as f:
                f.write(
                    "step,time_s,vehicles_active,injected_total,"
                    "arrived_total,avg_speed_ms,waiting_time_s\n"
                )
        if step % 100 == 0:
            csv_path = os.path.join(
                os.path.dirname(sumocfg), "..", "output", "metrics.csv"
            )
            with open(csv_path, "a") as f:
                f.write(
                    f"{metrics.step},{metrics.time_s:.1f},"
                    f"{metrics.vehicles_active},"
                    f"{metrics.vehicles_injected_total},"
                    f"{metrics.vehicles_arrived_total},"
                    f"{metrics.avg_speed_ms:.2f},"
                    f"{metrics.total_waiting_time_s:.1f}\n"
                )

    engine.register_post_step_hook(csv_logger)

    engine.start()
    engine.run(max_steps=args.steps)


if __name__ == "__main__":
    main()
