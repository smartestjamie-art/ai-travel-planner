<script setup lang="ts">
import { message } from "ant-design-vue";
import { onMounted, ref, watch } from "vue";

import { deleteTrip, getTripDetail, listTrips } from "../services/api";
import type { Itinerary, TripSummaryItem } from "../types";

const props = defineProps<{
  active: boolean;
}>();

const emit = defineEmits<{
  openTrip: [itinerary: Itinerary];
}>();

const loading = ref(false);
const items = ref<TripSummaryItem[]>([]);
const deletingTripId = ref("");

async function loadTrips() {
  loading.value = true;
  try {
    const response = await listTrips();
    items.value = response.items;
  } catch (error) {
    console.error(error);
    message.error("Failed to load trip history.");
  } finally {
    loading.value = false;
  }
}

async function openTrip(tripId: string) {
  try {
    const response = await getTripDetail(tripId);
    emit("openTrip", response.itinerary);
    message.success("Loaded saved itinerary.");
  } catch (error) {
    console.error(error);
    message.error("Failed to load trip details.");
  }
}

async function removeTrip(tripId: string) {
  const confirmed = window.confirm("Are you sure you want to delete this saved trip? This cannot be undone.");
  if (!confirmed) {
    return;
  }

  deletingTripId.value = tripId;
  try {
    await deleteTrip(tripId);
    items.value = items.value.filter((item) => item.trip_id !== tripId);
    message.success("Trip deleted.");
  } catch (error) {
    console.error(error);
    message.error("Failed to delete trip.");
  } finally {
    deletingTripId.value = "";
  }
}

onMounted(() => {
  if (props.active) {
    void loadTrips();
  }
});

watch(
  () => props.active,
  (active) => {
    if (active) {
      void loadTrips();
    }
  }
);
</script>

<template>
  <section class="history-page">
    <div class="history-header">
      <div>
        <h2>Trip History</h2>
        <p>This shows summaries of itineraries already saved to the backend database.</p>
      </div>
      <button class="refresh-button" @click="loadTrips">Refresh List</button>
    </div>

    <div v-if="loading" class="history-state">Loading trip history...</div>
    <div v-else-if="items.length === 0" class="history-state">No saved trips yet.</div>

    <div v-else class="history-grid">
      <article
        v-for="item in items"
        :key="item.trip_id"
        class="history-card"
      >
        <div class="history-card__destination">{{ item.destination }}</div>
        <div class="history-card__trip-id">{{ item.trip_id }}</div>
        <p class="history-card__summary">{{ item.summary }}</p>
        <div class="history-card__time">
          Updated: {{ item.updated_at || "Not recorded" }}
        </div>
        <div class="history-card__actions">
          <button class="history-card__button" @click="openTrip(item.trip_id)">
            View Details
          </button>
          <button
            class="history-card__button history-card__button--danger"
            :disabled="deletingTripId === item.trip_id"
            @click="removeTrip(item.trip_id)"
          >
            {{ deletingTripId === item.trip_id ? "Deleting..." : "Delete Trip" }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.history-page {
  display: grid;
  gap: 18px;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  padding: 24px;
  border-radius: 20px;
  background: rgba(255, 252, 246, 0.96);
  box-shadow: 0 12px 40px rgba(100, 76, 50, 0.09);
  border: 1px solid rgba(180, 155, 110, 0.15);
}

.history-header h2 {
  margin: 0 0 8px;
  font-size: 28px;
  color: #3a3020;
  font-family: "Georgia", serif;
}

.history-header p {
  margin: 0;
  color: #7c6f5e;
  font-family: "Segoe UI", sans-serif;
}

.refresh-button,
.history-card__button {
  border: none;
  border-radius: 14px;
  padding: 12px 18px;
  background: linear-gradient(135deg, #5a7a40 0%, #6e8f52 100%);
  color: #f5f0e4;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
  cursor: pointer;
  transition: opacity 0.2s;
}

.history-card__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.history-card__button--danger {
  background: rgba(180, 70, 50, 0.1);
  color: #a83820;
}

.history-card__button:disabled {
  opacity: 0.65;
  cursor: wait;
}

.history-state {
  padding: 28px;
  border-radius: 20px;
  background: rgba(255, 252, 246, 0.96);
  box-shadow: 0 12px 40px rgba(100, 76, 50, 0.09);
  border: 1px solid rgba(180, 155, 110, 0.15);
  color: #9c8c7a;
  text-align: center;
  font-family: "Segoe UI", sans-serif;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 18px;
}

.history-card {
  display: grid;
  gap: 12px;
  padding: 22px;
  border-radius: 20px;
  background: rgba(255, 252, 246, 0.96);
  box-shadow: 0 12px 40px rgba(100, 76, 50, 0.09);
  border: 1px solid rgba(180, 155, 110, 0.15);
}

.history-card__destination {
  font-size: 26px;
  font-weight: 800;
  color: #3a5c2a;
  font-family: "Georgia", serif;
}

.history-card__trip-id {
  color: #a89880;
  font-size: 13px;
  word-break: break-all;
  font-family: "Segoe UI", sans-serif;
}

.history-card__summary {
  margin: 0;
  color: #4a4036;
  line-height: 1.75;
  font-family: "Segoe UI", sans-serif;
}

.history-card__time {
  color: #9c8c7a;
  font-size: 13px;
  font-family: "Segoe UI", sans-serif;
}
</style>
