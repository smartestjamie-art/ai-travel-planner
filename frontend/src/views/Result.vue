<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { message } from "ant-design-vue";

import AmapTripMap from "../components/AmapTripMap.vue";
import {
  editTrip,
  fetchWeatherForecast,
  getMarkdownExportUrl,
  getPdfExportUrl,
  saveTrip,
} from "../services/api";
import type { Itinerary, WeatherForecastResponse } from "../types";

const props = defineProps<{
  itinerary: Itinerary | null;
}>();

const emit = defineEmits<{
  backHome: [];
  viewHistory: [];
  updated: [itinerary: Itinerary];
}>();

const saving = ref(false);
const exportingPdf = ref(false);
const exportingMarkdown = ref(false);
const editing = ref(false);
const editScope = ref("day_1");
const editInstruction = ref("Make this day more relaxed, with fewer fixed activities.");
const weatherLoading = ref(false);
const weatherError = ref("");
const weather = ref<WeatherForecastResponse | null>(null);

function formatShortDate(dateText?: string | null): string {
  if (!dateText) {
    return "TBD";
  }

  const parts = dateText.split("-");
  if (parts.length !== 3) {
    return dateText;
  }

  return `${parts[1]}-${parts[2]}`;
}

function formatWeatherDate(dateText?: string | null, week?: string | null): string {
  const weekdayMap: Record<string, string> = {
    "1": "Mon",
    "2": "Tue",
    "3": "Wed",
    "4": "Thu",
    "5": "Fri",
    "6": "Sat",
    "7": "Sun",
  };
  const weekday = week ? weekdayMap[week] || `Day ${week}` : "";
  return [formatShortDate(dateText), weekday].filter(Boolean).join(" ");
}

const budgetItems = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  const budget = props.itinerary.budget_breakdown;
  return [
    { label: "Attraction Tickets", value: `¥${budget.tickets.toFixed(0)}` },
    { label: "Hotel Accommodation", value: `¥${budget.hotel.toFixed(0)}` },
    { label: "Meals", value: `¥${budget.meals.toFixed(0)}` },
    { label: "Transportation", value: `¥${budget.transport.toFixed(0)}` },
  ];
});

const dayBudgetItems = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  return props.itinerary.days.map((day) => {
    const tickets = day.spots.reduce((sum, spot) => sum + (spot.estimated_cost ?? 0), 0);
    const meals = day.meals.reduce((sum, meal) => sum + (meal.estimated_cost ?? 0), 0);
    const transport = day.transport.reduce((sum, item) => sum + (item.estimated_cost ?? 0), 0);
    const hotel = day.hotel?.estimated_cost ?? 0;
    const total = tickets + meals + transport + hotel;

    return {
      key: day.day_index,
      title: `Day ${day.day_index}`,
      subtitle: day.theme || "Untitled Theme",
      tickets,
      meals,
      transport,
      hotel,
      total,
    };
  });
});

const mapPoints = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  return props.itinerary.days.flatMap((day) =>
    day.spots.map((spot) => ({
      key: `${day.day_index}-${spot.name}`,
      dayIndex: day.day_index,
      date: day.date || "TBD",
      theme: day.theme || "Untitled Theme",
      name: spot.name,
      address: spot.address || spot.location || "To be added",
      latitude: spot.latitude,
      longitude: spot.longitude,
      poiId: spot.poi_id,
      imageUrl: spot.image_url,
      description: spot.description || "No description available",
    }))
  );
});

const technicalTipKeywords = [
  "LLM",
  "RAG",
  "LangChain",
  "Chroma",
  "demo",
  "test",
  "rules",
  "model",
  "source code",
];

const rainWeatherKeywords = ["rain", "showers", "thunderstorm", "light rain", "moderate rain", "heavy rain"];
const sunnyTipKeywords = ["sunscreen", "sun", "sunshine", "sun exposure"];

const weatherText = computed(() => {
  if (!weather.value) {
    return "";
  }

  return weather.value.days
    .map((day) => `${day.day_weather || ""}${day.night_weather || ""}`)
    .join(" ");
});

const hasRainyWeather = computed(() => {
  return rainWeatherKeywords.some((keyword) => weatherText.value.includes(keyword));
});

const displayTips = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  const tips = props.itinerary.tips
    .map((tip) => tip.trim())
    .filter(Boolean)
    .filter((tip) => !technicalTipKeywords.some((keyword) => tip.includes(keyword)));

  const weatherAwareTips = hasRainyWeather.value
    ? tips.filter((tip) => !sunnyTipKeywords.some((keyword) => tip.includes(keyword)))
    : tips;

  if (hasRainyWeather.value) {
    weatherAwareTips.push("Rain is possible, so bring an umbrella or a lightweight raincoat.");
    weatherAwareTips.push("Roads can be slippery in rainy weather — wear non-slip shoes around Erhai Lake and the old town's stone streets.");
  }

  const uniqueTips = Array.from(new Set(weatherAwareTips));
  if (uniqueTips.length) {
    return uniqueTips;
  }

  return [
    `Check the real-time weather in ${props.itinerary.destination} and bring rain gear or a light jacket as needed.`,
    "The old town, eco-corridor, and stone-paved streets are best explored at a leisurely pace — comfortable, non-slip shoes are recommended.",
  ];
});

function buildVisibleItinerary(): Itinerary | null {
  if (!props.itinerary) {
    return null;
  }

  return {
    ...props.itinerary,
    tips: displayTips.value,
  };
}

async function loadWeather() {
  if (!props.itinerary?.destination) {
    weather.value = null;
    return;
  }

  weatherLoading.value = true;
  weatherError.value = "";
  try {
    weather.value = await fetchWeatherForecast(props.itinerary.destination);
  } catch (error) {
    console.error(error);
    weather.value = null;
    weatherError.value = "Failed to load weather information.";
  } finally {
    weatherLoading.value = false;
  }
}

watch(
  () => props.itinerary?.destination,
  () => {
    void loadWeather();
  },
  { immediate: true }
);

watch(
  () => props.itinerary?.trip_id,
  () => {
    const firstDay = props.itinerary?.days[0];
    editScope.value = firstDay ? `day_${firstDay.day_index}` : "day_1";
  },
  { immediate: true }
);

async function openPdfExport() {
  const itineraryToExport = buildVisibleItinerary();
  if (!itineraryToExport) {
    return;
  }

  const exportWindow = window.open("about:blank", "_blank");
  exportingPdf.value = true;
  try {
    await saveTrip(itineraryToExport);
    const exportUrl = getPdfExportUrl(itineraryToExport.trip_id);
    if (exportWindow) {
      exportWindow.location.href = exportUrl;
    } else {
      window.location.href = exportUrl;
    }
  } catch (error) {
    console.error(error);
    exportWindow?.close();
    message.error("Failed to sync the current itinerary before exporting the PDF.");
  } finally {
    exportingPdf.value = false;
  }
}

async function openMarkdownExport() {
  const itineraryToExport = buildVisibleItinerary();
  if (!itineraryToExport) {
    return;
  }

  const exportWindow = window.open("about:blank", "_blank");
  exportingMarkdown.value = true;
  try {
    await saveTrip(itineraryToExport);
    const exportUrl = getMarkdownExportUrl(itineraryToExport.trip_id);
    if (exportWindow) {
      exportWindow.location.href = exportUrl;
    } else {
      window.location.href = exportUrl;
    }
  } catch (error) {
    console.error(error);
    exportWindow?.close();
    message.error("Failed to sync the current itinerary before exporting Markdown.");
  } finally {
    exportingMarkdown.value = false;
  }
}

async function handleSave() {
  const itineraryToSave = buildVisibleItinerary();
  if (!itineraryToSave) {
    return;
  }

  saving.value = true;
  try {
    await saveTrip(itineraryToSave);
    message.success("Itinerary saved. You can view it in the history list.");
  } catch (error) {
    console.error(error);
    message.error("Failed to save the itinerary.");
  } finally {
    saving.value = false;
  }
}

async function handleEdit() {
  if (!props.itinerary) {
    return;
  }

  const instruction = editInstruction.value.trim();
  if (!instruction) {
    message.warning("Please enter how you'd like to adjust the itinerary.");
    return;
  }

  editing.value = true;
  try {
    const updatedItinerary = await editTrip({
      trip_id: props.itinerary.trip_id,
      current_itinerary: props.itinerary,
      user_instruction: instruction,
      edit_scope: editScope.value,
      preserve_constraints: ["Keep the budget structure", "Keep the destination and travel dates"],
    });
    emit("updated", updatedItinerary);
    message.success("Itinerary updated with smart adjustments.");
  } catch (error) {
    console.error(error);
    message.error("Smart adjustment failed. Please try again later.");
  } finally {
    editing.value = false;
  }
}
</script>

<template>
  <section v-if="itinerary" class="result-page">
    <aside class="sidebar-card">
      <div class="sidebar-card__title">Itinerary Navigation</div>
      <ul class="sidebar-list">
        <li>Overview</li>
        <li>Budget Breakdown</li>
        <li>Daily Spending</li>
        <li>Smart Adjustment</li>
        <li>Attraction Map</li>
        <li>Weather</li>
        <li>Point Details</li>
        <li>Daily Itinerary</li>
      </ul>

      <div class="sidebar-actions">
        <button class="back-button" @click="$emit('backHome')">Back to Planning</button>
        <button class="save-button" :disabled="saving" @click="handleSave">
          {{ saving ? "Saving..." : "Save Itinerary" }}
        </button>
        <button class="history-button" @click="$emit('viewHistory')">History</button>
        <button class="export-button" :disabled="exportingPdf" @click="openPdfExport">
          {{ exportingPdf ? "Preparing PDF..." : "Export PDF" }}
        </button>
        <button
          class="export-button export-button--light"
          :disabled="exportingMarkdown"
          @click="openMarkdownExport"
        >
          {{ exportingMarkdown ? "Preparing..." : "Export Markdown" }}
        </button>
      </div>
    </aside>

    <div class="result-grid">
      <section class="result-card">
        <div class="result-card__title">{{ itinerary.destination }} Travel Plan</div>
        <div class="info-row"><strong>Trip ID: </strong>{{ itinerary.trip_id }}</div>
        <div class="info-row">
          <strong>Dates: </strong>
          {{ itinerary.days[0]?.date || "TBD" }} to
          {{ itinerary.days[itinerary.days.length - 1]?.date || "TBD" }}
        </div>
        <div class="info-row"><strong>Destination: </strong>{{ itinerary.destination }}</div>
        <div class="info-row summary-text">{{ itinerary.summary }}</div>
        <div v-if="displayTips.length" class="overview-tips">
          <div class="overview-tips__title">Travel Tips</div>
          <ul>
            <li v-for="tip in displayTips" :key="tip">{{ tip }}</li>
          </ul>
        </div>
      </section>

      <section class="result-card">
        <div class="result-card__title">Budget Breakdown</div>
        <div class="budget-grid">
          <div v-for="item in budgetItems" :key="item.label" class="budget-box">
            <div class="budget-box__label">{{ item.label }}</div>
            <div class="budget-box__value">{{ item.value }}</div>
          </div>
        </div>
        <div class="budget-total">
          <span>Estimated Total Cost</span>
          <strong>¥{{ itinerary.estimated_budget.toFixed(0) }}</strong>
        </div>
      </section>

      <section class="result-card result-card--map">
        <div class="result-card__title">Attraction Map</div>
        <AmapTripMap :points="mapPoints" />
      </section>

      <section class="result-card result-card--weather">
        <div class="result-card__title">Weather</div>

        <div v-if="weatherLoading" class="weather-state">Loading weather information...</div>
        <div v-else-if="weatherError" class="weather-state">{{ weatherError }}</div>
        <div v-else-if="weather" class="weather-grid">
          <article
            v-for="day in weather.days"
            :key="`${day.date}-${day.week}`"
            class="weather-card"
          >
            <div class="weather-card__date">
              {{ formatWeatherDate(day.date, day.week) }}
            </div>
            <div class="weather-card__temp">
              {{ day.day_temp || "-" }}° / {{ day.night_temp || "-" }}°
            </div>
            <div class="weather-card__desc">Day: {{ day.day_weather || "Unknown" }}</div>
            <div class="weather-card__desc">Night: {{ day.night_weather || "Unknown" }}</div>
          </article>
        </div>
        <div v-else class="weather-state">No weather information available.</div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">Smart Itinerary Adjustment</div>
        <div class="edit-panel">
          <div class="edit-panel__controls">
            <label class="edit-field">
              <span>Adjustment Scope</span>
              <select v-model="editScope">
                <option
                  v-for="day in itinerary.days"
                  :key="day.day_index"
                  :value="`day_${day.day_index}`"
                >
                  Day {{ day.day_index }} · {{ day.theme || "Untitled Theme" }}
                </option>
              </select>
            </label>
            <button
              class="edit-submit-button"
              :disabled="editing"
              @click="handleEdit"
            >
              {{ editing ? "Adjusting..." : "Smart Adjust" }}
            </button>
          </div>
          <textarea
            v-model="editInstruction"
            class="edit-textarea"
            rows="3"
            placeholder="For example: Make day two more relaxed with a lighter schedule; swap day three for a spot good for watching the sunset."
          ></textarea>
        </div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">Daily Spending</div>
        <div class="day-budget-grid">
          <article
            v-for="item in dayBudgetItems"
            :key="item.key"
            class="day-budget-card"
          >
            <div class="day-budget-card__header">
              <span>{{ item.title }}</span>
              <span>{{ item.subtitle }}</span>
            </div>
            <div class="day-budget-card__body">
              <div class="day-budget-row">
                <span>Tickets</span>
                <strong>¥{{ item.tickets.toFixed(0) }}</strong>
              </div>
              <div class="day-budget-row">
                <span>Meals</span>
                <strong>¥{{ item.meals.toFixed(0) }}</strong>
              </div>
              <div class="day-budget-row">
                <span>Transport</span>
                <strong>¥{{ item.transport.toFixed(0) }}</strong>
              </div>
              <div class="day-budget-row">
                <span>Lodging</span>
                <strong>¥{{ item.hotel.toFixed(0) }}</strong>
              </div>
              <div class="day-budget-row day-budget-row--total">
                <span>Daily Total</span>
                <strong>¥{{ item.total.toFixed(0) }}</strong>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">Map Point Details</div>
        <div class="point-grid">
          <article v-for="point in mapPoints" :key="point.key" class="point-card">
            <div class="point-card__header">
              <span>Day {{ point.dayIndex }} · {{ point.name }}</span>
              <span>{{ formatShortDate(point.date) }}</span>
            </div>

            <div class="point-card__body">
              <div
                v-if="point.imageUrl"
                class="point-card__image"
                :style="{ backgroundImage: `url(${point.imageUrl})` }"
              ></div>
              <div v-else class="point-card__image point-card__image--empty">
                No image available
              </div>
              <div class="point-card__line">
                <strong>Theme: </strong>
                <span>{{ point.theme }}</span>
              </div>
              <div class="point-card__line">
                <strong>Address: </strong>
                <span>{{ point.address }}</span>
              </div>
              <div class="point-card__desc">{{ point.description }}</div>
            </div>
          </article>
        </div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">Daily Itinerary</div>
        <div class="day-list">
          <details
            v-for="day in itinerary.days"
            :key="day.day_index"
            class="day-card"
            :open="day.day_index === 1"
          >
            <summary class="day-card__header">
              <span>Day {{ day.day_index }} · {{ day.theme || "Untitled Theme" }}</span>
              <span class="day-card__meta">{{ formatShortDate(day.date) }}</span>
            </summary>

            <div class="day-card__body">
              <div class="day-card__section">
                <strong>Main Attraction: </strong>
                <span>{{ day.spots[0]?.name || "Not scheduled" }}</span>
              </div>
              <div class="day-card__section">
                <strong>Attraction Address: </strong>
                <span>{{ day.spots[0]?.address || day.spots[0]?.location || "To be added" }}</span>
              </div>
              <div class="day-card__section">
                <strong>Dining Suggestion: </strong>
                <span>{{ day.meals[0]?.name || "Not scheduled" }}</span>
              </div>
              <div class="day-card__section">
                <strong>Lodging: </strong>
                <span>{{ day.hotel?.name || "Not scheduled" }}</span>
              </div>
              <div class="day-card__section">
                <strong>Transportation: </strong>
                <span>
                  {{
                    day.transport[0]?.distance_km != null
                      ? `${day.transport[0].distance_km.toFixed(2)} km / ${day.transport[0].estimated_minutes ?? 0} min`
                      : day.transport[0]?.duration || "To be added"
                  }}
                </span>
              </div>
              <div class="day-card__section">
                <strong>Notes: </strong>
                <span>{{ day.notes[day.notes.length - 1] || "None" }}</span>
              </div>
            </div>
          </details>
        </div>
      </section>
    </div>
  </section>

  <section v-else class="empty-state">
    <div class="empty-state__card">
      <h2>No results yet</h2>
      <p>Go back to the planning page to generate an itinerary, and the results page will display real data.</p>
      <button class="back-button" @click="$emit('backHome')">Back to Planning</button>
    </div>
  </section>
</template>

<style scoped>
.result-page {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 22px;
}

.sidebar-card,
.result-card,
.empty-state__card {
  border-radius: 20px;
  background: rgba(255, 252, 246, 0.96);
  box-shadow: 0 12px 40px rgba(100, 76, 50, 0.09);
  border: 1px solid rgba(180, 155, 110, 0.15);
}

.sidebar-card {
  align-self: start;
  padding: 18px;
}

.sidebar-card__title,
.result-card__title {
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: 12px;
  background: linear-gradient(135deg, #3a5c2a 0%, #5e8048 100%);
  color: #f5f0e4;
  font-size: 15px;
  font-weight: 700;
  font-family: "Georgia", serif;
  letter-spacing: 0.01em;
}

.sidebar-list {
  display: grid;
  gap: 12px;
  padding: 0;
  margin: 0 0 18px;
  list-style: none;
  color: #6a5c4a;
  font-size: 14px;
  font-family: "Segoe UI", sans-serif;
}

.sidebar-actions {
  display: grid;
  gap: 10px;
}

.back-button,
.save-button,
.history-button,
.export-button {
  width: 100%;
  border: none;
  border-radius: 12px;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
  cursor: pointer;
  transition: opacity 0.2s;
}

.back-button {
  background: rgba(90, 122, 64, 0.12);
  color: #4a6b30;
}

.save-button {
  background: linear-gradient(135deg, #b86b3a 0%, #c98248 100%);
  color: #fffaf2;
}

.save-button:disabled,
.export-button:disabled {
  opacity: 0.65;
  cursor: wait;
}

.history-button {
  background: rgba(90, 70, 40, 0.1);
  color: #6a4e2e;
}

.export-button {
  background: rgba(90, 120, 60, 0.12);
  color: #4a7030;
}

.export-button--light {
  background: rgba(140, 100, 50, 0.1);
  color: #7a5828;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.result-card {
  padding: 18px;
}

.result-card--map,
.result-card--weather {
  min-height: 330px;
}

.result-card--full {
  grid-column: 1 / -1;
}

.info-row {
  margin-bottom: 10px;
  color: #4a4036;
  line-height: 1.75;
  font-family: "Segoe UI", sans-serif;
}

.summary-text {
  margin-top: 14px;
}

.overview-tips {
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(90, 120, 60, 0.07);
  border: 1px solid rgba(120, 150, 80, 0.15);
}

.overview-tips__title {
  margin-bottom: 8px;
  color: #3d5028;
  font-weight: 800;
  font-family: "Georgia", serif;
}

.overview-tips ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 18px;
  color: #5a5040;
  line-height: 1.75;
  font-family: "Segoe UI", sans-serif;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.budget-box {
  padding: 16px;
  border-radius: 14px;
  background: #faf5ec;
  border: 1px solid rgba(160, 130, 90, 0.14);
}

.budget-box__label {
  color: #9c8c7a;
  font-size: 13px;
  font-family: "Segoe UI", sans-serif;
}

.budget-box__value {
  margin-top: 10px;
  color: #b86b3a;
  font-size: 22px;
  font-weight: 700;
  font-family: "Georgia", serif;
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 14px;
  padding: 16px 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, #b86b3a 0%, #c98248 100%);
  color: #fffaf2;
  font-family: "Segoe UI", sans-serif;
}

.budget-total strong {
  font-size: 28px;
  font-family: "Georgia", serif;
}

.weather-state {
  color: #9c8c7a;
  line-height: 1.8;
  font-family: "Segoe UI", sans-serif;
}

.weather-grid {
  display: grid;
  gap: 12px;
}

.weather-card {
  padding: 14px;
  border-radius: 14px;
  background: #faf5ec;
  border: 1px solid rgba(160, 130, 90, 0.14);
}

.weather-card__date {
  color: #3d3020;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
}

.weather-card__temp {
  margin: 8px 0;
  color: #b86b3a;
  font-size: 24px;
  font-weight: 800;
  font-family: "Georgia", serif;
}

.weather-card__desc {
  color: #7c6f5e;
  line-height: 1.7;
  font-family: "Segoe UI", sans-serif;
}

.edit-panel {
  display: grid;
  gap: 14px;
}

.edit-panel__controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px;
  gap: 12px;
  align-items: end;
}

.edit-field {
  display: grid;
  gap: 8px;
  color: #4a3c28;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
}

.edit-field select,
.edit-textarea {
  width: 100%;
  border: 1px solid rgba(160, 130, 90, 0.22);
  border-radius: 12px;
  background: #faf5ec;
  color: #3d3020;
  font: inherit;
  outline: none;
  font-family: "Segoe UI", sans-serif;
}

.edit-field select {
  min-height: 44px;
  padding: 0 14px;
}

.edit-textarea {
  resize: vertical;
  min-height: 92px;
  padding: 12px 14px;
  line-height: 1.7;
}

.edit-field select:focus,
.edit-textarea:focus {
  border-color: rgba(90, 122, 64, 0.6);
  box-shadow: 0 0 0 3px rgba(90, 122, 64, 0.1);
}

.edit-submit-button {
  min-height: 44px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #5a7a40 0%, #6e8f52 100%);
  color: #f5f0e4;
  font-weight: 800;
  font-family: "Segoe UI", sans-serif;
  cursor: pointer;
  transition: opacity 0.2s;
}

.edit-submit-button:disabled {
  opacity: 0.65;
  cursor: wait;
}

.day-budget-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.day-budget-card {
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(160, 130, 90, 0.14);
  background: #faf5ec;
}

.day-budget-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(90, 120, 60, 0.1);
  color: #3d3020;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
}

.day-budget-card__body {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.day-budget-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #4a4036;
  font-family: "Segoe UI", sans-serif;
}

.day-budget-row--total {
  padding-top: 10px;
  border-top: 1px solid rgba(160, 130, 90, 0.16);
  color: #7a4020;
  font-weight: 700;
}

.point-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
}

.point-card {
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(160, 130, 90, 0.14);
  background: #faf5ec;
}

.point-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(90, 120, 60, 0.1);
  color: #3d3020;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
}

.point-card__body {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.point-card__image {
  min-height: 150px;
  border-radius: 12px;
  background-position: center;
  background-size: cover;
  background-color: #ede5d0;
}

.point-card__image--empty {
  display: grid;
  place-items: center;
  color: #9c8c7a;
  font-weight: 700;
  background: linear-gradient(135deg, rgba(160, 130, 80, 0.15), rgba(90, 120, 60, 0.1)), #f0e8d8;
  font-family: "Segoe UI", sans-serif;
}

.point-card__line {
  color: #4a4036;
  line-height: 1.7;
  font-family: "Segoe UI", sans-serif;
}

.point-card__desc {
  padding-top: 10px;
  border-top: 1px solid rgba(160, 130, 90, 0.14);
  color: #7c6f5e;
  line-height: 1.7;
  font-family: "Segoe UI", sans-serif;
}

.day-list {
  display: grid;
  gap: 12px;
}

.day-card {
  border-radius: 16px;
  border: 1px solid rgba(160, 130, 90, 0.14);
  background: #faf5ec;
  overflow: hidden;
}

.day-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(90, 120, 60, 0.1);
  color: #3d3020;
  font-weight: 700;
  font-family: "Segoe UI", sans-serif;
  cursor: pointer;
  list-style: none;
}

.day-card__header::-webkit-details-marker {
  display: none;
}

.day-card__header::after {
  content: "Expand";
  flex: 0 0 auto;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(90, 120, 60, 0.14);
  color: #4a6b30;
  font-size: 12px;
}

.day-card[open] .day-card__header::after {
  content: "Collapse";
}

.day-card__meta {
  margin-left: auto;
  color: #9c8c7a;
  font-size: 13px;
}

.day-card__body {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.day-card__section {
  color: #4a4036;
  line-height: 1.75;
  font-family: "Segoe UI", sans-serif;
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 360px;
}

.empty-state__card {
  max-width: 560px;
  padding: 36px;
  text-align: center;
}

.empty-state__card h2 {
  margin: 0 0 12px;
  color: #3a3020;
  font-family: "Georgia", serif;
}

.empty-state__card p {
  margin: 0 0 18px;
  color: #9c8c7a;
  line-height: 1.7;
  font-family: "Segoe UI", sans-serif;
}

@media (max-width: 960px) {
  .result-page {
    grid-template-columns: 1fr;
  }

  .result-grid {
    grid-template-columns: 1fr;
  }

  .edit-panel__controls {
    grid-template-columns: 1fr;
  }
}
</style>
