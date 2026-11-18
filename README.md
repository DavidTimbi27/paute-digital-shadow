# Sombra Digital de Tráfico de Paute

Prototipo académico que combina una red SUMO de Paute, una visualización 3D web y una cámara USB opcional para detectar y contar vehículos en el cruce de Av. Interoceánica (E40) con José Miguel Barzallo, junto al Mercado 26 de Febrero.

> **Estado de evidencia:** el software y sus rutas se pueden ejecutar localmente. La cámara produce detecciones en vivo cuando hay cámara/modelo disponibles. Este repositorio no incluye video real anotado ni una evaluación independiente de precisión, latencia o error de posición. Los conteos observados en la interfaz y las pruebas sintéticas de software no equivalen a métricas de campo.

## Componentes

- `scripts/server_web.py`: servidor web, telemetría, detector Ultralytics/YOLOv11, seguimiento y enlace opcional con TraCI. Puerto HTTP predeterminado: **8085**; WebSocket: `/ws/telemetry`.
- `web/`: interfaz Three.js y red 3D exportada.
- `net/` y `config/`: red SUMO, rutas, perfiles y configuración.
- `data/paute.osm`: datos geográficos de OpenStreetMap usados para la red/geometría; verificar atribución y licencia ODbL al redistribuir.
- `scripts/export_network_3d.py`: regenera `web/paute_network_3d.json` desde la red y datos disponibles.
- `docs/`: propuesta, informe IEEE, referencias y presentación editables en LaTeX.

## Requisitos y ejecución

El entorno observado al documentar fue Python 3.14.3, SUMO 1.18.0 para la red y `aiohttp 3.14.5`, `fastapi 0.163.1`, `uvicorn 0.54.0`, `ultralytics 8.4.215`, `opencv-python 4.14.0.94`, `Pillow 12.3.0`, `lap 0.5.14` y `torch 2.15.0`. El archivo `requirements.txt` define rangos, no un lockfile; para reproducibilidad académica, guarde `python -m pip freeze` y las versiones exactas en cada ejecución. Las versiones disponibles cambian con el tiempo.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Descargue un peso Ultralytics compatible con YOLOv11 (`yolo11n.pt`) y colóquelo en la raíz. Los pesos se excluyen del control de versiones: el usuario debe verificar y aceptar su licencia por separado.

En una primera terminal PowerShell, genere la demanda sin tráfico sintético sobre el bloque reservado a la cámara y abra SUMO-GUI mediante WSLg:

```powershell
python scripts/filter_sumo_routes.py
$projectInWsl = (wsl.exe -d Ubuntu -- wslpath -a "$PWD").Trim()
wsl.exe -d Ubuntu -- bash -lc "cd '$projectInWsl' && sumo-gui -c config/paute.sumocfg --start --delay 100"
```

Luego, en otra terminal PowerShell, inicie el servidor web:

```powershell
python scripts/server_web.py
```

Abra `http://localhost:8085` y permita el acceso a la cámara USB. El sitio puede servirse en la red local; el acceso a cámara desde otros equipos normalmente requiere HTTPS o `localhost`. SUMO/TraCI usa el puerto 8813. En Windows, el backend detecta las herramientas SUMO en Ubuntu WSL para cargar TraCI.

## Regeneración y configuración

```powershell
python scripts/export_network_3d.py
```

La configuración del escenario documenta semilla SUMO 42 y paso de 0.1 s. El nodo de cámara exportado es `2910139955`; sus rutas observadas/modeladas están en `web/paute_network_3d.json` bajo `cctv_reference.routes` (`SUBE`, `BAJA`). La clasificación de CO₂ que muestra la aplicación es una estimación basada en factores configurados; no es una medición de emisiones.

Antes de regenerar una ejecución comparable, registre `python --version`, `sumo --version`, `python -m pip freeze`, los parámetros, la fecha, la semilla y la fuente de los videos. La salida grande de SUMO y los pesos no se versionan.

## Informe y presentación

Desde la carpeta `docs/`, compile `propuesta.tex`, `informe.tex` y `presentacion.tex` con una distribución LaTeX que incluya IEEEtran y Beamer. Para el informe, ejecute LaTeX, BibTeX y LaTeX dos veces. Las imágenes son regenerables desde la red exportada con `python scripts/build_report_assets.py` (ejecutado desde la raíz del repositorio).

## Validación responsable

La rúbrica requiere comparar con anotaciones independientes emparejadas por vehículo/tiempo y reportar el denominador de cada métrica. Este repositorio aún no contiene esas anotaciones. Por tanto, no se publican valores de precisión, recall, exactitud de clase, error espacial o retraso como resultados medidos. Use `docs/validation/annotations_template.csv` para preparar una muestra anonimizada y documente cámara, intervalo, reglas de anotación y desacuerdos antes de calcular métricas.

El informe identifica además como trabajo pendiente la reproducción acelerada offline con pausa/búsqueda y una matriz OD de salidas validada por brazo. No confundir tráfico sintético de SUMO con conteos reales.

## Repositorio GitHub

Este directorio puede versionarse con Git. Excluye `.venv`, pesos YOLO y resultados voluminosos de SUMO. Revise las licencias de OpenStreetMap, SUMO y los pesos antes de publicar. La publicación en el perfil `DavidTimbi27` requiere conectar GitHub en esta sesión; no se debe incluir video de cámara ni datos personales sin autorización.

## Estructura

```text
config/  data/  net/  scripts/  web/  docs/
```
