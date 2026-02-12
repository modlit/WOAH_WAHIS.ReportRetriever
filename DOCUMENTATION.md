# WAHIS API Documentation

Technical documentation for the WAHIS (World Animal Health Information System) API as used by `report_retriever.py`.

> Originally documented by [Loic Leray](https://loicleray.com). Updated by [modlit](https://modlit.io) (2026) to reflect the new v1 API.
> For general usage instructions see `README.md`.

---

## API Overview

The WAHIS API base URL is:

```
https://wahis.woah.org/api/v1
```

All requests require the following headers:

```json
{
  "Accept": "application/json",
  "Content-Type": "application/json",
  "accept-language": "en",
  "env": "PRD",
  "type": "REQUEST",
  "token": "#PIPRD202006#",
  "clientId": "OIEwebsite"
}
```

The script uses `curl_cffi` with Chrome TLS fingerprint impersonation to bypass Cloudflare bot detection. A standard `requests` library will receive HTTP 403.

---

## Known API Endpoints

### GET /pi/country/list

Returns a list of all countries/territories with their numeric area IDs.

- **URL:** `https://wahis.woah.org/api/v1/pi/country/list?language=en`
- **Method:** GET

**Example response:**

```json
[
  { "areaId": 1, "name": "Afghanistan", "isoCode": "AF" },
  { "areaId": 2, "name": "Albania", "isoCode": "AL" },
  ...
]
```

### GET /pi/country/list-geo-region

Returns geographic regions with the country IDs they contain.

- **URL:** `https://wahis.woah.org/api/v1/pi/country/list-geo-region?language=en`
- **Method:** GET

**Example response:**

```json
[
  { "name": "Africa", "countryIds": [4, 12, 24, ...] },
  { "name": "Europe", "countryIds": [1, 2, 8, ...] },
  ...
]
```

### GET /pi/disease/first-level-filters

Returns all diseases with their numeric IDs for use in search filters.

- **URL:** `https://wahis.woah.org/api/v1/pi/disease/first-level-filters?language=en`
- **Method:** GET

**Example response:**

```json
[
  { "name": "Bluetongue virus (Inf. with) ", "ids": [42] },
  { "name": "African swine fever virus (Inf. with) ", "ids": [1] },
  ...
]
```

**Note:** Disease names may contain trailing spaces and parenthetical annotations. Always use the `-op` flag to get exact names.

### GET /pi/disease/second-level-filters

Returns disease subtypes/serotypes.

- **URL:** `https://wahis.woah.org/api/v1/pi/disease/second-level-filters?language=en`
- **Method:** GET

### GET /pi/catalog/report-reason/list

Returns possible report reasons (e.g. "First occurrence in the country").

- **URL:** `https://wahis.woah.org/api/v1/pi/catalog/report-reason/list?language=en`
- **Method:** GET

### GET /pi/catalog/event-status/list

Returns event status options (e.g. "On-going", "Resolved", "Stable").

- **URL:** `https://wahis.woah.org/api/v1/pi/catalog/event-status/list?language=en`
- **Method:** GET

### GET /pi/catalog/report-status/list

Returns report status options.

- **URL:** `https://wahis.woah.org/api/v1/pi/catalog/report-status/list?language=en`
- **Method:** GET

---

### POST /pi/event/filtered-list

Search for outbreak events matching given filters. Returns a paginated list of report summaries.

- **URL:** `https://wahis.woah.org/api/v1/pi/event/filtered-list?language=en`
- **Method:** POST
- **Max page size:** 2000 (larger values return empty results)
- **Page numbering:** 0-indexed

**Payload:**

```json
{
  "eventIds": [],
  "reportIds": [],
  "countries": [1, 2, 3],
  "firstDiseases": [42],
  "secondDiseases": [],
  "typeStatuses": [],
  "reasons": [],
  "eventStatuses": [],
  "reportTypes": [],
  "reportStatuses": [],
  "eventStartDate": { "from": "2024-01-01", "to": "2026-02-12" },
  "submissionDate": null,
  "animalTypes": [],
  "sortColumn": "submissionDate",
  "sortOrder": "desc",
  "pageSize": 2000,
  "pageNumber": 0
}
```

**Key fields:**

| Field | Type | Description |
|-------|------|-------------|
| `countries` | `int[]` | Area IDs from `/pi/country/list`. Empty = all countries. |
| `firstDiseases` | `int[]` | Disease IDs from `/pi/disease/first-level-filters`. Empty = all diseases. |
| `secondDiseases` | `int[]` | Subtype IDs from `/pi/disease/second-level-filters`. |
| `eventStartDate` | `object` | `{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}` or `null` for no date filter. |
| `submissionDate` | `object` | Same format as `eventStartDate`, filters by report submission date. |
| `reasons` | `int[]` | Reason IDs from `/pi/catalog/report-reason/list`. |
| `eventStatuses` | `int[]` | Status IDs from `/pi/catalog/event-status/list`. |
| `sortColumn` | `string` | Column to sort by (e.g. `"submissionDate"`, `"eventStartDate"`). |
| `sortOrder` | `string` | `"desc"` or `"asc"`. |
| `pageSize` | `int` | Max 2000. |
| `pageNumber` | `int` | 0-indexed page number. |

**Example response:**

```json
{
  "list": [
    {
      "reportId": 56789,
      "eventId": 12345,
      "country": "France",
      "disease": "Bluetongue virus (Inf. with) ",
      "subType": "BTV-3",
      "eventStartDate": "2024-08-15T00:00:00.000+00:00",
      "eventStatus": "On-going",
      "reason": "Recurrence",
      "reportType": "Follow-up report",
      "reportStatus": "Confirmed",
      "submissionDate": "2024-09-01T00:00:00.000+00:00",
      "reportNumber": 5,
      "isAquatic": false,
      "isLastReportUnchanged": false,
      "createdBy": "...",
      ...
    },
    ...
  ],
  "totalSize": 284
}
```

**Pagination:** The script loops with increasing `pageNumber` until `len(all_reports) >= totalSize` or a batch returns fewer than `pageSize` results.

---

### GET /pi/review/report/{reportId}/all-information

Returns the complete details for a single report, including event metadata, outbreaks, species data, control measures, and diagnostics.

- **URL:** `https://wahis.woah.org/api/v1/pi/review/report/{reportId}/all-information?language=en`
- **Method:** GET

**Example response structure:**

```json
{
  "event": {
    "country": { "name": "France", "isoCode": "FR", "areaId": 68 },
    "disease": {
      "name": "Bluetongue virus (Inf. with) ",
      "group": "Cattle diseases",
      "category": "Listed"
    },
    "causalAgent": { "name": "BTV-3" },
    "startDate": "2024-08-15T00:00:00.000+00:00",
    "endDate": null,
    "confirmationDate": "2024-08-20T00:00:00.000+00:00"
  },
  "outbreaks": [
    {
      "outbreakId": 98765,
      "location": "Commune de XYZ",
      "startDate": "2024-08-15T00:00:00.000+00:00",
      "endDate": "2024-09-10T00:00:00.000+00:00",
      "latitude": 48.8566,
      "longitude": 2.3522,
      "status": "Resolved",
      "epiUnit": "Farm",
      "speciesDetails": [
        {
          "speciesName": "Cattle",
          "susceptible": 150,
          "cases": 12,
          "deaths": 0,
          "killed": 0,
          "vaccinated": 150
        }
      ]
    },
    ...
  ],
  "controlMeasures": [
    { "name": "Movement control inside the country" },
    { "name": "Vaccination in response to the outbreak(s)" }
  ],
  "epidemiologicalComments": {
    "comment": "The outbreak was detected during routine surveillance..."
  }
}
```

**Key sections:**

| Section | Description |
|---------|-------------|
| `event` | Event-level metadata: country, disease, causal agent, dates. |
| `event.country` | Country name, ISO code, and numeric `areaId`. |
| `event.disease` | Disease name, group, and OIE category. |
| `outbreaks[]` | List of individual outbreaks with location, coordinates, dates, status. |
| `outbreaks[].speciesDetails[]` | Per-species breakdown: susceptible, cases, deaths, killed, vaccinated. |
| `controlMeasures[]` | Applied control measures. |
| `epidemiologicalComments` | Free-text epidemiological commentary. |

---

## Data Flattening

The script flattens the nested API responses into flat rows for export to Excel/CSV:

- **One row per outbreak** — each outbreak from each report becomes a separate row
- **Report-level fields** (reportId, eventId, country, disease, dates, status) are repeated for each outbreak row
- **Event-level fields** (event_country, event_disease, causal_agent, event dates) are extracted from the `event` object
- **Outbreak-level fields** (outbreak_id, location, coordinates, start/end dates, status, epi unit) come from each outbreak
- **Species aggregates** (total_susceptible, total_cases, total_deaths, total_killed) are summed across all species in the outbreak

Output is saved every 250 reports (configurable with `-s` flag) to avoid data loss on long runs.

---

## Changes from the Legacy API

| Aspect | Legacy (pre-2025) | Current (v1 API, 2026) |
|--------|-------------------|----------------------|
| Base URL | `https://wahis.woah.org/pi/` | `https://wahis.woah.org/api/v1/pi/` |
| Report list | `POST /pi/getReportList` | `POST /pi/event/filtered-list?language=en` |
| Report detail | `GET /pi/getReport/{id}` | `GET /pi/review/report/{id}/all-information?language=en` |
| Filter options | `GET /pi/reports/filters?columnName={x}` | Separate endpoints per filter type (see above) |
| Country filter | String names in `reportFilters.country` | Numeric area IDs in `countries` |
| Disease filter | String names in `reportFilters.diseases` | Numeric IDs in `firstDiseases` |
| Date filter | `reportFilters.reportDate.startDate/endDate` | `eventStartDate: {"from": ..., "to": ...}` |
| Page numbering | 1-indexed | 0-indexed |
| Max page size | ~1 billion | 2000 |
| Auth headers | None required | `token`, `clientId`, `env` headers required |
| Cloudflare | Not present | Active — requires TLS fingerprint impersonation |
