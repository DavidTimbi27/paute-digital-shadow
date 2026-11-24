/**
 * app.js — Sombra Digital Paute 3D (Versión con Coordenadas y Polígonos Exactos)
 * Motor WebGL Three.js con Proyección Oficial SUMO, Polígonos OSM Reales,
 * POIs Georreferenciados al Milímetro, Emisiones CO2 y Navegación WASD.
 */

// --- Variables Principales ---
let scene, camera, renderer, controls;
let networkData = null;

// Grupos de Capas
let roadGroup, buildingsGroup, poisGroup, streetlightsGroup, vehiclesGroup, trailsGroup;

// Estado de Capas
const layersState = {
    buildings: true,
    pois: true,
    streetlights: true,
    trails: true
};

// Mapa de Vehículos Activos (id -> { group, trail, trailHistory, data, spotLight })
const vehiclesMap = new Map();
let inspectedVehicleId = null;
let followedVehicleId = null;
let isFollowMode = false;

// Iluminación y Tiempos del Día
let ambientLight, sunLight, hemiLight;
let currentDayTime = 'night';

// Controles de Teclado (Vuelo Libre WASD)
const keyState = { w: false, a: false, s: false, d: false, q: false, e: false };

// Raycasting para Selección Interactiva
let raycaster, mouse;

// Configuración Visual del Parque Automotor de Paute
const FLEET_STYLES = {
    moto: {
        color: 0x00e5ff,
        bodyDim: [0.8, 1.1, 2.2],
        hasCabin: false,
        name: "Motocicleta 150cc"
    },
    car: {
        color: 0x2979ff,
        bodyDim: [1.8, 1.4, 4.5],
        cabinDim: [1.6, 0.9, 2.5],
        hasCabin: true,
        name: "Sedán Particular"
    },
    pickup: {
        color: 0x00e676,
        bodyDim: [1.9, 1.7, 5.3],
        cabinDim: [1.8, 1.0, 2.8],
        hasCabin: true,
        name: "Camioneta D-Max/Hilux"
    },
    bus: {
        color: 0xff9100,
        bodyDim: [2.5, 3.2, 11.5],
        hasCabin: false,
        name: "Autobús Intercantonal"
    },
    truck: {
        color: 0xff3d00,
        bodyDim: [2.4, 3.0, 7.8],
        cabinDim: [2.3, 2.4, 2.5],
        hasCabin: true,
        name: "Camión Mercado"
    },
    trailer: {
        color: 0xb388ff,
        bodyDim: [2.55, 3.6, 16.5],
        hasCabin: true,
        name: "Tráiler E40"
    }
};

// Presets de Cámara con Coordenadas Exactas (Matemática Oficial SUMO)
const CAMERA_PRESETS = {
    overview: { pos: [0, 950, 750], target: [0, 0, -250] },
    hospital: { pos: [-763.0, 160, -170], target: [-763.0, 0, -316.0] }, // Hospital Básico Paute
    market: { pos: [-64.8, 140, -210], target: [-64.8, 0, -350.1] },     // Mercado 26 de Febrero
    terminal: { pos: [622.4, 150, -135], target: [622.4, 0, -274.5] },   // Terminal Terrestre
    e40: { pos: [0, 95, 75], target: [0, 0, 0] },
    cctv: { pos: [0, 42, 35], target: [0, 0, 0] }
};

// Variables para Sistema de Cámara USB en Vivo
let cctvGroup = null;
let cctvStream = null;
let cctvRtspTextureCanvas = null;
let cctvScreenMaterial = null;
let isCCTVModalOpen = false;
let cctvFallbackAnimationId = null;
let cctvTwinRenderer = null;
let cctvTwinCamera = null;
let cctvPipTwinRenderer = null;
let cctvPipTwinCamera = null;
let cctvTwinControls = null;
let cctvPipTwinControls = null;
let lastCctvTwinRenderAt = 0;
let pipViewMode = "dual";
let cctvLens = null;
let visionFramePending = false;
let visionFrameTimeoutId = null;
let lastPipPaintAt = 0;
let visionFrameCanvas = null;
let visionOverlayResizeObserver = null;
let mirrorDualLayout = true;
let CCTV_REFERENCE = null;
const CCTV_ANCHOR = new THREE.Vector3();
const CCTV_LOOK_AT = new THREE.Vector3();

// ─── Inicialización ────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
    setupCollapsiblePanels();
    initScene();
    setupKeyboardFlight();
    setupRaycasting();
    loadNetworkData();
    connectWebSocket();
    initWebcamSystem();
    setupVisionOverlayResize();
    animate();
});

function setupCollapsiblePanels() {
    document.querySelectorAll('.panel-collapse-toggle[data-collapse-target]').forEach(button => {
        const panel = document.getElementById(button.dataset.collapseTarget);
        if (!panel) return;

        const storageKey = `paute-panel-collapsed-${panel.id}`;
        const label = button.dataset.collapseLabel || 'Panel';
        const updateButton = collapsed => {
            button.textContent = collapsed ? `+ ${label}` : '−';
            button.setAttribute('aria-expanded', String(!collapsed));
            button.title = `${collapsed ? 'Expandir' : 'Minimizar'} ${label.toLowerCase()}`;
        };

        let collapsed = false;
        try { collapsed = localStorage.getItem(storageKey) === 'true'; } catch (_) { /* almacenamiento opcional */ }
        panel.classList.toggle('panel-collapsed', collapsed);
        updateButton(collapsed);

        button.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            collapsed = !panel.classList.contains('panel-collapsed');
            panel.classList.toggle('panel-collapsed', collapsed);
            updateButton(collapsed);
            try { localStorage.setItem(storageKey, String(collapsed)); } catch (_) { /* almacenamiento opcional */ }
        });
    });
}

function initScene() {
    const container = document.getElementById('canvas-container');

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0d14);
    scene.fog = new THREE.FogExp2(0x0a0d14, 0.0004);

    camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 1, 14000);
    camera.position.set(0, 950, 750);

    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    container.appendChild(renderer.domElement);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.maxPolarAngle = Math.PI / 2 - 0.04;
    controls.minDistance = 15;
    controls.maxDistance = 4000;
    controls.target.set(0, 0, -250);

    // Grupos de capas
    roadGroup = new THREE.Group();
    buildingsGroup = new THREE.Group();
    poisGroup = new THREE.Group();
    streetlightsGroup = new THREE.Group();
    vehiclesGroup = new THREE.Group();
    trailsGroup = new THREE.Group();

    scene.add(roadGroup);
    scene.add(buildingsGroup);
    scene.add(poisGroup);
    scene.add(streetlightsGroup);
    scene.add(vehiclesGroup);
    scene.add(trailsGroup);

    setupLighting();
    createTerrain();
    buildCCTVMount();
    initCCTVTwinRenderer();

    window.addEventListener('resize', onWindowResize);
}

function initCCTVTwinRenderer() {
    const modalCanvas = document.getElementById('cctv-twin-canvas');
    const pipCanvas = document.getElementById('cctv-pip-twin-canvas');
    if (modalCanvas) {
        cctvTwinRenderer = new THREE.WebGLRenderer({ canvas: modalCanvas, antialias: true, alpha: false });
        cctvTwinRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        cctvTwinRenderer.setClearColor(0x060911, 1);
        cctvTwinCamera = new THREE.PerspectiveCamera(60, 16 / 9, 0.1, 1200);
        cctvTwinControls = createCCTVTwinControls(cctvTwinCamera, modalCanvas);
    }
    if (pipCanvas) {
        cctvPipTwinRenderer = new THREE.WebGLRenderer({ canvas: pipCanvas, antialias: false, alpha: false });
        cctvPipTwinRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
        cctvPipTwinRenderer.setClearColor(0x060911, 1);
        cctvPipTwinCamera = new THREE.PerspectiveCamera(60, 16 / 9, 0.1, 1200);
        cctvPipTwinControls = createCCTVTwinControls(cctvPipTwinCamera, pipCanvas);
    }
    resetCCTVTwinView(false);
}

function createCCTVTwinControls(viewCamera, canvas) {
    if (!THREE.OrbitControls || !canvas) return null;
    const orbit = new THREE.OrbitControls(viewCamera, canvas);
    orbit.enableDamping = true;
    orbit.dampingFactor = 0.09;
    orbit.enablePan = true;
    orbit.screenSpacePanning = true;
    orbit.minDistance = CCTV_REFERENCE?.view_camera?.min_distance_m ?? 7;
    orbit.maxDistance = CCTV_REFERENCE?.view_camera?.max_distance_m ?? 120;
    orbit.maxPolarAngle = Math.PI * 0.49;
    orbit.addEventListener('change', () => syncCCTVTwinViews(orbit));
    return orbit;
}

let syncingCCTVTwinViews = false;
let restoringCCTVTwinView = false;
let cctvTwinPersistTimer = null;
const CCTV_TWIN_VIEW_KEY = 'paute-cctv-twin-view-v2';

function syncCCTVTwinViews(sourceControls) {
    if (!sourceControls || syncingCCTVTwinViews || restoringCCTVTwinView) return;
    syncingCCTVTwinViews = true;
    const sourceCamera = sourceControls.object;
    const counterpart = sourceControls === cctvTwinControls ? cctvPipTwinControls : cctvTwinControls;
    if (counterpart) {
        counterpart.target.copy(sourceControls.target);
        counterpart.object.position.copy(sourceCamera.position);
        counterpart.object.quaternion.copy(sourceCamera.quaternion);
        counterpart.object.fov = sourceCamera.fov;
        counterpart.object.updateProjectionMatrix();
        counterpart.update();
    }
    clearTimeout(cctvTwinPersistTimer);
    cctvTwinPersistTimer = setTimeout(() => {
        try { localStorage.setItem(CCTV_TWIN_VIEW_KEY, JSON.stringify({
            target: sourceControls.target.toArray(),
            offset: sourceCamera.position.clone().sub(sourceControls.target).toArray(),
            fov: sourceCamera.fov
        })); } catch (_) {}
    }, 240);
    syncingCCTVTwinViews = false;
}

function resetCCTVTwinView(save = true, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    if (!CCTV_REFERENCE || !cctvLens || !cctvTwinCamera || !cctvPipTwinCamera) return;
    let saved = null;
    if (save) {
        try { localStorage.removeItem(CCTV_TWIN_VIEW_KEY); } catch (_) {}
    } else {
        try { saved = JSON.parse(localStorage.getItem(CCTV_TWIN_VIEW_KEY) || 'null'); } catch (_) {}
    }
    const normal = new THREE.Vector3(...(CCTV_REFERENCE.camera_normal || [0, 0, 1])).normalize();
    const view = CCTV_REFERENCE.view_camera || {};
    cctvLens.updateWorldMatrix(true, false);
    const lensPosition = cctvLens.getWorldPosition(new THREE.Vector3());
    const target = saved?.target?.length === 3
        ? new THREE.Vector3(...saved.target)
        : new THREE.Vector3(...CCTV_REFERENCE.camera_look_at);
    const position = saved?.offset?.length === 3
        ? target.clone().add(new THREE.Vector3(...saved.offset))
        : lensPosition.clone().addScaledVector(normal, -(view.backoff_m ?? 15))
            .add(new THREE.Vector3(0, view.elevation_m ?? 3.5, 0));
    const fov = Number.isFinite(saved?.fov)
        ? THREE.MathUtils.clamp(saved.fov, 42, 75) : (view.fov_deg ?? 60);
    restoringCCTVTwinView = true;
    [[cctvTwinCamera, cctvTwinControls], [cctvPipTwinCamera, cctvPipTwinControls]].forEach(([viewCamera, orbit]) => {
        viewCamera.position.copy(position);
        viewCamera.fov = fov;
        viewCamera.updateProjectionMatrix();
        if (orbit) {
            orbit.target.copy(target);
            orbit.update();
        } else viewCamera.lookAt(target);
    });
    restoringCCTVTwinView = false;
    if (save) {
        syncCCTVTwinViews(cctvTwinControls || cctvPipTwinControls);
    }
}

function zoomCCTVTwin(factor, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const orbit = cctvTwinControls || cctvPipTwinControls;
    if (!orbit) return;
    const offset = orbit.object.position.clone().sub(orbit.target).multiplyScalar(factor);
    const distance = THREE.MathUtils.clamp(offset.length(), orbit.minDistance, orbit.maxDistance);
    offset.setLength(distance);
    orbit.object.position.copy(orbit.target).add(offset);
    orbit.update();
    syncCCTVTwinViews(orbit);
}

function renderTwinView(renderer3d, camera3d, canvas) {
    if (!renderer3d || !camera3d || !cctvLens || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    const dpr = renderer3d.getPixelRatio();
    if (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr)) {
        renderer3d.setSize(rect.width, rect.height, false);
    }
    const orbit = camera3d === cctvTwinCamera ? cctvTwinControls : cctvPipTwinControls;
    if (orbit) orbit.update();
    camera3d.aspect = rect.width / rect.height;
    camera3d.updateProjectionMatrix();
    renderer3d.render(scene, camera3d);
}

function renderCCTVTwin() {
    const now = performance.now();
    if (now - lastCctvTwinRenderAt < 33) return;
    lastCctvTwinRenderAt = now;
    if (isCCTVModalOpen) {
        renderTwinView(cctvTwinRenderer, cctvTwinCamera, document.getElementById('cctv-twin-canvas'));
    }
    if (pipViewMode !== 'camera') {
        renderTwinView(cctvPipTwinRenderer, cctvPipTwinCamera, document.getElementById('cctv-pip-twin-canvas'));
    }
}

function applyCCTVReference(reference) {
    if (!reference || !reference.anchor_3d || !reference.camera_look_at) return;
    CCTV_REFERENCE = reference;
    CCTV_ANCHOR.set(...reference.anchor_3d);
    CCTV_LOOK_AT.set(...reference.camera_look_at);
    const [anchorX, anchorY, anchorZ] = reference.anchor_3d;
    const mapView = reference.map_view || {};
    const cctvOffset = mapView.cctv_offset || [0, 42, 35];
    const e40Offset = mapView.e40_offset || [0, 95, 75];
    CAMERA_PRESETS.cctv = {
        pos: [anchorX + cctvOffset[0], anchorY + cctvOffset[1], anchorZ + cctvOffset[2]],
        target: [anchorX, anchorY, anchorZ]
    };
    CAMERA_PRESETS.e40 = {
        pos: [anchorX + e40Offset[0], anchorY + e40Offset[1], anchorZ + e40Offset[2]],
        target: [anchorX, anchorY, anchorZ]
    };
    if (cctvGroup) {
        cctvGroup.position.copy(CCTV_ANCHOR);
        const cameraHead = cctvGroup.children[3];
        if (cameraHead && Number.isFinite(reference.camera_yaw_deg)) {
            cameraHead.rotation.y = THREE.MathUtils.degToRad(reference.camera_yaw_deg);
        }
    }
    [cctvTwinControls, cctvPipTwinControls].forEach(orbit => {
        if (!orbit) return;
        orbit.minDistance = reference.view_camera?.min_distance_m ?? 7;
        orbit.maxDistance = reference.view_camera?.max_distance_m ?? 120;
    });
    resetCCTVTwinView(false);
}

function applyPipViewMode() {
    const content = document.getElementById('cctv-pip-content');
    const button = document.getElementById('btn-cctv-pip-mode');
    if (!content) return;
    content.classList.remove('pip-dual', 'pip-camera-only', 'pip-twin-only');
    const cls = pipViewMode === 'camera' ? 'pip-camera-only' : (pipViewMode === 'twin' ? 'pip-twin-only' : 'pip-dual');
    content.classList.add(cls);
    if (button) {
        button.textContent = pipViewMode === 'dual' ? 'D' : (pipViewMode === 'camera' ? 'C' : '3D');
        button.title = `PiP: ${pipViewMode === 'dual' ? 'Vista Dual' : (pipViewMode === 'camera' ? 'Solo Camara' : 'Solo Gemelo')}. Pulsar para cambiar`;
    }
}

function cyclePipViewMode(event) {
    if (event) { event.stopPropagation(); event.preventDefault(); }
    pipViewMode = pipViewMode === 'dual' ? 'camera' : (pipViewMode === 'camera' ? 'twin' : 'dual');
    applyPipViewMode();
    renderCCTVTwin();
}

function captureCCTVFrame() {
    if (visionFramePending || !cctvStream || !ws || ws.readyState !== WebSocket.OPEN) return;
    const video = getActiveCCTVVideo();
    if (!video) return;
    const isImage = video.tagName === 'IMG';
    const frameWidth = isImage ? video.naturalWidth : video.videoWidth;
    const frameHeight = isImage ? video.naturalHeight : video.videoHeight;
    if ((isImage && !video.complete) || (!isImage && video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) || !frameWidth) return;
    if (!visionFrameCanvas) visionFrameCanvas = document.createElement('canvas');
    const scale = Math.min(1, 640 / frameWidth);
    visionFrameCanvas.width = Math.round(frameWidth * scale);
    visionFrameCanvas.height = Math.round(frameHeight * scale);
    visionFrameCanvas.getContext('2d', { alpha: false }).drawImage(video, 0, 0, visionFrameCanvas.width, visionFrameCanvas.height);
    visionFramePending = true;
    visionFrameTimeoutId = setTimeout(() => {
        visionFramePending = false;
        if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    }, 3500);
    try {
        ws.send(JSON.stringify({ type: 'FRAME_INFERENCE', image: visionFrameCanvas.toDataURL('image/jpeg', 0.70) }));
    } catch (err) {
        clearTimeout(visionFrameTimeoutId);
        visionFramePending = false;
    }
}

function getActiveCCTVVideo() {
    if (cctvStream?.kind === 'rtsp') {
        const image = document.getElementById(isCCTVModalOpen ? 'cctv-modal-network-image' : 'cctv-network-image');
        if (image?.complete && image.naturalWidth) return image;
        return document.getElementById('cctv-network-image');
    }
    const pipVideo = document.getElementById('cctv-video');
    const modalVideo = document.getElementById('cctv-modal-video');
    if (isCCTVModalOpen && modalVideo && modalVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && modalVideo.videoWidth) {
        return modalVideo;
    }
    if (pipVideo && pipVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && pipVideo.videoWidth) return pipVideo;
    return modalVideo && modalVideo.videoWidth ? modalVideo : pipVideo;
}

function containedVideoRect(width, height, videoWidth, videoHeight) {
    const ratio = videoWidth / Math.max(videoHeight, 1);
    let drawWidth = width;
    let drawHeight = drawWidth / ratio;
    if (drawHeight > height) {
        drawHeight = height;
        drawWidth = drawHeight * ratio;
    }
    return {
        x: (width - drawWidth) * 0.5,
        y: (height - drawHeight) * 0.5,
        width: drawWidth,
        height: drawHeight
    };
}

function syncVisionOverlayCanvas(canvas) {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
    }
}

function setupVisionOverlayResize() {
    const pairs = [
        ['cctv-video', 'cctv-yolo-canvas'],
        ['cctv-modal-video', 'cctv-modal-yolo-canvas']
    ];
    const syncAll = () => pairs.forEach(([, canvasId]) =>
        syncVisionOverlayCanvas(document.getElementById(canvasId))
    );
    if (window.ResizeObserver) {
        visionOverlayResizeObserver = new ResizeObserver(syncAll);
        pairs.forEach(([, canvasId]) => {
            const canvas = document.getElementById(canvasId);
            if (canvas && canvas.parentElement) visionOverlayResizeObserver.observe(canvas.parentElement);
        });
    }
    pairs.forEach(([videoId, canvasId]) => {
        const video = document.getElementById(videoId);
        if (video) video.addEventListener('loadedmetadata', () => syncVisionOverlayCanvas(document.getElementById(canvasId)));
    });
    window.addEventListener('resize', syncAll, { passive: true });
    syncAll();
}

function updatePipPreview() {
    if (!cctvStream) return;
    const now = performance.now();
    if (now - lastPipPaintAt < 33) return;
    const source = getActiveCCTVVideo();
    const canvas = document.getElementById('cctv-pip-preview');
    const sourceWidth = source?.tagName === 'IMG' ? source.naturalWidth : source?.videoWidth;
    const sourceHeight = source?.tagName === 'IMG' ? source.naturalHeight : source?.videoHeight;
    if (!source || !canvas || (!cctvStream || cctvStream.kind !== 'rtsp') && source.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !sourceWidth) return;
    lastPipPaintAt = now;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
    }
    const ctx = canvas.getContext('2d', { alpha: false });
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const drawRect = containedVideoRect(canvas.width, canvas.height, sourceWidth, sourceHeight);
    ctx.drawImage(source, drawRect.x, drawRect.y, drawRect.width, drawRect.height);
    canvas.style.display = 'block';
    if (cctvRtspTextureCanvas && cctvScreenMaterial?.map) cctvScreenMaterial.map.needsUpdate = true;
    const pipVideo = document.getElementById('cctv-video');
    if (pipVideo) pipVideo.style.display = 'none';
}

function setupLighting() {
    ambientLight = new THREE.AmbientLight(0x223344, 1.2);
    scene.add(ambientLight);

    hemiLight = new THREE.HemisphereLight(0xffffff, 0x111827, 0.6);
    scene.add(hemiLight);

    sunLight = new THREE.DirectionalLight(0xddeeff, 2.2);
    sunLight.position.set(350, 700, 450);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 2048;
    sunLight.shadow.mapSize.height = 2048;
    const d = 1500;
    sunLight.shadow.camera.left = -d;
    sunLight.shadow.camera.right = d;
    sunLight.shadow.camera.top = d;
    sunLight.shadow.camera.bottom = -d;
    sunLight.shadow.camera.near = 100;
    sunLight.shadow.camera.far = 3000;
    scene.add(sunLight);
}

function createTerrain() {
    const groundGeo = new THREE.PlaneGeometry(10000, 10000);
    const groundMat = new THREE.MeshStandardMaterial({
        color: 0x080b11,
        roughness: 0.95,
        metalness: 0.1
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.5;
    ground.receiveShadow = true;
    scene.add(ground);

    const grid = new THREE.GridHelper(6000, 120, 0x1e293b, 0x0f172a);
    grid.position.y = -0.4;
    scene.add(grid);
}

// ─── Carga de Red y Polígonos Exactos ───────────────────────────────
async function loadNetworkData() {
    try {
        const response = await fetch('paute_network_3d.json?v=20261117-building-baja2');
        networkData = await response.json();
        applyCCTVReference(networkData.cctv_reference);
        console.log('✓ Red exacta cargada:', networkData.metadata);

        buildRoadMeshes(networkData.edges);
        if (networkData.junctions) {
            buildJunctionMeshes(networkData.junctions);
        }
        buildExactOSMBuildings(networkData.buildings);
        buildPOIs(networkData.pois);
        buildStreetLights(networkData.edges);
        populatePOIsList(networkData.pois);
    } catch (e) {
        console.error('Error cargando red 3D:', e);
    }
}

// Carreteras con Calzadas de Asfalto, Aceras y Líneas Fluorescentes
function buildRoadMeshes(edges) {
    const roadMat = new THREE.MeshStandardMaterial({
        color: 0x18202c,
        roughness: 0.82,
        metalness: 0.18
    });

    const sidewalkMat = new THREE.MeshStandardMaterial({
        color: 0x283344,
        roughness: 0.9,
        metalness: 0.05
    });

    const centerLineMat = new THREE.MeshBasicMaterial({
        color: 0x00e5ff,
        opacity: 0.75,
        transparent: true
    });

    edges.forEach(edge => {
        edge.lanes.forEach(lane => {
            const pts = lane.points;
            if (pts.length < 2) return;

            const width = lane.width || 3.2;

            for (let i = 0; i < pts.length - 1; i++) {
                const p1 = new THREE.Vector3(pts[i][0], pts[i][1], pts[i][2]);
                const p2 = new THREE.Vector3(pts[i+1][0], pts[i+1][1], pts[i+1][2]);
                
                const dir = new THREE.Vector3().subVectors(p2, p1).normalize();
                const normal = new THREE.Vector3(-dir.z, 0, dir.x).multiplyScalar(width * 0.5);

                // Solapar suavemente 0.45m en los extremos para sellar juntas con intersecciones
                const extP1 = (i === 0) ? p1.clone().sub(dir.clone().multiplyScalar(0.45)) : p1;
                const extP2 = (i === pts.length - 2) ? p2.clone().add(dir.clone().multiplyScalar(0.45)) : p2;

                const v1 = new THREE.Vector3().addVectors(extP1, normal);
                const v2 = new THREE.Vector3().subVectors(extP1, normal);
                const v3 = new THREE.Vector3().addVectors(extP2, normal);
                const v4 = new THREE.Vector3().subVectors(extP2, normal);

                const quadGeo = new THREE.BufferGeometry();
                const verts = new Float32Array([
                    v1.x, v1.y, v1.z,  v2.x, v2.y, v2.z,  v3.x, v3.y, v3.z,
                    v2.x, v2.y, v2.z,  v4.x, v4.y, v4.z,  v3.x, v3.y, v3.z
                ]);
                quadGeo.setAttribute('position', new THREE.BufferAttribute(verts, 3));
                quadGeo.computeVertexNormals();

                const mesh = new THREE.Mesh(quadGeo, roadMat);
                mesh.receiveShadow = true;
                roadGroup.add(mesh);

                // Aceras en bordes
                const swWidth = 1.6;
                const swNormal = new THREE.Vector3(-dir.z, 0, dir.x).multiplyScalar(swWidth);
                const s1 = new THREE.Vector3().addVectors(v1, swNormal);
                const s2 = new THREE.Vector3().addVectors(v3, swNormal);
                s1.y = 0.22; s2.y = 0.22; v1.y = 0.22; v3.y = 0.22;

                const swGeo = new THREE.BufferGeometry();
                const swVerts = new Float32Array([
                    v1.x, v1.y, v1.z,  s1.x, s1.y, s1.z,  v3.x, v3.y, v3.z,
                    s1.x, s1.y, s1.z,  s2.x, s2.y, s2.z,  v3.x, v3.y, v3.z
                ]);
                swGeo.setAttribute('position', new THREE.BufferAttribute(swVerts, 3));
                swGeo.computeVertexNormals();
                const swMesh = new THREE.Mesh(swGeo, sidewalkMat);
                swMesh.receiveShadow = true;
                roadGroup.add(swMesh);
            }

            // Línea central fluorescente
            const curve = new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(p[0], 0.10, p[2])));
            const lineGeo = new THREE.TubeGeometry(curve, pts.length * 2, 0.12, 4, false);
            const lineMesh = new THREE.Mesh(lineGeo, centerLineMat);
            roadGroup.add(lineMesh);
        });
    });
}

// Intersecciones Viales Pavimentadas Oficiales SUMO (Polígonos Exactos de Unión sin Z-Fighting)
function buildJunctionMeshes(junctions) {
    if (!junctions || !junctions.length) return;

    const junctionMat = new THREE.MeshStandardMaterial({
        color: 0x18202c,
        roughness: 0.85,
        metalness: 0.15,
        side: THREE.DoubleSide,
        polygonOffset: true,
        polygonOffsetFactor: -1,
        polygonOffsetUnits: -1
    });

    const markMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.85,
        side: THREE.DoubleSide
    });

    junctions.forEach(j => {
        const pts = j.shape;
        if (!pts || pts.length < 3) return;

        try {
            const shape = new THREE.Shape();
            shape.moveTo(pts[0][0], pts[0][1]);
            for (let i = 1; i < pts.length; i++) {
                shape.lineTo(pts[i][0], pts[i][1]);
            }
            shape.closePath();

            const geom = new THREE.ShapeGeometry(shape);
            geom.rotateX(Math.PI / 2); // Rotar de plano XY al plano XZ del terreno

            const mesh = new THREE.Mesh(geom, junctionMat);
            // El polígono oficial SUMO cubre los extremos de carril y queda apenas
            // sobre la calzada para evitar z-fighting en sus bordes.
            mesh.position.y = 0.08;
            mesh.receiveShadow = true;
            mesh.userData = { id: j.id, type: j.type };
            roadGroup.add(mesh);

            // Marcas viales en el cruce de la Cámara (E40 ∩ Barzallo 2910139955)
            if (j.id === '2910139955' && j.centroid) {
                const cx = j.centroid[0];
                const cz = j.centroid[1];
                for (let k = -3; k <= 3; k++) {
                    const zebraGeo = new THREE.PlaneGeometry(0.6, 3.2);
                    zebraGeo.rotateX(Math.PI / 2);
                    const zebra = new THREE.Mesh(zebraGeo, markMat);
                    zebra.position.set(cx + k * 1.0, 0.035, cz - 3.8);
                    zebra.rotation.y = 0.38;
                    roadGroup.add(zebra);
                }
            }
        } catch (e) {
            // Ignorar polígonos degenerados si existieran
        }
    });
}

// Polígonos Reales de Edificios y Manzanas de OpenStreetMap
function buildExactOSMBuildings(buildings) {
    if (!buildings || !buildings.length) return;

    buildings.forEach(b => {
        const poly = b.polygon;
        if (!poly || poly.length < 3) return;

        try {
            const shape = new THREE.Shape();
            shape.moveTo(poly[0][0], poly[0][1]);
            for (let i = 1; i < poly.length; i++) {
                shape.lineTo(poly[i][0], poly[i][1]);
            }
            shape.closePath();

            const height = b.height || 8.0;
            const geom = new THREE.ExtrudeGeometry(shape, {
                depth: height,
                bevelEnabled: true,
                bevelThickness: 0.3,
                bevelSize: 0.2,
                bevelSegments: 1
            });
            geom.rotateX(Math.PI / 2);

            const colorHex = parseInt((b.color || "#263345").replace('#', '0x'));
            const mat = new THREE.MeshStandardMaterial({
                color: colorHex,
                roughness: 0.7,
                metalness: 0.06,
                emissive: colorHex,
                emissiveIntensity: 0.07,
                transparent: false,
                opacity: 1
            });

            const mesh = new THREE.Mesh(geom, mat);
            mesh.position.y = height;
            mesh.castShadow = true;
            mesh.receiveShadow = true;
            mesh.userData = { id: b.id, name: b.name, type: b.type };

            // Bordes luminosos en techos
            const edgesGeom = new THREE.EdgesGeometry(geom, 24);
            const lineMat = new THREE.LineBasicMaterial({
                color: colorHex,
                transparent: true,
                opacity: 0.8
            });
            const line = new THREE.LineSegments(edgesGeom, lineMat);
            mesh.add(line);

            buildingsGroup.add(mesh);
        } catch (err) {
            console.warn('Error extruyendo edificio OSM:', b.id, err);
        }
    });
}

// Puntos de Interés Oficiales (POIs) Georreferenciados
function buildPOIs(pois) {
    if (!pois) return;

    pois.forEach(poi => {
        const pGroup = new THREE.Group();
        pGroup.position.set(poi.coords_3d[0], 0, poi.coords_3d[1]);
        pGroup.userData = poi;

        const colorHex = parseInt(poi.color.replace('#', '0x'));

        // Pilar holográfico
        const cylGeo = new THREE.CylinderGeometry(4.5, 4.5, 40, 16, 1, true);
        const cylMat = new THREE.MeshBasicMaterial({
            color: colorHex,
            transparent: true,
            opacity: 0.38,
            side: THREE.DoubleSide
        });
        const cyl = new THREE.Mesh(cylGeo, cylMat);
        cyl.position.y = 20;
        pGroup.add(cyl);

        // Anillo de suelo pulsante
        const ringGeo = new THREE.RingGeometry(3.5, 8, 24);
        const ringMat = new THREE.MeshBasicMaterial({
            color: colorHex,
            transparent: true,
            opacity: 0.85,
            side: THREE.DoubleSide
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.rotation.x = -Math.PI / 2;
        ring.position.y = 0.4;
        pGroup.add(ring);

        // Esfera luminosa en la cima
        const sphereGeo = new THREE.SphereGeometry(3.5, 16, 16);
        const sphereMat = new THREE.MeshStandardMaterial({
            color: colorHex,
            emissive: colorHex,
            emissiveIntensity: 0.85
        });
        const sphere = new THREE.Mesh(sphereGeo, sphereMat);
        sphere.position.y = 40;
        pGroup.add(sphere);

        // Letrero 3D flotante con texto del POI
        const labelSprite = createTextSprite(`${poi.icon} ${poi.title}`, colorHex);
        labelSprite.position.set(0, 48, 0);
        pGroup.add(labelSprite);

        // Luz de baliza
        const light = new THREE.PointLight(colorHex, 2.5, 95);
        light.position.y = 32;
        pGroup.add(light);

        poisGroup.add(pGroup);
    });
}

// Crear Sprite 2D de Texto para POIs
function createTextSprite(text, colorHex) {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = 'rgba(10, 15, 25, 0.85)';
    ctx.roundRect(10, 10, 492, 108, 24);
    ctx.fill();

    ctx.strokeStyle = `#${colorHex.toString(16).padStart(6, '0')}`;
    ctx.lineWidth = 4;
    ctx.stroke();

    ctx.font = 'bold 36px Outfit, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 256, 64);

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(38, 9.5, 1);
    return sprite;
}

// Farolas y Alumbrado Público
function buildStreetLights(edges) {
    const lampMat = new THREE.MeshBasicMaterial({ color: 0xffe082 });
    const postMat = new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.8 });

    edges.forEach((edge, eIdx) => {
        if (eIdx % 3 !== 0) return;
        edge.lanes.forEach(lane => {
            const pts = lane.points;
            if (pts.length < 2) return;

            for (let i = 0; i < pts.length; i += 4) {
                const pt = pts[i];
                const post = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.25, 9, 6), postMat);
                post.position.set(pt[0] + 3.0, 4.5, pt[2]);
                post.castShadow = true;

                const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.4, 8, 8), lampMat);
                bulb.position.set(0, 4.5, -0.6);
                post.add(bulb);

                streetlightsGroup.add(post);
            }
        });
    });
}

function populatePOIsList(pois) {
    const container = document.getElementById('pois-container');
    if (!container || !pois) return;

    container.innerHTML = '';
    pois.forEach(poi => {
        const item = document.createElement('div');
        item.className = 'poi-item';
        item.innerHTML = `
            <div class="poi-left">
                <span class="poi-icon">${poi.icon}</span>
                <div class="poi-details">
                    <span class="poi-title">${poi.title}</span>
                    <span class="poi-sub">${poi.subtitle}</span>
                </div>
            </div>
            <span class="poi-fly-btn">Volar ↗</span>
        `;
        item.onclick = () => flyToCoords(poi.coords_3d[0], poi.coords_3d[1], poi.title);
        container.appendChild(item);
    });
}

// ─── Renderizado de Vehículos Detallados en 3D ───────────────────────
function updateVehicles(vehiclesData) {
    const presentIds = new Set();

    vehiclesData.forEach(v => {
        presentIds.add(v.id);
        const style = FLEET_STYLES[v.type] || FLEET_STYLES.car;

        if (!vehiclesMap.has(v.id)) {
            const vGroup = new THREE.Group();

            const bW = style.bodyDim[0];
            const bH = style.bodyDim[1];
            const bL = style.bodyDim[2];

            // 1. Chasis Base
            const bodyGeo = new THREE.BoxGeometry(bW, bH, bL);
            const bodyMat = new THREE.MeshStandardMaterial({
                color: style.color,
                roughness: 0.35,
                metalness: 0.65
            });
            const body = new THREE.Mesh(bodyGeo, bodyMat);
            body.position.y = bH / 2;
            body.castShadow = true;
            vGroup.add(body);

            // 2. Cabina Superior
            if (style.hasCabin && style.cabinDim) {
                const cW = style.cabinDim[0];
                const cH = style.cabinDim[1];
                const cL = style.cabinDim[2];
                const cabinGeo = new THREE.BoxGeometry(cW, cH, cL);
                const cabinMat = new THREE.MeshStandardMaterial({
                    color: 0x111827,
                    roughness: 0.1,
                    metalness: 0.9,
                    transparent: true,
                    opacity: 0.85
                });
                const cabin = new THREE.Mesh(cabinGeo, cabinMat);
                cabin.position.set(0, bH + cH / 2 - 0.1, -0.2);
                cabin.castShadow = true;
                vGroup.add(cabin);
            }

            // 3. Ruedas
            const wheelMat = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.9 });
            const wheelRadius = bH * 0.28;
            const wheelThick = 0.28;
            const wGeo = new THREE.CylinderGeometry(wheelRadius, wheelRadius, wheelThick, 10);
            wGeo.rotateZ(Math.PI / 2);

            const wheelOffsets = [
                [-bW/2, wheelRadius, bL*0.3],
                [bW/2, wheelRadius, bL*0.3],
                [-bW/2, wheelRadius, -bL*0.3],
                [bW/2, wheelRadius, -bL*0.3]
            ];
            wheelOffsets.forEach(pos => {
                const wheel = new THREE.Mesh(wGeo, wheelMat);
                wheel.position.set(pos[0], pos[1], pos[2]);
                wheel.castShadow = true;
                vGroup.add(wheel);
            });

            // 4. Faros y Conos de Luz
            const headMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
            const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.25, 0.15), headMat);
            const h2 = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.25, 0.15), headMat);
            h1.position.set(-bW*0.36, bH*0.5, bL*0.5);
            h2.position.set(bW*0.36, bH*0.5, bL*0.5);
            vGroup.add(h1);
            vGroup.add(h2);

            const spotLight = new THREE.SpotLight(0xffffff, 2.0, 35, Math.PI / 7, 0.4);
            spotLight.position.set(0, bH*0.6, bL*0.5);
            const targetObj = new THREE.Object3D();
            targetObj.position.set(0, 0, bL*0.5 + 25);
            vGroup.add(targetObj);
            spotLight.target = targetObj;
            vGroup.add(spotLight);

            // 5. Luces Traseras
            const tailMat = new THREE.MeshBasicMaterial({ color: 0xff1744 });
            const t1 = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.2, 0.15), tailMat);
            const t2 = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.2, 0.15), tailMat);
            t1.position.set(-bW*0.36, bH*0.5, -bL*0.5);
            t2.position.set(bW*0.36, bH*0.5, -bL*0.5);
            vGroup.add(t1);
            vGroup.add(t2);

            vGroup.position.set(v.x, v.y, v.z);
            vGroup.rotation.y = THREE.MathUtils.degToRad(v.heading);
            vGroup.userData = { id: v.id, data: v };

            vehiclesGroup.add(vGroup);

            // Estela de luz
            const trailPositions = new Float32Array(30 * 3);
            for (let i = 0; i < 30 * 3; i += 3) {
                trailPositions[i] = v.x;
                trailPositions[i+1] = 0.45;
                trailPositions[i+2] = v.z;
            }
            const trailGeo = new THREE.BufferGeometry();
            trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPositions, 3));
            const trailMat = new THREE.LineBasicMaterial({
                color: style.color,
                transparent: true,
                opacity: 0.55,
                linewidth: 2
            });
            const trailLine = new THREE.Line(trailGeo, trailMat);
            trailsGroup.add(trailLine);

            vehiclesMap.set(v.id, {
                group: vGroup,
                trail: trailLine,
                trailHistory: [],
                spotLight: spotLight,
                data: v
            });
        }

        const vehObj = vehiclesMap.get(v.id);
        const group = vehObj.group;
        vehObj.data = v;

        group.position.x += (v.x - group.position.x) * 0.45;
        group.position.z += (v.z - group.position.z) * 0.45;
        group.position.y = v.y;
        group.rotation.y = THREE.MathUtils.degToRad(v.heading);

        if (vehObj.spotLight) {
            vehObj.spotLight.intensity = (currentDayTime === 'night' || currentDayTime === 'dusk') ? 2.5 : 0.0;
        }

        if (layersState.trails && vehObj.trail) {
            vehObj.trailHistory.unshift([group.position.x, 0.45, group.position.z]);
            if (vehObj.trailHistory.length > 25) vehObj.trailHistory.pop();

            const posAttr = vehObj.trail.geometry.attributes.position;
            for (let i = 0; i < vehObj.trailHistory.length; i++) {
                posAttr.setXYZ(i, vehObj.trailHistory[i][0], vehObj.trailHistory[i][1], vehObj.trailHistory[i][2]);
            }
            posAttr.needsUpdate = true;
        }

        if (inspectedVehicleId === v.id) {
            updateInspectorUI(v);
        }

        if (isFollowMode && v.id === followedVehicleId) {
            updateFollowCamera(group, v);
        }
    });

    for (const [id, vehObj] of vehiclesMap.entries()) {
        if (!presentIds.has(id)) {
            vehiclesGroup.remove(vehObj.group);
            trailsGroup.remove(vehObj.trail);
            vehiclesMap.delete(id);
            if (followedVehicleId === id) {
                followedVehicleId = null;
                isFollowMode = false;
                document.getElementById('btn-cam-follow').classList.remove('active');
            }
        }
    }
}

// ─── Inspector de Vehículo & Telemetría CO2 ──────────────────────────
function selectVehicleForInspection(vehData) {
    inspectedVehicleId = vehData.id;
    const inspector = document.getElementById('vehicle-inspector');
    inspector.style.display = 'block';
    updateInspectorUI(vehData);
}

function updateInspectorUI(v) {
    document.getElementById('insp-type-badge').innerText = v.type.toUpperCase();
    document.getElementById('insp-name').innerText = v.name || 'Vehículo Urbano';
    document.getElementById('insp-id').innerText = v.id;
    document.getElementById('insp-fuel').innerText = v.fuel || 'Gasolina';
    document.getElementById('insp-speed').innerText = `${v.speed_kmh || (v.speed*3.6).toFixed(1)} km/h`;
    document.getElementById('insp-co2').innerText = `${v.co2_gps || 0.0} g/s`;
    document.getElementById('insp-cons').innerText = `${v.consumption_l || 7.5} l/100km`;
    document.getElementById('insp-co2-accum').innerText = `${v.co2_accum_g || 0.0} g`;
    document.getElementById('insp-heading').innerText = `${Math.round(v.heading)}°`;
}

function closeInspector() {
    inspectedVehicleId = null;
    document.getElementById('vehicle-inspector').style.display = 'none';
}

function followInspectedVehicle() {
    if (inspectedVehicleId && vehiclesMap.has(inspectedVehicleId)) {
        followedVehicleId = inspectedVehicleId;
        isFollowMode = true;
        document.getElementById('btn-cam-follow').classList.add('active');
    }
}

// ─── Modo Persecución de Cámara ─────────────────────────────────────
function updateFollowCamera(targetGroup, v) {
    const angle = targetGroup.rotation.y;
    const distance = 28;
    const height = 11;

    const camX = targetGroup.position.x - Math.sin(angle) * distance;
    const camZ = targetGroup.position.z - Math.cos(angle) * distance;
    const camY = targetGroup.position.y + height;

    camera.position.set(camX, camY, camZ);
    controls.target.copy(targetGroup.position);
}

function toggleFollowMode() {
    isFollowMode = !isFollowMode;
    const btn = document.getElementById('btn-cam-follow');

    if (isFollowMode) {
        const firstKey = vehiclesMap.keys().next().value;
        if (firstKey) {
            followedVehicleId = firstKey;
            inspectedVehicleId = firstKey;
            selectVehicleForInspection(vehiclesMap.get(firstKey).data);
            btn.classList.add('active');
        } else {
            isFollowMode = false;
        }
    } else {
        followedVehicleId = null;
        btn.classList.remove('active');
        setCameraView('overview');
    }
}

// ─── Tiempos del Día / Ciclo Circadiano ──────────────────────────────
function setTimeOfDay(timeKey) {
    currentDayTime = timeKey;
    document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    if (timeKey === 'dawn') {
        scene.background.setHex(0x3a2e39);
        scene.fog.color.setHex(0x3a2e39);
        ambientLight.color.setHex(0xffcc80);
        ambientLight.intensity = 1.6;
        sunLight.color.setHex(0xffaa5e);
        sunLight.intensity = 2.4;
        sunLight.position.set(400, 250, 400);
    } else if (timeKey === 'day') {
        scene.background.setHex(0x60a5fa);
        scene.fog.color.setHex(0x60a5fa);
        ambientLight.color.setHex(0xffffff);
        ambientLight.intensity = 1.9;
        sunLight.color.setHex(0xffffff);
        sunLight.intensity = 3.8;
        sunLight.position.set(200, 800, 300);
    } else if (timeKey === 'dusk') {
        scene.background.setHex(0x28182b);
        scene.fog.color.setHex(0x28182b);
        ambientLight.color.setHex(0xff7043);
        ambientLight.intensity = 1.4;
        sunLight.color.setHex(0xff5722);
        sunLight.intensity = 2.0;
        sunLight.position.set(-400, 200, 300);
    } else if (timeKey === 'night') {
        scene.background.setHex(0x0a0d14);
        scene.fog.color.setHex(0x0a0d14);
        ambientLight.color.setHex(0x223344);
        ambientLight.intensity = 1.2;
        sunLight.color.setHex(0x8899bb);
        sunLight.intensity = 1.4;
        sunLight.position.set(300, 600, 400);
    }
}

// ─── Toggles de Capas & Polígonos ───────────────────────────────────
function toggleLayer(layerKey) {
    layersState[layerKey] = !layersState[layerKey];
    if (layerKey === 'buildings') buildingsGroup.visible = layersState.buildings;
    if (layerKey === 'pois') poisGroup.visible = layersState.pois;
    if (layerKey === 'streetlights') streetlightsGroup.visible = layersState.streetlights;
    if (layerKey === 'trails') trailsGroup.visible = layersState.trails;
}

// ─── Transiciones de Cámara Cinemáticas ─────────────────────────────
function setCameraView(presetKey) {
    isFollowMode = false;
    followedVehicleId = null;
    document.getElementById('btn-cam-follow').classList.remove('active');

    document.querySelectorAll('.hud-controls .ctrl-btn').forEach(b => b.classList.remove('active'));
    const btnId = `btn-cam-${presetKey}`;
    if (document.getElementById(btnId)) document.getElementById(btnId).classList.add('active');

    const preset = CAMERA_PRESETS[presetKey];
    if (!preset) return;

    flyToCoords(preset.target[0], preset.target[2], null, preset.pos[1], preset.pos[2] - preset.target[2]);
}

function flyToCoords(targetX, targetZ, title, altitude = 150, offsetZ = 130) {
    isFollowMode = false;
    followedVehicleId = null;

    new TWEEN.Tween(camera.position)
        .to({ x: targetX, y: altitude, z: targetZ + offsetZ }, 1400)
        .easing(TWEEN.Easing.Cubic.Out)
        .start();

    new TWEEN.Tween(controls.target)
        .to({ x: targetX, y: 0, z: targetZ }, 1400)
        .easing(TWEEN.Easing.Cubic.Out)
        .start();
}

// ─── Vuelo Libre con Teclado (WASD / Flechas) ───────────────────────
function setupKeyboardFlight() {
    window.addEventListener('keydown', (e) => {
        const k = e.key.toLowerCase();
        if (k === 'w' || k === 'arrowup') keyState.w = true;
        if (k === 's' || k === 'arrowdown') keyState.s = true;
        if (k === 'a' || k === 'arrowleft') keyState.a = true;
        if (k === 'd' || k === 'arrowright') keyState.d = true;
        if (k === 'q') keyState.q = true;
        if (k === 'e') keyState.e = true;
    });

    window.addEventListener('keyup', (e) => {
        const k = e.key.toLowerCase();
        if (k === 'w' || k === 'arrowup') keyState.w = false;
        if (k === 's' || k === 'arrowdown') keyState.s = false;
        if (k === 'a' || k === 'arrowleft') keyState.a = false;
        if (k === 'd' || k === 'arrowright') keyState.d = false;
        if (k === 'q') keyState.q = false;
        if (k === 'e') keyState.e = false;
    });
}

function updateKeyboardFlight() {
    if (!keyState.w && !keyState.s && !keyState.a && !keyState.d && !keyState.q && !keyState.e) return;

    isFollowMode = false;
    const moveSpeed = 6.5;

    const forward = new THREE.Vector3();
    camera.getWorldDirection(forward);
    forward.y = 0;
    forward.normalize();

    const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();

    if (keyState.w) { camera.position.addScaledVector(forward, moveSpeed); controls.target.addScaledVector(forward, moveSpeed); }
    if (keyState.s) { camera.position.addScaledVector(forward, -moveSpeed); controls.target.addScaledVector(forward, -moveSpeed); }
    if (keyState.d) { camera.position.addScaledVector(right, -moveSpeed); controls.target.addScaledVector(right, -moveSpeed); }
    if (keyState.a) { camera.position.addScaledVector(right, moveSpeed); controls.target.addScaledVector(right, moveSpeed); }
    if (keyState.q) { camera.position.y += moveSpeed * 0.7; controls.target.y += moveSpeed * 0.7; }
    if (keyState.e && camera.position.y > 15) { camera.position.y -= moveSpeed * 0.7; controls.target.y -= moveSpeed * 0.7; }
}

// ─── Raycasting para Clic en Vehículos y POIs ───────────────────────
function setupRaycasting() {
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    window.addEventListener('click', (e) => {
        if (e.target.closest('.glass-panel')) return;

        mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
        mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;

        raycaster.setFromCamera(mouse, camera);

        const vIntersects = raycaster.intersectObjects(vehiclesGroup.children, true);
        if (vIntersects.length > 0) {
            let hitGroup = vIntersects[0].object;
            while (hitGroup.parent && hitGroup.parent !== vehiclesGroup) {
                hitGroup = hitGroup.parent;
            }
            if (hitGroup && hitGroup.userData && hitGroup.userData.data) {
                selectVehicleForInspection(hitGroup.userData.data);
                return;
            }
        }

        const poiIntersects = raycaster.intersectObjects(poisGroup.children, true);
        if (poiIntersects.length > 0) {
            let poiGroup = poiIntersects[0].object;
            while (poiGroup.parent && poiGroup.parent !== poisGroup) {
                poiGroup = poiGroup.parent;
            }
            if (poiGroup && poiGroup.userData) {
                if (poiGroup.userData.id === 'poi_cctv_barzallo') {
                    expandCCTVModal();
                }
                flyToCoords(poiGroup.userData.coords_3d[0], poiGroup.userData.coords_3d[1], poiGroup.userData.title);
                return;
            }
        }

        if (cctvGroup) {
            const cctvIntersects = raycaster.intersectObjects(cctvGroup.children, true);
            if (cctvIntersects.length > 0) {
                expandCCTVModal();
                return;
            }
        }
    });
}

// ─── Conexión WebSocket ─────────────────────────────────────────────
function connectWebSocket() {
    const loc = window.location;
    const wsUrl = (loc.protocol === 'https:' ? 'wss://' : 'ws://') + loc.host + '/ws/telemetry';

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('✓ WebSocket conectado con la Sombra Digital de Paute');
        document.getElementById('connection-indicator').classList.add('live');
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'TELEMETRY_UPDATE') {
                updateTelemetryUI(data);
                updateVehicles(data.vehicles);
                updateVisionUI(data.vision_stats);
            } else if (data.type === 'FRAME_INFERENCE_RESULT') {
                clearTimeout(visionFrameTimeoutId);
                visionFramePending = false;
                drawVisionDetections(data);
                updateVisionUI(data.counts);
            } else if (data.type === 'FRAME_INFERENCE_SKIPPED') {
                clearTimeout(visionFrameTimeoutId);
                visionFramePending = false;
            }
        } catch (e) {
            console.error('Error parseando telemetría:', e);
        }
    };

    ws.onclose = () => {
        clearTimeout(visionFrameTimeoutId);
        visionFramePending = false;
        document.getElementById('connection-indicator').classList.remove('live');
        setTimeout(connectWebSocket, 2000);
    };
}

function updateVisionUI(stats) {
    if (!stats) return;
    const fields = {
        'cnt-total': stats.total, 'cnt-flow': Number(stats.flow_per_min || 0).toFixed(1),
        'cnt-co2': Number(stats.co2_detected_kg || 0).toFixed(3),
        'cnt-sube': stats.sube, 'cnt-baja': stats.baja,
        'cnt-motos': stats.motos, 'cnt-sedanes': stats.sedanes,
        'cnt-camionetas': stats.camionetas, 'cnt-buses': stats.buses,
        'cnt-camiones': stats.camiones, 'cnt-trailers': stats.trailers,
        'modal-cnt-total': stats.total, 'modal-cnt-flow': `${Number(stats.flow_per_min || 0).toFixed(1)} veh/min`,
        'modal-cnt-sube': stats.sube, 'modal-cnt-baja': stats.baja,
        'modal-cnt-co2': `${Number(stats.co2_detected_kg || 0).toFixed(3)} kg`,
        'modal-cnt-motos': stats.motos, 'modal-cnt-sedanes': stats.sedanes,
        'modal-cnt-camionetas': stats.camionetas, 'modal-cnt-buses': stats.buses,
        'modal-cnt-camiones': stats.camiones, 'modal-cnt-trailers': stats.trailers
    };
    Object.entries(fields).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value !== undefined) el.textContent = value;
    });
    const pipBadge = document.getElementById('pip-flow-badge');
    if (pipBadge) pipBadge.textContent = `SUBE ${stats.sube || 0} | BAJA ${stats.baja || 0} | TOTAL ${stats.total || 0}`;
}

function drawVisionDetections(result) {
    const countX = result.lines?.count_x ?? 0.52;
    const hystLeft = result.lines?.zone_left ?? 0.44;
    const hystRight = result.lines?.zone_right ?? 0.60;
    const crossLeft = result.lines?.left ?? 0.48;
    const crossRight = result.lines?.right ?? 0.55;
    const roiXMin = result.roi?.x_min ?? 0.08;
    const roiXMax = result.roi?.x_max ?? 0.95;
    const roiMin = result.roi?.y_min ?? 0.22;
    const roiMax = result.roi?.y_max ?? 0.92;
    ['cctv-yolo-canvas', 'cctv-modal-yolo-canvas'].forEach(id => {
        const canvas = document.getElementById(id);
        const video = cctvStream?.kind === 'rtsp'
            ? document.getElementById(id === 'cctv-yolo-canvas' ? 'cctv-network-image' : 'cctv-modal-network-image')
            : document.getElementById(id === 'cctv-yolo-canvas' ? 'cctv-video' : 'cctv-modal-video');
        const videoWidth = video?.tagName === 'IMG' ? video.naturalWidth : video?.videoWidth;
        const videoHeight = video?.tagName === 'IMG' ? video.naturalHeight : video?.videoHeight;
        if (!canvas || !video || !videoWidth || !videoHeight) return;
        syncVisionOverlayCanvas(canvas);
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const ctx = canvas.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, rect.width, rect.height);
        const content = containedVideoRect(rect.width, rect.height, videoWidth, videoHeight);

        // Diagnostic roadway ROI, hysteresis band and crossing thresholds.
        const roiTop = content.y + content.height * roiMin;
        const roiBottom = content.y + content.height * roiMax;
        const roiLeft = content.x + content.width * roiXMin;
        const roiRight = content.x + content.width * roiXMax;
        ctx.fillStyle = 'rgba(0, 255, 130, 0.07)';
        ctx.fillRect(roiLeft, roiTop, roiRight - roiLeft, roiBottom - roiTop);
        ctx.strokeStyle = 'rgba(0, 255, 130, 0.85)';
        ctx.lineWidth = 2;
        ctx.strokeRect(roiLeft, roiTop, roiRight - roiLeft, roiBottom - roiTop);
        ctx.setLineDash([6, 5]);
        [hystLeft, hystRight].forEach(xNorm => {
            const x = content.x + content.width * xNorm;
            ctx.strokeStyle = 'rgba(255, 213, 79, 0.72)';
            ctx.beginPath(); ctx.moveTo(x, roiTop); ctx.lineTo(x, roiBottom); ctx.stroke();
        });
        ctx.setLineDash([2, 4]);
        [crossLeft, crossRight].forEach(xNorm => {
            const x = content.x + content.width * xNorm;
            ctx.strokeStyle = 'rgba(255, 152, 0, 0.8)';
            ctx.beginPath(); ctx.moveTo(x, roiTop); ctx.lineTo(x, roiBottom); ctx.stroke();
        });
        ctx.setLineDash([]);
        const centerX = content.x + content.width * countX;
        ctx.strokeStyle = '#ffca28'; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(centerX, roiTop); ctx.lineTo(centerX, roiBottom); ctx.stroke();

        (result.detections || []).forEach(detection => {
            const [x1, y1, x2, y2] = detection.bbox;
            const left = content.x + x1 * content.width;
            const top = content.y + y1 * content.height;
            const boxWidth = (x2 - x1) * content.width;
            const boxHeight = (y2 - y1) * content.height;
            const parked = detection.state === 'ESTACIONADO';
            const counted = detection.state === 'CONTADO';
            const color = parked ? '#b0a77a' : (counted ? '#69f0ae' : '#00e5ff');
            ctx.strokeStyle = color;
            ctx.lineWidth = parked ? 2 : 3;
            ctx.strokeRect(left, top, boxWidth, boxHeight);
            ctx.fillStyle = color;
            ctx.font = 'bold 13px sans-serif';
            const status = parked ? ' ESTACIONADO' : '';
            ctx.fillText(`${detection.vtype} ${Math.round(detection.conf * 100)}%${status}`, left, Math.max(content.y + 16, top - 5));
        });
    });
}

function updateTelemetryUI(data) {
    if (!data.metrics) return;
    const m = data.metrics;

    document.getElementById('kpi-active').innerText = m.active_vehicles || 0;
    document.getElementById('kpi-speed').innerHTML = `${m.avg_speed_kmh || 0} <small>km/h</small>`;
    document.getElementById('kpi-co2-accum').innerHTML = `${m.total_co2_kg || 0} <small>kg</small>`;
    document.getElementById('kpi-co2-rate').innerHTML = `${m.co2_rate_kgh || 0} <small>kg/h</small>`;
    document.getElementById('kpi-market-status').innerText = m.market_density || 'Normal';
    document.getElementById('kpi-market-count').innerText = `${m.market_veh_count || 0} vehículos en radio`;
    document.getElementById('kpi-teleport').innerText = `${m.teleport_count || 0} (Evitados)`;

    // Actualizar telemetría de la esquina de la Cámara USB (Barzallo ∩ Interoceánica)
    const barzalloCount = m.barzallo_cam_count !== undefined ? m.barzallo_cam_count : (
        data.vehicles ? data.vehicles.filter(v => Math.hypot(v.x - (-72.0), v.z - (-205.0)) < 130.0).length : 0
    );
    const zCountEl = document.getElementById('cctv-zone-count');
    const zFricEl = document.getElementById('cctv-zone-friction');
    if (zCountEl) zCountEl.innerText = barzalloCount;
    if (zFricEl) {
        if (barzalloCount < 5) {
            zFricEl.innerText = "Fluido";
            zFricEl.className = "stat-v success";
        } else if (barzalloCount < 12) {
            zFricEl.innerText = "Moderado";
            zFricEl.className = "stat-v highlight";
        } else {
            zFricEl.innerText = "Congestión";
            zFricEl.className = "stat-v warning";
        }
    }

    // Actualizar reloj de la cámara
    const clockEl = document.getElementById('cctv-hud-clock');
    if (clockEl) {
        const now = new Date();
        clockEl.innerText = now.toTimeString().split(' ')[0] + '.' + String(Math.floor(now.getMilliseconds() / 100)).padStart(1, '0');
    }
}

// ─── Bucle de Animación a 60 FPS ────────────────────────────────────
function animate() {
    requestAnimationFrame(animate);

    TWEEN.update();
    controls.update();
    updateKeyboardFlight();

    // Rotar anillos holográficos de los POIs
    poisGroup.children.forEach(poi => {
        if (poi.children[1]) poi.children[1].rotation.z += 0.015;
    });

    // Parpadeo suave del LED de grabación de la cámara
    if (cctvGroup && cctvGroup.children[3] && cctvGroup.children[3].children[3]) {
        const led = cctvGroup.children[3].children[3];
        const pulse = 0.5 + 0.5 * Math.sin(Date.now() * 0.005);
        led.material.opacity = pulse;
    }

    // Posicionar la ventana pequeña sobre la esquina de Interoceánica y Barzallo en el mapa

    renderer.render(scene, camera);
    renderCCTVTwin();
    updatePipPreview();
    captureCCTVFrame();
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

// =====================================================================
// SISTEMA DE CÁMARA USB EN VIVO (ESQUINA INTEROCEÁNICA ∩ JOSÉ MIGUEL BARZALLO)
// =====================================================================

function buildCCTVMount() {
    cctvGroup = new THREE.Group();
    // Coordenadas milimétricas exactas en la esquina real de Av. Interoceánica (E40) y José Miguel Barzallo
    cctvGroup.position.copy(CCTV_ANCHOR);

    const metalMat = new THREE.MeshStandardMaterial({
        color: 0x334155,
        metalness: 0.85,
        roughness: 0.25
    });
    const whiteMat = new THREE.MeshStandardMaterial({
        color: 0xf8fafc,
        metalness: 0.3,
        roughness: 0.35
    });
    const lensMat = new THREE.MeshBasicMaterial({ color: 0x00e5ff });
    const recMat = new THREE.MeshBasicMaterial({ color: 0xff1744, transparent: true, opacity: 1.0 });

    // 1. Pedestal de anclaje en el suelo
    const baseGeo = new THREE.CylinderGeometry(0.8, 1.1, 0.8, 14);
    const base = new THREE.Mesh(baseGeo, metalMat);
    base.position.y = 0.4;
    cctvGroup.add(base);

    // 2. Poste vertical (9.5 metros)
    const poleGeo = new THREE.CylinderGeometry(0.24, 0.3, 9.5, 12);
    const pole = new THREE.Mesh(poleGeo, metalMat);
    pole.position.y = 4.75;
    cctvGroup.add(pole);

    // 3. Brazo horizontal orientado hacia la calzada de José Miguel Barzallo
    const armGeo = new THREE.CylinderGeometry(0.12, 0.12, 3.8, 8);
    armGeo.rotateZ(Math.PI / 2);
    const arm = new THREE.Mesh(armGeo, metalMat);
    arm.position.set(-1.4, 9.3, 0.6);
    arm.rotation.y = THREE.MathUtils.degToRad(-45);
    cctvGroup.add(arm);

    // 4. Cuerpo de la Cámara CCTV con Orientación Transversal Fidedigna
    const camHead = new THREE.Group();
    camHead.position.set(-2.8, 9.2, 1.4);
    camHead.rotation.y = THREE.MathUtils.degToRad(CCTV_REFERENCE?.camera_yaw_deg ?? 15.23);
    camHead.rotation.x = THREE.MathUtils.degToRad(22);  // Inclinada hacia el paso de vehículos

    // Caja de cámara
    const bodyGeo = new THREE.BoxGeometry(0.75, 0.65, 1.6);
    const camBody = new THREE.Mesh(bodyGeo, whiteMat);
    camHead.add(camBody);

    // Parasol superior
    const shieldGeo = new THREE.BoxGeometry(0.85, 0.1, 1.7);
    const shield = new THREE.Mesh(shieldGeo, metalMat);
    shield.position.set(0, 0.38, 0);
    camHead.add(shield);

    // Lente frontal
    const lensGeo = new THREE.CylinderGeometry(0.24, 0.24, 0.35, 16);
    lensGeo.rotateX(Math.PI / 2);
    const lens = new THREE.Mesh(lensGeo, lensMat);
    lens.position.set(0, 0, 0.88);
    camHead.add(lens);
    cctvLens = lens;

    // LED de grabación (REC)
    const ledGeo = new THREE.SphereGeometry(0.09, 8, 8);
    const led = new THREE.Mesh(ledGeo, recMat);
    led.position.set(0.24, 0.22, 0.82);
    camHead.add(led);

    cctvGroup.add(camHead);

    // 5. Mini pantalla 3D en el poste con textura de video
    const screenGeo = new THREE.PlaneGeometry(3.2, 2.1);
    cctvScreenMaterial = new THREE.MeshBasicMaterial({
        color: 0x00e5ff,
        side: THREE.DoubleSide
    });
    const screenMesh = new THREE.Mesh(screenGeo, cctvScreenMaterial);
    screenMesh.position.set(-1.2, 6.8, 0.8);
    screenMesh.rotation.y = THREE.MathUtils.degToRad(135);
    cctvGroup.add(screenMesh);

    // 6. Rótulo flotante interactivo
    const labelSprite = createTextSprite("📹 CÁMARA VIAL BARZALLO • E40", 0x00e5ff);
    labelSprite.position.set(0, 11.5, 0);
    cctvGroup.add(labelSprite);

    // 7. Luz de vigilancia
    const cctvLight = new THREE.PointLight(0x00e5ff, 2.0, 35);
    cctvLight.position.set(-2.8, 9.2, 1.4);
    cctvGroup.add(cctvLight);

    cctvGroup.userData = { isCCTV: true };
    scene.add(cctvGroup);
}

// Posicionamiento de la ventana pequeña 2D proyectada directamente sobre la esquina 3D
async function initWebcamSystem() {
    setupCCTVFallbackCanvas('cctv-fallback-canvas');
    setupCCTVFallbackCanvas('cctv-modal-canvas');
    setupCCTVFallbackCanvas('cctv-pip-preview');
    startCCTVFallbackSimulation();

    // Enumerar dispositivos de video disponibles
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        navigator.mediaDevices.enumerateDevices()
            .then(populateCameraDevices)
            .catch(err => console.log('Error enumerando dispositivos:', err));

        navigator.mediaDevices.addEventListener('devicechange', () => {
            navigator.mediaDevices.enumerateDevices()
                .then(populateCameraDevices)
                .catch(() => {});
        });
    }

    // Intentar conexión inicial
    try {
        connectRTSPCamera();
    } catch (e) {
        // Esperará el clic del usuario en el botón "Activar Cámara USB"
    }
}

// Solicitar acceso a la cámara USB física
function connectRTSPCamera() {
    const images = [document.getElementById('cctv-network-image'), document.getElementById('cctv-modal-network-image')];
    if (images.some(image => !image)) return;
    cctvStream = { kind: 'rtsp' };
    ['cctv-video', 'cctv-modal-video'].forEach(id => {
        const video = document.getElementById(id);
        if (video) video.style.display = 'none';
    });
    images.forEach(image => {
        image.style.display = 'none';
        image.onload = () => {
            image.style.display = 'block';
            const prompt = document.getElementById('cctv-prompt-overlay');
            if (prompt) prompt.style.display = 'none';
        };
        image.onerror = () => {
            image.style.display = 'none';
            const prompt = document.getElementById('cctv-prompt-overlay');
            if (prompt) prompt.style.display = 'flex';
        };
        image.src = `/api/camera/stream?ts=${Date.now()}`;
    });
    const preview = document.getElementById('cctv-pip-preview');
    if (preview && cctvScreenMaterial) {
        cctvRtspTextureCanvas = preview;
        cctvScreenMaterial.map = new THREE.CanvasTexture(preview);
        cctvScreenMaterial.map.colorSpace = THREE.SRGBColorSpace;
        cctvScreenMaterial.needsUpdate = true;
    }
}

async function configureEZVIZCamera(event) {
    event.preventDefault();
    const ip = document.getElementById('ezviz-ip').value.trim();
    const username = document.getElementById('ezviz-user').value.trim();
    const codeInput = document.getElementById('ezviz-code');
    const status = document.getElementById('ezviz-connection-status');
    const button = event.currentTarget.querySelector('button[type="submit"]');

    button.disabled = true;
    status.textContent = 'Configurando cámara...';
    try {
        const response = await fetch('/api/camera/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip, username, password: codeInput.value })
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || 'No se pudo configurar la cámara.');
        }

        codeInput.value = '';
        status.textContent = 'Conectando al video...';
        connectRTSPCamera();
    } catch (error) {
        status.textContent = `Error de conexión: ${error.message}`;
    } finally {
        button.disabled = false;
    }
}

async function requestWebcamAccess(deviceId = null) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.warn('getUserMedia no soportado en este navegador.');
        return;
    }

    try {
        if (cctvStream?.getTracks) {
            cctvStream.getTracks().forEach(t => t.stop());
            cctvStream = null;
        }

        const constraints = {
            video: deviceId ? { deviceId: { exact: deviceId } } : {
                width: { ideal: 1920 },
                height: { ideal: 1080 }
            },
            audio: false
        };

        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        cctvStream = stream;

        const videoPip = document.getElementById('cctv-video');
        const videoModal = document.getElementById('cctv-modal-video');
        const promptOverlay = document.getElementById('cctv-prompt-overlay');

        // Un solo decodificador activo evita que la c?mara USB quede negra en el PiP.
        const activeVideo = isCCTVModalOpen ? videoModal : videoPip;
        const idleVideo = isCCTVModalOpen ? videoPip : videoModal;
        [document.getElementById('cctv-network-image'), document.getElementById('cctv-modal-network-image')]
            .forEach(image => { if (image) image.style.display = 'none'; });
        if (idleVideo) {
            idleVideo.pause();
            idleVideo.srcObject = null;
            idleVideo.style.display = 'none';
        }
        if (activeVideo) {
            activeVideo.srcObject = stream;
            activeVideo.style.display = 'block';
            activeVideo.play().catch(() => {});
        }

        if (promptOverlay) promptOverlay.style.display = 'none';

        const c1 = document.getElementById('cctv-fallback-canvas');
        const c2 = document.getElementById('cctv-modal-canvas');
        if (c1) c1.style.display = 'none';
        if (c2) c2.style.display = 'none';

        // Mapear textura de video en el monitor 3D
        if (cctvScreenMaterial && (activeVideo || videoPip)) {
            const videoTexture = new THREE.VideoTexture(activeVideo || videoPip);
            cctvScreenMaterial.map = videoTexture;
            cctvScreenMaterial.needsUpdate = true;
        }

        navigator.mediaDevices.enumerateDevices().then(populateCameraDevices);

    } catch (err) {
        console.warn('Acceso a cámara USB esperando permiso o acción del usuario:', err);
        const promptOverlay = document.getElementById('cctv-prompt-overlay');
        if (promptOverlay) promptOverlay.style.display = 'flex';
        startCCTVFallbackSimulation();
    }
}

function populateCameraDevices(devices) {
    const select = document.getElementById('cctv-device-select');
    if (!select) return;

    const videoInputs = devices.filter(d => d.kind === 'videoinput');
    select.innerHTML = '';

    if (videoInputs.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.innerText = 'Cámara USB Predeterminada';
        select.appendChild(opt);
        return;
    }

    videoInputs.forEach((dev, idx) => {
        const opt = document.createElement('option');
        opt.value = dev.deviceId;
        opt.innerText = dev.label || `Cámara USB ${idx + 1}`;
        select.appendChild(opt);
    });
}

function switchCameraDevice(deviceId) {
    if (deviceId) {
        requestWebcamAccess(deviceId);
    }
}

// Clics y Apertura en Pantalla Agrandada
function handleCCTVPipClick(e) {
    if (e.target.closest('#cctv-prompt-overlay') || e.target.closest('#btn-cctv-expand')
        || e.target.closest('#cctv-pip-twin-pane')) return;
    expandCCTVModal();
}

function expandCCTVModal(e) {
    if (e) e.stopPropagation();
    isCCTVModalOpen = true;
    const modal = document.getElementById('cctv-modal-backdrop');
    if (modal) {
        modal.classList.add('active');
    }

    const videoPip = document.getElementById('cctv-video');
    const videoModal = document.getElementById('cctv-modal-video');
    if (videoPip && videoModal && cctvStream?.getTracks) {
        videoPip.pause();
        videoPip.srcObject = null;
        videoModal.srcObject = cctvStream;
        videoModal.play().catch(() => {});
    }
}

function closeCCTVModal(e) {
    if (e) e.stopPropagation();
    isCCTVModalOpen = false;
    const modal = document.getElementById('cctv-modal-backdrop');
    if (modal) {
        modal.classList.remove('active');
    }
    const videoPip = document.getElementById('cctv-video');
    const videoModal = document.getElementById('cctv-modal-video');
    if (videoModal && videoPip && cctvStream?.getTracks) {
        videoModal.pause();
        videoModal.srcObject = null;
        videoPip.srcObject = cctvStream;
        videoPip.play().catch(() => {});
    }
}

function toggleMirrorDualLayout() {
    mirrorDualLayout = !mirrorDualLayout;
    const body = document.getElementById('cctv-modal-body');
    if (body) body.classList.toggle('single-view', !mirrorDualLayout);
    const button = document.getElementById('btn-toggle-mirror-mode');
    if (button) button.textContent = mirrorDualLayout ? '🌓 Modo Espejo Dual' : '🌓 Ver Gemelo 3D';
}

function toggleFullScreenCamera() {
    const container = document.getElementById('cctv-modal-card');
    if (!container) return;
    if (!document.fullscreenElement) {
        container.requestFullscreen().catch(err => console.log('Fullscreen error:', err));
    } else {
        document.exitFullscreen().catch(err => console.log('Exit fullscreen error:', err));
    }
}

function flyToCCTVIntersection() {
    closeCCTVModal();
    setCameraView('cctv');
}

function focusCCTVCamera() {
    setCameraView('cctv');
}

// Patrón visual de Standby / Sensor mientras se activa la cámara USB
function setupCCTVFallbackCanvas(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    canvas.width = 640;
    canvas.height = 360;
}

function startCCTVFallbackSimulation() {
    if (cctvFallbackAnimationId) return;

    function renderFrame() {
        if (cctvStream) {
            cctvFallbackAnimationId = null;
            return;
        }

        ['cctv-fallback-canvas', 'cctv-modal-canvas'].forEach(id => {
            const canvas = document.getElementById(id);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            canvas.style.display = 'block';

            // Fondo de sensor nocturno
            ctx.fillStyle = '#060a12';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Rejilla de sensor vial
            ctx.strokeStyle = 'rgba(0, 229, 255, 0.08)';
            ctx.lineWidth = 1;
            for (let x = 0; x < canvas.width; x += 40) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, canvas.height);
                ctx.stroke();
            }
            for (let y = 0; y < canvas.height; y += 40) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvas.width, y);
                ctx.stroke();
            }

            // Mira y cuadrantes de detección vehicular
            const cx = canvas.width / 2;
            const cy = canvas.height / 2;
            ctx.strokeStyle = 'rgba(0, 229, 255, 0.35)';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(cx - 80, cy - 50, 160, 100);

            // Líneas de mira en esquinas
            ctx.strokeStyle = '#00e5ff';
            ctx.beginPath();
            ctx.moveTo(cx - 80, cy - 30); ctx.lineTo(cx - 80, cy - 50); ctx.lineTo(cx - 60, cy - 50);
            ctx.moveTo(cx + 80, cy - 30); ctx.lineTo(cx + 80, cy - 50); ctx.lineTo(cx + 60, cy - 50);
            ctx.moveTo(cx - 80, cy + 30); ctx.lineTo(cx - 80, cy + 50); ctx.lineTo(cx - 60, cy + 50);
            ctx.moveTo(cx + 80, cy + 30); ctx.lineTo(cx + 80, cy + 50); ctx.lineTo(cx + 60, cy + 50);
            ctx.stroke();

            // Línea de barrido de radar
            const scanY = (Date.now() * 0.12) % canvas.height;
            ctx.fillStyle = 'rgba(0, 229, 255, 0.06)';
            ctx.fillRect(0, scanY - 15, canvas.width, 30);
            ctx.strokeStyle = 'rgba(0, 229, 255, 0.4)';
            ctx.beginPath();
            ctx.moveTo(0, scanY);
            ctx.lineTo(canvas.width, scanY);
            ctx.stroke();

            // Texto de telemetría y aviso
            ctx.fillStyle = '#00e5ff';
            ctx.font = 'bold 13px "JetBrains Mono", monospace';
            ctx.fillText('CAM_01: AV. INTEROCEANICA ∩ J.M. BARZALLO', 18, 28);

            const now = new Date();
            ctx.fillStyle = '#94a3b8';
            ctx.font = '11px "JetBrains Mono", monospace';
            ctx.fillText(`STANDBY • EN ESPERA DE TRANSMISIÓN USB • ${now.toTimeString().split(' ')[0]}`, 18, 50);

            ctx.fillStyle = '#f8fafc';
            ctx.font = 'bold 14px Outfit, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('CÁMARA USB CONECTADA', cx, cy - 10);
            ctx.fillStyle = '#00e5ff';
            ctx.font = '12px Outfit, sans-serif';
            ctx.fillText('Haz clic en la ventana para activar la transmisión en vivo', cx, cy + 15);
            ctx.textAlign = 'left';
        });

        cctvFallbackAnimationId = requestAnimationFrame(renderFrame);
    }

    cctvFallbackAnimationId = requestAnimationFrame(renderFrame);
}

// Cerrar con tecla Escape
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isCCTVModalOpen) {
        closeCCTVModal();
    }
});
