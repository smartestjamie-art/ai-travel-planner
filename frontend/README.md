# Frontend Development Notes

`frontend/` is currently the frontend project for TripPlannerDemo, built with `Vue 3 + TypeScript + Vite + Ant Design Vue + Axios`. It is no longer just a skeleton page — it now works end-to-end with the backend for generation, saving, history, maps, weather, editing, and export.

## 1. Current Capabilities

- Planning page: fill in destination, dates, number of travelers, budget, preferences, and notes, then calls `/trip/generate`
- Result page: displays the itinerary overview, budget breakdown, daily spending, map, weather, location photos, and the daily schedule
- Save: calls `/trip/save`
- History list: calls `/trip` and `/trip/{trip_id}`
- Delete a saved trip: calls `DELETE /trip/{trip_id}`
- Smart adjustment: calls `/trip/edit`
- Export: supports PDF / Markdown, saving the current page data before exporting
- Map: integrates the Amap (Gaode) JavaScript API
- Weather: displays the weather forecast returned by the backend's `/weather/forecast`

## 2. Directory Structure

```text
frontend/
├── src/
│   ├── components/
│   │   └── AmapTripMap.vue
│   ├── services/
│   │   └── api.ts
│   ├── types/
│   │   └── index.ts
│   ├── views/
│   │   ├── History.vue
│   │   ├── Home.vue
│   │   └── Result.vue
│   ├── App.vue
│   └── main.ts
├── .env.example
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 3. Environment Variables

Create a `.env` file under the `frontend/` directory on the server:

```env
VITE_API_BASE_URL=http://your-server-address:8000
VITE_AMAP_JS_KEY=your Amap JavaScript API key
```

Notes:

- If you're opening the browser on your own computer, don't set `VITE_API_BASE_URL` to the server's internal `127.0.0.1`
- The Amap frontend map requires a JavaScript API key, not the backend Web service key
- After changing `.env`, restart `npm run dev`

## 4. How to Start

### Install dependencies

```bash
cd ~/autodl-tmp/TripPlannerDemo/frontend
npm install
```

### Start the dev server

```bash
cd ~/autodl-tmp/TripPlannerDemo/frontend
npm run dev
```

`vite.config.ts` is currently configured as:

```ts
server: {
  host: "0.0.0.0",
  port: 5173,
}
```

Access it in your browser at:

```text
http://your-server-address:5173
```

## 5. Prerequisites for Backend Integration

Before running the frontend, the backend needs to be started first:

```bash
cd ~/autodl-tmp/TripPlannerDemo/backend
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

Once your browser can reach the following addresses, open the frontend:

```text
http://your-server-address:8000/
http://your-server-address:8000/docs
```

## 6. Common Issues

### Page loads, but generating an itinerary fails

Check the following first:

- Whether the backend on port `8000` is running
- Whether `VITE_API_BASE_URL` in `frontend/.env` is correct
- Whether the frontend was restarted after changing `.env`
- Whether the browser console shows any CORS or network request errors

### Map doesn't display

Check the following first:

- Whether `VITE_AMAP_JS_KEY` is filled in
- Whether this key is actually an Amap JavaScript API key
- Whether the itinerary already contains `latitude` / `longitude`

### Exported PDF opens as a blank page

Under normal conditions, the backend should show:

```text
POST /trip/save
GET /export/{trip_id}/pdf
```

If you only see `POST /trip/save`, it means the frontend did not navigate to the export URL — first confirm the frontend code has been updated and restarted.

### `npm run dev` reports that `package.json` can't be found

This means you're in the wrong directory. Frontend commands must be run from the `frontend/` directory:

```bash
cd ~/autodl-tmp/TripPlannerDemo/frontend
```

Do not run `npm run dev` from the `backend/` directory.

## 7. Recommended Verification Order

1. Start the backend
2. Start the frontend
3. Generate a trip
4. Check the map locations
5. Check the weather information
6. Save the trip
7. Open the history list
8. Smart-adjust a specific day
9. Export as PDF
10. Delete the test trip
