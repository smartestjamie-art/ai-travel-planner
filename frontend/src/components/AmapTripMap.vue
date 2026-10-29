<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

interface TripMapPoint {
  key: string;
  dayIndex: number;
  date: string;
  theme: string;
  name: string;
  address: string;
  latitude: number | null | undefined;
  longitude: number | null | undefined;
  poiId: string | null | undefined;
  imageUrl?: string | null;
  description: string;
}

const props = defineProps<{
  points: TripMapPoint[];
}>();

declare global {
  interface Window {
    AMap?: any;
  }
}

const mapContainer = ref<HTMLDivElement | null>(null);
const mapInstance = ref<any>(null);
const markerList = ref<any[]>([]);
const routeLine = ref<any>(null);
const loadError = ref("");

const amapKey = import.meta.env.VITE_AMAP_JS_KEY;

const validPoints = computed(() =>
  props.points.filter(
    (point) => point.longitude != null && point.latitude != null
  )
);

function clearOverlays() {
  if (!mapInstance.value) {
    return;
  }

  markerList.value.forEach((marker) => {
    mapInstance.value.remove(marker);
  });
  markerList.value = [];

  if (routeLine.value) {
    mapInstance.value.remove(routeLine.value);
    routeLine.value = null;
  }
}

function drawPoints(map: any): { overlays: any[]; line: any } {
  const overlays: any[] = [];
  let line: any = null;

  const sorted = [...validPoints.value].sort((a, b) => a.dayIndex - b.dayIndex);
  const bounds: [number, number][] = [];
  const routePath: [number, number][] = [];

  sorted.forEach((point) => {
    const position: [number, number] = [point.longitude as number, point.latitude as number];
    bounds.push(position);
    routePath.push(position);

    const marker = new window.AMap.Marker({
      position,
      title: point.name,
      offset: new window.AMap.Pixel(-12, -28),
      content: `
        <div style="position:relative;display:flex;flex-direction:column;align-items:center;">
          <div style="font-size:22px;line-height:1;">🚩</div>
          <div style="
            margin-top:2px;
            padding:2px 7px;
            border-radius:999px;
            background:linear-gradient(135deg,#6d82de,#8a67cf);
            color:#fff;
            font-size:11px;
            font-weight:700;
            white-space:nowrap;
            box-shadow:0 2px 6px rgba(0,0,0,0.18);
          ">D${point.dayIndex}</div>
        </div>
      `,
    });

    const imageHtml = point.imageUrl
      ? `<img src="${point.imageUrl}" alt="${point.name}" style="width:100%;height:100%;object-fit:cover;border-radius:8px;" />`
      : `<div style="width:100%;height:100%;display:grid;place-items:center;border-radius:8px;background:linear-gradient(135deg,#e8edff,#f0e8ff);color:#8b8fad;font-size:10px;">No image available</div>`;

    const bubble = new window.AMap.Marker({
      position,
      offset: new window.AMap.Pixel(14, -46),
      content: `
        <div style="
          position:relative;
          width:110px;
          background:#fff;
          border-radius:10px;
          box-shadow:0 3px 12px rgba(0,0,0,0.12);
          overflow:hidden;
          font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        ">
          <div style="width:110px;height:72px;overflow:hidden;background:#eef3ff;">
            ${imageHtml}
          </div>
          <div style="padding:5px 8px 6px;">
            <div style="font-size:11px;font-weight:600;color:#2d3748;line-height:1.3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${point.name}</div>
          </div>
          <div style="
            position:absolute;
            left:-5px;
            top:30px;
            width:0;
            height:0;
            border-top:5px solid transparent;
            border-bottom:5px solid transparent;
            border-right:5px solid #fff;
            filter:drop-shadow(-2px 0 2px rgba(0,0,0,0.06));
          "></div>
        </div>
      `,
      zIndex: 100,
    });

    const infoWindow = new window.AMap.InfoWindow({
      offset: new window.AMap.Pixel(0, -32),
      content: `
        <div style="max-width:240px;padding:4px 2px;line-height:1.7;">
          <strong>${point.name}</strong><br/>
          <span>Day ${point.dayIndex} · ${point.theme}</span><br/>
          <span>${point.address}</span>
        </div>
      `,
    });

    marker.on("click", () => {
      infoWindow.open(map, position);
    });

    map.add(marker);
    map.add(bubble);
    overlays.push(marker);
    overlays.push(bubble);
  });

  if (routePath.length >= 2) {
    line = new window.AMap.Polyline({
      path: routePath,
      strokeColor: "#6d82de",
      strokeWeight: 3,
      strokeOpacity: 0.8,
      strokeStyle: "dashed",
      strokeDasharray: [10, 6],
      lineJoin: "round",
      lineCap: "round",
      showDir: true,
      dirColor: "#6d82de",
      dirSize: 8,
      borderWeight: 1,
      borderColor: "rgba(109,130,222,0.25)",
      zIndex: 50,
    });
    map.add(line);
  }

  if (bounds.length === 1) {
    map.setZoomAndCenter(13, bounds[0]);
  } else if (bounds.length > 1) {
    map.setFitView(overlays, false, [60, 60, 60, 60]);
  }

  return { overlays, line };
}

function renderMarkers() {
  if (!window.AMap || !mapInstance.value) {
    return;
  }

  clearOverlays();
  const { overlays, line } = drawPoints(mapInstance.value);
  markerList.value = overlays;
  routeLine.value = line;
}

const MAP_STYLE = {
  zoom: 11,
  resizeEnable: true,
  viewMode: "2D",
  mapStyle: "amap://styles/whitesmoke",
  animateEnable: false,
};

const zoomOpen = ref(false);
const zoomContainer = ref<HTMLDivElement | null>(null);
let zoomMap: any = null;

async function openZoom() {
  if (!window.AMap || zoomOpen.value) {
    return;
  }
  zoomOpen.value = true;
  await nextTick();
  if (!zoomContainer.value) {
    return;
  }
  zoomMap = new window.AMap.Map(zoomContainer.value, MAP_STYLE);
  await nextTick();
  zoomMap.resize();
  drawPoints(zoomMap);
}

function closeZoom() {
  zoomOpen.value = false;
  if (zoomMap) {
    zoomMap.destroy();
    zoomMap = null;
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && zoomOpen.value) {
    closeZoom();
  }
}

function ensureMapScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.AMap) {
      resolve();
      return;
    }

    const existingScript = document.querySelector<HTMLScriptElement>(
      'script[data-amap-loader="true"]'
    );

    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error("Failed to load the Amap script.")), {
        once: true,
      });
      return;
    }

    const securityCode = import.meta.env.VITE_AMAP_SECURITY_CODE;
    if (securityCode) {
      (window as any)._AMapSecurityConfig = { securityJsCode: securityCode };
    }

    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${amapKey}`;
    script.async = true;
    script.defer = true;
    script.dataset.amapLoader = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load the Amap script."));
    document.head.appendChild(script);
  });
}

async function initMap() {
  if (!amapKey) {
    loadError.value = "The frontend Amap JavaScript key is not configured.";
    return;
  }

  if (!mapContainer.value) {
    return;
  }

  try {
    loadError.value = "";
    await ensureMapScript();

    if (!window.AMap) {
      loadError.value = "Failed to initialize the Amap object.";
      return;
    }

    mapInstance.value = new window.AMap.Map(mapContainer.value, MAP_STYLE);

    // Right after the container mounts, the browser may not have finished layout
    // measurement yet, so the map can get the wrong size and its coordinates end up
    // offset. Wait one frame, then force a resize and reposition.
    await nextTick();
    mapInstance.value.resize();

    renderMarkers();
  } catch (error) {
    console.error(error);
    loadError.value = "Failed to load the map. Please check the frontend Amap key or your network connection.";
  }
}

onMounted(() => {
  void initMap();
  window.addEventListener("keydown", onKeydown);
});

watch(validPoints, () => {
  if (mapInstance.value) {
    renderMarkers();
  }
  if (zoomMap) {
    zoomMap.clearMap();
    drawPoints(zoomMap);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
  closeZoom();
  clearOverlays();
  if (mapInstance.value) {
    mapInstance.value.destroy();
    mapInstance.value = null;
  }
});
</script>

<template>
  <div class="trip-map">
    <div v-if="loadError" class="trip-map__placeholder">
      <strong>Map Not Available</strong>
      <span>{{ loadError }}</span>
    </div>
    <div v-else-if="validPoints.length === 0" class="trip-map__placeholder">
      <strong>No Points to Display</strong>
      <span>This itinerary doesn't have any usable coordinate data yet.</span>
    </div>
    <div v-else class="trip-map__stage">
      <div ref="mapContainer" class="trip-map__canvas"></div>
      <button
        type="button"
        class="trip-map__magnifier"
        title="Enlarge map"
        aria-label="Enlarge map"
        @click="openZoom"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <circle cx="10.5" cy="10.5" r="6.5" />
          <line x1="15.5" y1="15.5" x2="21" y2="21" />
          <line x1="10.5" y1="7.5" x2="10.5" y2="13.5" />
          <line x1="7.5" y1="10.5" x2="13.5" y2="10.5" />
        </svg>
      </button>
    </div>

    <Teleport to="body">
      <div v-if="zoomOpen" class="trip-map-zoom" @click.self="closeZoom">
        <div class="trip-map-zoom__panel">
          <div class="trip-map-zoom__bar">
            <strong>Route map</strong>
            <span>Scroll or pinch to zoom, drag to pan, Esc to close</span>
            <button type="button" class="trip-map-zoom__close" aria-label="Close" @click="closeZoom">×</button>
          </div>
          <div ref="zoomContainer" class="trip-map-zoom__canvas"></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.trip-map {
  height: calc(100% - 58px);
  min-height: 280px;
}

.trip-map__stage {
  position: relative;
  width: 100%;
  height: 100%;
}

.trip-map__magnifier {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.95);
  color: #5b6bd6;
  box-shadow: 0 2px 10px rgba(60, 70, 120, 0.25);
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.trip-map__magnifier:hover {
  transform: scale(1.08);
  box-shadow: 0 4px 14px rgba(60, 70, 120, 0.35);
}

.trip-map__canvas,
.trip-map__placeholder {
  width: 100%;
  height: 100%;
  min-height: 280px;
  border-radius: 20px;
}

.trip-map__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 20px;
  background:
    linear-gradient(135deg, rgba(129, 179, 255, 0.18), rgba(137, 108, 230, 0.15)),
    linear-gradient(45deg, rgba(255, 255, 255, 0.75), rgba(244, 247, 255, 0.9));
  color: #5b6474;
  text-align: center;
}

.trip-map-zoom {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(20, 24, 45, 0.55);
  backdrop-filter: blur(3px);
}

.trip-map-zoom__panel {
  display: flex;
  flex-direction: column;
  width: min(1200px, 100%);
  height: min(800px, 100%);
  overflow: hidden;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 20px 60px rgba(10, 15, 40, 0.45);
}

.trip-map-zoom__bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  color: #3b4256;
  border-bottom: 1px solid #eceff6;
}

.trip-map-zoom__bar span {
  flex: 1;
  color: #8b93a7;
  font-size: 13px;
}

.trip-map-zoom__close {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  background: #f1f3fa;
  color: #5b6474;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.trip-map-zoom__close:hover {
  background: #e4e8f6;
}

.trip-map-zoom__canvas {
  flex: 1;
  min-height: 0;
}

.trip-map__placeholder strong {
  font-size: 22px;
  color: #4b5563;
}

.trip-map__placeholder span {
  max-width: 360px;
  color: #7b8494;
  line-height: 1.7;
}
</style>
