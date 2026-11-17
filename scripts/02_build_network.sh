#!/bin/bash
# ===========================================================================
# 02_build_network.sh — Conversión OSM → Red SUMO (.net.xml)
# ===========================================================================
# Pipeline de netconvert con parámetros optimizados para:
#   • Limpieza de geometría redundante
#   • Heurísticos de rampas y unión de intersecciones
#   • Optimización de semáforos
#   • Elevación constante Z=0 para el plano 3D (OSG)
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# --- Rutas de entrada/salida ---
OSM_FILE="$PROJECT_DIR/data/paute.osm"
NET_FILE="$PROJECT_DIR/net/paute.net.xml"
TYPE_FILE="$PROJECT_DIR/config/osmNetconvert.typ.xml"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   netconvert — Red Vial de Paute para SUMO                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# --- Validar entrada ---
if [ ! -f "$OSM_FILE" ]; then
    echo "ERROR: No se encontró $OSM_FILE"
    echo "       Ejecute primero: bash 01_download_osm.sh"
    exit 1
fi

# --- Crear archivo de tipos OSM si no existe ---
if [ ! -f "$TYPE_FILE" ]; then
    echo "[0/3] Generando archivo de tipos OSM por defecto..."
    # SUMO incluye un tipo por defecto; copiamos si está disponible
    SUMO_TYPE_DEFAULT="$SUMO_HOME/data/typemap/osmNetconvert.typ.xml"
    if [ -f "$SUMO_TYPE_DEFAULT" ]; then
        cp "$SUMO_TYPE_DEFAULT" "$TYPE_FILE"
        echo "  ✓ Copiado desde \$SUMO_HOME"
    else
        echo "  ⚠ No se encontró archivo de tipos en \$SUMO_HOME/data/typemap/"
        echo "    Se usará la configuración interna de netconvert."
        TYPE_FILE=""
    fi
fi

mkdir -p "$(dirname "$NET_FILE")"

echo "[1/3] Ejecutando netconvert..."
echo ""

# --- Comando netconvert completo ---
NETCONVERT_CMD="netconvert \
    --osm-files \"$OSM_FILE\" \
    --output-file \"$NET_FILE\" \
    \
    --geometry.remove \
    --roundabouts.guess \
    --ramps.guess \
    --junctions.join \
    --junctions.join-dist 15 \
    --junctions.corner-detail 5 \
    --junctions.internal-link-detail 4 \
    \
    --tls.guess-signals \
    --tls.discard-simple \
    --tls.join \
    --tls.default-type actuated \
    --tls.green.time 31 \
    \
    --edges.join \
    --remove-edges.isolated \
    --keep-edges.by-vclass passenger,bus,truck \
    \
    --no-turnarounds.tls \
    --offset.disable-normalization \
    --lefthand false \
    \
    --default.lanewidth 3.2 \
    --default.speed 13.89 \
    --osm.sidewalks false \
    --osm.crossings false \
    \
    --proj.utm"

# Agregar archivo de tipos si existe
if [ -n "${TYPE_FILE:-}" ] && [ -f "${TYPE_FILE:-}" ]; then
    NETCONVERT_CMD="$NETCONVERT_CMD --type-files \"$TYPE_FILE\""
fi

echo "  Comando:"
echo "  $NETCONVERT_CMD"
echo ""

eval $NETCONVERT_CMD

echo ""
echo "[2/3] Validando red generada..."

if [ -s "$NET_FILE" ]; then
    NET_SIZE=$(du -h "$NET_FILE" | cut -f1)
    EDGE_COUNT=$(grep -c "<edge " "$NET_FILE" || echo "0")
    JUNCTION_COUNT=$(grep -c "<junction " "$NET_FILE" || echo "0")
    echo "  ✓ Red:          $NET_FILE ($NET_SIZE)"
    echo "  ✓ Aristas:      $EDGE_COUNT"
    echo "  ✓ Intersecciones: $JUNCTION_COUNT"
else
    echo "  ✗ ERROR: La red generada está vacía."
    exit 1
fi

echo ""
echo "[3/3] Generando rutas aleatorias de prueba con randomTrips..."

# Generar archivo de rutas de prueba para validación inicial
TRIPS_FILE="$PROJECT_DIR/net/paute_test.trips.xml"
ROUTE_FILE="$PROJECT_DIR/net/paute_test.rou.xml"

RANDOM_TRIPS_PY=""
if [ -n "${SUMO_HOME:-}" ]; then
    RANDOM_TRIPS_PY="$SUMO_HOME/tools/randomTrips.py"
fi

if [ -n "$RANDOM_TRIPS_PY" ] && [ -f "$RANDOM_TRIPS_PY" ]; then
    python3 "$RANDOM_TRIPS_PY" \
        -n "$NET_FILE" \
        -o "$TRIPS_FILE" \
        -r "$ROUTE_FILE" \
        --begin 0 \
        --end 3600 \
        --period 2.0 \
        --fringe-factor 5 \
        --validate \
        --seed 42
    echo "  ✓ Rutas de prueba: $ROUTE_FILE"
else
    echo "  ⚠ randomTrips.py no encontrado. Configure \$SUMO_HOME."
    echo "    Ejemplo: export SUMO_HOME=/usr/share/sumo"
fi

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Red construida exitosamente."
echo "  Para visualizar: sumo-gui -c config/paute.sumocfg"
echo "══════════════════════════════════════════════════════════════"
