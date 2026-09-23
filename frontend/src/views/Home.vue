<script setup lang="ts">
import axios from "axios";
import { computed, reactive, ref } from "vue";
import { message } from "ant-design-vue";

import { generateTrip } from "../services/api";
import type { Itinerary, TripRequestPayload } from "../types";

const emit = defineEmits<{
  generated: [itinerary: Itinerary];
}>();

const preferenceOptions = [
  "Nature & Scenery",
  "Photography",
  "Food",
  "Old Towns",
  "Relaxation",
];

const dietaryOptions = [
  "Vegetarian",
  "Vegan",
  "Halal",
  "No Seafood",
  "No Pork",
  "Less Spicy",
  "No Cilantro",
  "Nut Allergy",
];

function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

const today = new Date();
const todayPlus2 = new Date(today);
todayPlus2.setDate(todayPlus2.getDate() + 2);

const formState = reactive({
  destination: "Dali",
  startDate: formatDate(today),
  endDate: formatDate(todayPlus2),
  travelers: 2,
  budget: 3200,
  hotelLevel: "Comfort",
  pace: "Relaxed",
  preferences: ["Nature & Scenery", "Photography", "Food"],
  dietaryPreferences: [],
  notes: "Would rather not get up too early, and would like a spot for watching the sunset.",
});

const isSubmitting = ref(false);

const dayCount = computed(() => {
  const start = new Date(formState.startDate);
  const end = new Date(formState.endDate);
  const diff = end.getTime() - start.getTime();
  return Number.isNaN(diff) ? 0 : Math.max(Math.floor(diff / 86400000) + 1, 0);
});

async function handleSubmit() {
  const payload: TripRequestPayload = {
    destination: formState.destination,
    start_date: formState.startDate,
    end_date: formState.endDate,
    travelers: formState.travelers,
    budget: formState.budget,
    preferences: formState.preferences,
    pace: formState.pace,
    dietary_preferences: formState.dietaryPreferences,
    hotel_level: formState.hotelLevel,
    special_notes: formState.notes,
  };

  isSubmitting.value = true;
  try {
    const itinerary = await generateTrip(payload);
    message.success("Itinerary generated successfully. Switching to the results page.");
    emit("generated", itinerary);
  } catch (error) {
    console.error(error);
    if (axios.isAxiosError(error)) {
      if (error.code === "ECONNABORTED") {
        message.error("Itinerary generation timed out; the model is responding slowly. Please try again later.");
      } else if (error.response) {
        message.error(`Failed to generate itinerary: backend returned ${error.response.status}.`);
      } else {
        message.error("Failed to generate itinerary. Please check the connection between frontend and backend.");
      }
    } else {
      message.error("Failed to generate itinerary. Please check the backend address or service status.");
    }
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <section class="home-page">
    <div class="planner-card">
      <div class="section-title">
        <span class="section-title__icon">📍</span>
        <span>Destination & Dates</span>
      </div>

      <a-row :gutter="[16, 16]">
        <a-col :xs="24" :md="8">
          <label class="field-label">Destination City</label>
          <a-input v-model:value="formState.destination" placeholder="Enter a destination" />
        </a-col>
        <a-col :xs="24" :md="5">
          <label class="field-label">Start Date</label>
          <a-input v-model:value="formState.startDate" />
        </a-col>
        <a-col :xs="24" :md="5">
          <label class="field-label">End Date</label>
          <a-input v-model:value="formState.endDate" />
        </a-col>
        <a-col :xs="12" :md="3">
          <label class="field-label">Travelers</label>
          <a-input-number v-model:value="formState.travelers" :min="1" style="width: 100%" />
        </a-col>
        <a-col :xs="12" :md="3">
          <label class="field-label">Trip Length</label>
          <div class="pill-box">{{ dayCount }} days</div>
        </a-col>
      </a-row>
    </div>

    <div class="planner-card">
      <div class="section-title">
        <span class="section-title__icon">⚙️</span>
        <span>Preferences</span>
      </div>

      <a-row :gutter="[16, 16]">
        <a-col :xs="24" :md="8">
          <label class="field-label">Pace Preference</label>
          <a-select
            v-model:value="formState.pace"
            :options="[
              { label: 'Relaxed', value: 'Relaxed' },
              { label: 'Moderate', value: 'Moderate' },
              { label: 'Packed', value: 'Packed' }
            ]"
          />
        </a-col>
        <a-col :xs="24" :md="8">
          <label class="field-label">Accommodation Preference</label>
          <a-select
            v-model:value="formState.hotelLevel"
            :options="[
              { label: 'Comfort', value: 'Comfort' },
              { label: 'Upscale', value: 'Upscale' },
              { label: 'Budget', value: 'Budget' }
            ]"
          />
        </a-col>
        <a-col :xs="24" :md="8">
          <label class="field-label">Budget</label>
          <a-input-number v-model:value="formState.budget" :min="0" style="width: 100%" />
        </a-col>
      </a-row>

      <div class="checkbox-area">
        <label class="field-label">Travel Preferences</label>
        <a-checkbox-group v-model:value="formState.preferences" :options="preferenceOptions" />
      </div>

      <div class="checkbox-area">
        <label class="field-label">Dietary Preferences</label>
        <a-checkbox-group
          v-model:value="formState.dietaryPreferences"
          :options="dietaryOptions"
        />
      </div>
    </div>

    <div class="planner-card">
      <div class="section-title">
        <span class="section-title__icon">💬</span>
        <span>Additional Requests</span>
      </div>
      <a-textarea
        v-model:value="formState.notes"
        :rows="4"
        placeholder="Enter any preferences, pace, or notes you'd like kept in mind"
      />
    </div>

    <div class="submit-panel">
      <button
        class="submit-panel__button"
        :disabled="isSubmitting"
        @click="handleSubmit"
      >
        {{ isSubmitting ? "Generating..." : "Start Planning" }}
      </button>
      <div class="submit-panel__status">
        Currently connected to `/trip/generate`; once generation succeeds, the real itinerary will be shown directly.
      </div>
    </div>
  </section>
</template>

<style scoped>
.home-page {
  display: grid;
  gap: 18px;
}

.planner-card {
  padding: 24px;
  border-radius: 20px;
  background: rgba(255, 252, 246, 0.96);
  box-shadow: 0 12px 40px rgba(100, 76, 50, 0.09);
  border: 1px solid rgba(180, 155, 110, 0.15);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(140, 110, 70, 0.18);
  color: #3d3328;
  font-size: 16px;
  font-weight: 700;
  font-family: "Georgia", serif;
}

.section-title__icon {
  font-size: 18px;
}

.field-label {
  display: block;
  margin-bottom: 8px;
  color: #7c6f5e;
  font-size: 13px;
  font-weight: 600;
  font-family: "Segoe UI", sans-serif;
}

.pill-box {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  border-radius: 12px;
  background: linear-gradient(135deg, #5a7a40 0%, #6e8f52 100%);
  color: #f5f0e4;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
}

.checkbox-area {
  margin-top: 18px;
}

:deep(.ant-checkbox-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

:deep(.ant-checkbox-wrapper) {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  border-radius: 10px;
  border: 1px solid rgba(140, 110, 70, 0.22);
  background: #faf5ec;
  color: #5a4a36;
  font-size: 13px;
  font-family: "Segoe UI", sans-serif;
  cursor: pointer;
  transition: all 0.15s;
  margin: 0 !important;
}

:deep(.ant-checkbox-wrapper:hover) {
  border-color: rgba(90, 120, 60, 0.4);
  background: rgba(90, 120, 60, 0.07);
}

:deep(.ant-checkbox-wrapper.ant-checkbox-wrapper-checked) {
  background: #4a6b30;
  border-color: #4a6b30;
  color: #f5f0e4;
}

:deep(.ant-checkbox) {
  display: none;
}

.submit-panel {
  padding: 12px 8px 0;
  text-align: center;
}

.submit-panel__button {
  min-width: 220px;
  border: none;
  border-radius: 999px;
  padding: 14px 32px;
  background: linear-gradient(135deg, #b86b3a 0%, #c98248 100%);
  color: #fffaf2;
  font-size: 15px;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
  cursor: pointer;
  box-shadow: 0 16px 32px rgba(160, 90, 40, 0.22);
  letter-spacing: 0.02em;
  transition: opacity 0.2s;
}

.submit-panel__button:disabled {
  opacity: 0.65;
  cursor: wait;
}

.submit-panel__status {
  margin-top: 12px;
  color: #9c8c7a;
  font-size: 13px;
  font-family: "Segoe UI", sans-serif;
}
</style>
