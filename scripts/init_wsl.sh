#!/bin/bash
# ===========================================================================
# init_wsl.sh — Inicialización del Entorno de Sombra Digital en WSL/Ubuntu
# ===========================================================================
# Este script configura todo el entorno necesario para ejecutar la
# simulación vehicular de Paute en SUMO via WSL (Windows Subsystem for Linux).
#
# Uso:
#   bash init_wsl.sh [--install-deps] [--build] [--run] [--all]
#
# Opciones:
#   --install-deps   Instala SUMO y dependencias en Ubuntu/WSL
#   --build          Descarga OSM y construye la red
#   --run            Ejecuta la simulación con SUMO-GUI
#   --run-nogui      Ejecuta sin GUI (modo batch)
#   --all            Ejecuta todo (instalar + construir + ejecutar)
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║   ░██████╗░█████╗░███╗░░░███╗██████╗░██████╗░░█████╗░         ║"
    echo "║   ██╔════╝██╔══██╗████╗░████║██╔══██╗██╔══██╗██╔══██╗         ║"
    echo "║   ╚█████╗░██║░░██║██╔████╔██║██████╦╝██████╔╝███████║         ║"
    echo "║   ░╚═══██╗██║░░██║██║╚██╔╝██║██╔══██╗██╔══██╗██╔══██║         ║"
    echo "║   ██████╔╝╚█████╔╝██║░╚═╝░██║██████╦╝██║░░██║██║░░██║         ║"
    echo "║   ╚═════╝░░╚════╝░╚═╝░░░░░╚═╝╚═════╝░╚═╝░░╚═╝╚═╝░░╚═╝       ║"
    echo "║                                                                ║"
    echo "║   DIGITAL — Paute, Azuay, Ecuador                             ║"
    echo "║   Gemelo Digital de Tráfico Urbano                             ║"
    echo "║                                                                ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err()  { echo -e "${RED}[ERROR]${NC} $1"; }

# ─────────────────────────────────────────────────────────────────────
# Instalación de dependencias
# ─────────────────────────────────────────────────────────────────────
install_dependencies() {
    log_info "Instalando dependencias del sistema..."

    # Actualizar repositorios
    sudo apt-get update -qq

    # Instalar SUMO desde el PPA oficial
    log_info "Añadiendo PPA de Eclipse SUMO..."
    sudo add-apt-repository -y ppa:sumo/stable 2>/dev/null || true
    sudo apt-get update -qq

    log_info "Instalando SUMO y herramientas..."
    sudo apt-get install -y \
        sumo \
        sumo-tools \
        sumo-doc \
        python3 \
        python3-pip \
        python3-venv \
        wget \
        curl \
        libgl1-mesa-glx \
        libglu1-mesa \
        libopenscenegraph-dev \
        mesa-utils

    # Configurar SUMO_HOME
    if ! grep -q "SUMO_HOME" ~/.bashrc; then
        echo '' >> ~/.bashrc
        echo '# SUMO - Simulation of Urban Mobility' >> ~/.bashrc
        echo 'export SUMO_HOME=/usr/share/sumo' >> ~/.bashrc
        echo 'export PATH="$PATH:$SUMO_HOME/bin"' >> ~/.bashrc
        log_info "SUMO_HOME añadido a ~/.bashrc"
    fi

    export SUMO_HOME=/usr/share/sumo
    export PATH="$PATH:$SUMO_HOME/bin"

    # Instalar dependencias Python
    log_info "Instalando dependencias Python..."
    pip3 install --user \
        traci \
        sumolib \
        lxml \
        2>/dev/null || true

    # Verificar instalación
    echo ""
    log_info "Verificando instalación..."
    echo -e "  SUMO version: $(sumo --version 2>/dev/null | head -1 || echo 'No encontrado')"
    echo -e "  SUMO_HOME:    ${SUMO_HOME:-'No definido'}"
    echo -e "  Python:       $(python3 --version 2>/dev/null || echo 'No encontrado')"
    echo -e "  netconvert:   $(netconvert --version 2>/dev/null | head -1 || echo 'No encontrado')"

    # Verificar soporte de display para SUMO-GUI via WSL
    log_info "Verificando display para SUMO-GUI..."
    if [ -z "${DISPLAY:-}" ]; then
        log_warn "DISPLAY no está configurado."
        log_warn "Para usar SUMO-GUI en WSL, necesita un servidor X11:"
        echo "  Opción 1 (WSLg - Windows 11): Ya integrado, debería funcionar."
        echo "  Opción 2 (VcXsrv):           Instalar VcXsrv y ejecutar:"
        echo "    export DISPLAY=\$(cat /etc/resolv.conf | grep nameserver | awk '{print \$2}'):0.0"
        echo "    export LIBGL_ALWAYS_INDIRECT=1"
        echo ""
        echo "  Añada estas líneas a ~/.bashrc para persistencia."
    else
        log_info "DISPLAY configurado: $DISPLAY"
    fi

    echo ""
    log_info "═══ Dependencias instaladas correctamente ═══"
}

# ─────────────────────────────────────────────────────────────────────
# Construcción de la red
# ─────────────────────────────────────────────────────────────────────
build_network() {
    log_info "═══ Construyendo red vial ═══"
    echo ""

    # Paso 1: Descargar datos OSM
    log_info "Ejecutando descarga OSM..."
    bash "$SCRIPT_DIR/01_download_osm.sh"
    echo ""

    # Paso 2: Construir red con netconvert
    log_info "Ejecutando netconvert..."
    bash "$SCRIPT_DIR/02_build_network.sh"
    echo ""

    log_info "═══ Red construida exitosamente ═══"
}

# ─────────────────────────────────────────────────────────────────────
# Ejecución de la simulación
# ─────────────────────────────────────────────────────────────────────
run_simulation() {
    local use_gui="${1:-true}"

    # Verificar que la red existe
    if [ ! -f "$PROJECT_DIR/net/paute.net.xml" ]; then
        log_err "Red no encontrada. Ejecute primero: bash init_wsl.sh --build"
        exit 1
    fi

    log_info "═══ Iniciando Sombra Digital ═══"
    echo ""
    echo "  Modo:           $([ "$use_gui" = "true" ] && echo "SUMO-GUI (2D/3D)" || echo "CLI (sin GUI)")"
    echo "  Puerto TraCI:   8813"
    echo "  Visor futuro:   8814 (placeholder)"
    echo ""

    cd "$PROJECT_DIR"

    if [ "$use_gui" = "true" ]; then
        # Modo GUI: Ejecutar orquestador con SUMO-GUI
        log_info "Lanzando orquestador con SUMO-GUI..."
        echo ""
        echo "  Para vista 3D (OSG), ejecute manualmente:"
        echo "    sumo-gui --osg-view true -c config/paute.sumocfg"
        echo ""

        python3 scripts/orquestador.py \
            --sumocfg config/paute.sumocfg \
            --steps 36000 \
            --rate 0.15 \
            --max-vehicles 120 \
            --port 8813
    else
        # Modo CLI: Sin GUI
        log_info "Lanzando orquestador sin GUI..."
        python3 scripts/orquestador.py \
            --nogui \
            --sumocfg config/paute.sumocfg \
            --steps 36000 \
            --rate 0.15 \
            --max-vehicles 120 \
            --port 8813
    fi
}

# ─────────────────────────────────────────────────────────────────────
# Ejecución directa de SUMO-GUI (sin orquestador)
# ─────────────────────────────────────────────────────────────────────
run_sumo_gui_standalone() {
    log_info "Lanzando SUMO-GUI en modo standalone (sin TraCI)..."

    # Verificar red
    if [ ! -f "$PROJECT_DIR/net/paute.net.xml" ]; then
        log_err "Red no encontrada. Ejecute primero: bash init_wsl.sh --build"
        exit 1
    fi

    # Para modo standalone, necesitamos rutas de prueba
    if [ ! -f "$PROJECT_DIR/net/paute_test.rou.xml" ]; then
        log_warn "No hay rutas de prueba. Generando..."
        bash "$SCRIPT_DIR/02_build_network.sh"
    fi

    cd "$PROJECT_DIR"

    # Vista 2D
    echo "  [2D] sumo-gui -c config/paute.sumocfg"
    sumo-gui -c config/paute.sumocfg &

    # Para 3D (descomentar):
    # echo "  [3D] sumo-gui --osg-view true -c config/paute.sumocfg"
    # sumo-gui --osg-view true -c config/paute.sumocfg &
}

# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────
main() {
    banner

    case "${1:-}" in
        --install-deps)
            install_dependencies
            ;;
        --build)
            build_network
            ;;
        --run)
            run_simulation true
            ;;
        --run-nogui)
            run_simulation false
            ;;
        --gui-standalone)
            run_sumo_gui_standalone
            ;;
        --all)
            install_dependencies
            echo ""
            build_network
            echo ""
            run_simulation true
            ;;
        *)
            echo "Uso: bash init_wsl.sh [OPCIÓN]"
            echo ""
            echo "Opciones:"
            echo "  --install-deps   Instalar SUMO y dependencias"
            echo "  --build          Descargar OSM y construir red"
            echo "  --run            Ejecutar con SUMO-GUI (TraCI)"
            echo "  --run-nogui      Ejecutar sin GUI (batch)"
            echo "  --gui-standalone Abrir SUMO-GUI sin TraCI"
            echo "  --all            Instalar + Construir + Ejecutar"
            echo ""
            echo "Flujo recomendado:"
            echo "  1. bash init_wsl.sh --install-deps"
            echo "  2. bash init_wsl.sh --build"
            echo "  3. bash init_wsl.sh --run"
            ;;
    esac
}

main "$@"
