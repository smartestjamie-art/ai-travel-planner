<script setup lang="ts">
import { ref } from "vue";

import type { Itinerary } from "./types";
import History from "./views/History.vue";
import Home from "./views/Home.vue";
import Result from "./views/Result.vue";

const currentView = ref<"home" | "result" | "history">("home");
const latestItinerary = ref<Itinerary | null>(null);

function handleGenerated(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}

function openTrip(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}

function updateCurrentItinerary(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}
</script>

<template>
  <div class="app-shell">
    <div class="app-shell__glow app-shell__glow--left"></div>
    <div class="app-shell__glow app-shell__glow--right"></div>

    <header class="hero">
      <div class="hero__badge">Trip Planner Demo</div>
      <h1 class="hero__title">Smart Travel Assistant</h1>

      <div class="hero__tabs">
        <button
          :class="['hero__tab', { 'hero__tab--active': currentView === 'home' }]"
          @click="currentView = 'home'"
        >
          Plan
        </button>
        <button
          :class="[
            'hero__tab',
            { 'hero__tab--active': currentView === 'result' },
            { 'hero__tab--disabled': !latestItinerary }
          ]"
          :disabled="!latestItinerary"
          @click="currentView = 'result'"
        >
          Result
        </button>
        <button
          :class="['hero__tab', { 'hero__tab--active': currentView === 'history' }]"
          @click="currentView = 'history'"
        >
          History
        </button>
      </div>
    </header>

    <main class="page-content">
      <Home
        v-if="currentView === 'home'"
        @generated="handleGenerated"
      />
      <Result
        v-else-if="currentView === 'result'"
        :itinerary="latestItinerary"
        @back-home="currentView = 'home'"
        @view-history="currentView = 'history'"
        @updated="updateCurrentItinerary"
      />
      <History
        v-else
        :active="currentView === 'history'"
        @open-trip="openTrip"
      />
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  min-width: 320px;
  font-family: "Georgia", "PingFang SC", "Microsoft YaHei", serif;
  background:
    radial-gradient(ellipse at top left, rgba(180, 155, 100, 0.18), transparent 40%),
    radial-gradient(ellipse at bottom right, rgba(100, 140, 90, 0.14), transparent 40%),
    linear-gradient(180deg, #f5f0e6 0%, #ede8db 100%);
  color: #2d2a24;
}

:global(*) {
  box-sizing: border-box;
}

.app-shell {
  position: relative;
  min-height: 100vh;
  padding: 40px 24px 64px;
  overflow: hidden;
}

.app-shell__glow {
  position: absolute;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  filter: blur(32px);
  opacity: 0.4;
  pointer-events: none;
}

.app-shell__glow--left {
  top: -110px;
  left: -90px;
  background: rgba(160, 120, 60, 0.35);
}

.app-shell__glow--right {
  right: -80px;
  bottom: 120px;
  background: rgba(80, 120, 70, 0.25);
}

.hero {
  position: relative;
  z-index: 1;
  max-width: 1280px;
  margin: 0 auto 28px;
  text-align: center;
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  padding: 8px 16px;
  border-radius: 999px;
  background: rgba(255, 250, 240, 0.85);
  color: #5a7a40;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.06em;
  font-family: "Segoe UI", sans-serif;
  box-shadow: 0 8px 24px rgba(80, 100, 60, 0.12);
}

.hero__title {
  margin: 18px 0 0;
  color: #f5f0e4;
  font-size: 48px;
  line-height: 1.1;
  font-family: "Georgia", serif;
  font-weight: 700;
  letter-spacing: -0.01em;
  text-shadow: 0 2px 12px rgba(30, 50, 20, 0.3);
}

.hero::before {
  content: "";
  position: absolute;
  inset: -24px 0 auto;
  height: 220px;
  z-index: -1;
  border-radius: 36px;
  background: linear-gradient(135deg, #3a5c2a 0%, #4a6e38 50%, #5e8048 100%);
  box-shadow: 0 32px 80px rgba(40, 70, 30, 0.28);
}

.hero__tabs {
  display: inline-flex;
  gap: 10px;
  margin-top: 24px;
  padding: 8px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(10px);
}

.hero__tab {
  border: none;
  border-radius: 12px;
  padding: 10px 20px;
  background: transparent;
  color: rgba(240, 235, 220, 0.9);
  font-size: 14px;
  font-weight: 600;
  font-family: "Segoe UI", sans-serif;
  cursor: pointer;
  transition: background 0.2s;
}

.hero__tab--active {
  background: rgba(255, 250, 240, 0.92);
  color: #4a6b30;
}

.hero__tab--disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.page-content {
  position: relative;
  z-index: 1;
  max-width: 1280px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .app-shell {
    padding: 24px 16px 40px;
  }

  .hero__title {
    font-size: 34px;
  }

  .hero::before {
    inset: -20px 0 auto;
    height: 230px;
  }
}
</style>
