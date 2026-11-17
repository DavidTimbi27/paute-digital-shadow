#!/bin/bash
# ===========================================================================
# 01_download_osm.sh — Descarga del extracto OSM para Paute, Azuay
# ===========================================================================
# Bounding-box calibrado para capturar ambos nodos de fricción:
#   • Nodo 1 — Desvío interprovincial: Av. Interoceánica (E40) ∩ J.M. Barzallo
#   • Nodo 2 — Zona de mercado:       J.M. Barzallo ∩ Daniel Palacios
#
# Coordenadas (WGS84):
#   Sur:   -2.7870    Norte: -2.7720
#   Oeste: -78.7720   Este:  -78.7540
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"

# --- Bounding box: (S, W, N, E) ---
BBOX_S="-2.7870"
BBOX_W="-78.7720"
BBOX_N="-2.7720"
BBOX_E="-78.7540"

OUTPUT_FILE="$DATA_DIR/paute.osm"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Descarga OSM — Paute, Azuay (Sombra Digital)             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Bounding box: S=$BBOX_S  W=$BBOX_W  N=$BBOX_N  E=$BBOX_E"
echo "  Destino:      $OUTPUT_FILE"
echo ""

# OpenStreetMap API directa para descarga de BBox
OSM_API_URL="https://api.openstreetmap.org/api/0.6/map?bbox=${BBOX_W},${BBOX_S},${BBOX_E},${BBOX_N}"

mkdir -p "$DATA_DIR"

echo "[1/2] Descargando mapa desde OpenStreetMap API..."
if command -v curl &>/dev/null; then
    curl -sL "$OSM_API_URL" -o "$OUTPUT_FILE"
elif command -v wget &>/dev/null; then
    wget -q -O "$OUTPUT_FILE" "$OSM_API_URL"
else
    echo "ERROR: Se requiere curl o wget."
    exit 1
fi

echo ""
echo "[2/2] Validando archivo descargado..."
if [ -s "$OUTPUT_FILE" ]; then
    FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    NODE_COUNT=$(grep -c "<node" "$OUTPUT_FILE" || echo "0")
    WAY_COUNT=$(grep -c "<way" "$OUTPUT_FILE" || echo "0")
    echo "  ✓ Archivo: $OUTPUT_FILE ($FILE_SIZE)"
    echo "  ✓ Nodos:   $NODE_COUNT"
    echo "  ✓ Vías:    $WAY_COUNT"
else
    echo "  ✗ ERROR: El archivo está vacío o la descarga falló."
    exit 1
fi

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Descarga completada. Ejecute 02_build_network.sh"
echo "══════════════════════════════════════════════════════════════"
