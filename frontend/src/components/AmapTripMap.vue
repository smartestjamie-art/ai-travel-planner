<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

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
const loadError = ref("");

const amapKey = import.meta.env.VITE_AMAP_JS_KEY;

const validPoints = computed(() =>
  props.points.filter(
    (point) => point.longitude != null && point.latitude != null
  )
);

function clearMarkers() {
  if (!mapInstance.value) {
    return;
  }

  markerList.value.forEach((marker) => {
    mapInstance.value.remove(marker);
  });
  markerList.value = [];
}

function renderMarkers() {
  if (!window.AMap || !mapInstance.value) {
    return;
  }

  clearMarkers();

  const bounds: [number, number][] = [];

  validPoints.value.forEach((point) => {
    const position: [number, number] = [point.longitude as number, point.latitude as number];
    bounds.push(position);

    const marker = new window.AMap.Marker({
      position,
      title: point.name,
      label: {
        content: `<div style="padding:2px 6px;border-radius:999px;background:#6d82de;color:#fff;font-size:12px;">D${point.dayIndex}</div>`,
        direction: "top",
      },
    });

    const infoWindow = new window.AMap.InfoWindow({
      offset: new window.AMap.Pixel(0, -24),
      content: `
        <div style="max-width:240px;padding:4px 2px;line-height:1.7;">
          <strong>${point.name}</strong><br/>
          <span>第${point.dayIndex}天 · ${point.theme}</span><br/>
          <span>${point.address}</span>
        </div>
      `,
    });

    marker.on("click", () => {
      infoWindow.open(mapInstance.value, position);
    });

    mapInstance.value.add(marker);
    markerList.value.push(marker);
  });

  if (bounds.length === 1) {
    mapInstance.value.setZoomAndCenter(13, bounds[0]);
  } else if (bounds.length > 1) {
    mapInstance.value.setFitView(markerList.value, false, [40, 40, 40, 40]);
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
      existingScript.addEventListener("error", () => reject(new Error("高德地图脚本加载失败。")), {
        once: true,
      });
      return;
    }

    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${amapKey}`;
    script.async = true;
    script.defer = true;
    script.dataset.amapLoader = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("高德地图脚本加载失败。"));
    document.head.appendChild(script);
  });
}

async function initMap() {
  if (!amapKey) {
    loadError.value = "未配置前端高德 JavaScript Key。";
    return;
  }

  if (!mapContainer.value) {
    return;
  }

  try {
    loadError.value = "";
    await ensureMapScript();

    if (!window.AMap) {
      loadError.value = "高德地图对象初始化失败。";
      return;
    }

    mapInstance.value = new window.AMap.Map(mapContainer.value, {
      zoom: 11,
      resizeEnable: true,
      viewMode: "2D",
      mapStyle: "amap://styles/whitesmoke",
    });

    renderMarkers();
  } catch (error) {
    console.error(error);
    loadError.value = "地图加载失败，请检查前端高德 Key 或网络环境。";
  }
}

onMounted(() => {
  void initMap();
});

watch(validPoints, () => {
  if (mapInstance.value) {
    renderMarkers();
  }
});

onBeforeUnmount(() => {
  clearMarkers();
  if (mapInstance.value) {
    mapInstance.value.destroy();
    mapInstance.value = null;
  }
});
</script>

<template>
  <div class="trip-map">
    <div v-if="loadError" class="trip-map__placeholder">
      <strong>地图暂未启用</strong>
      <span>{{ loadError }}</span>
    </div>
    <div v-else-if="validPoints.length === 0" class="trip-map__placeholder">
      <strong>暂无可展示点位</strong>
      <span>当前 itinerary 里还没有可用的经纬度数据。</span>
    </div>
    <div v-else ref="mapContainer" class="trip-map__canvas"></div>
  </div>
</template>

<style scoped>
.trip-map {
  height: calc(100% - 58px);
  min-height: 280px;
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
