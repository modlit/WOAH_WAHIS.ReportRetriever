# Copyright 2022, Loic Leray
# Updated 2026 to use the new WAHIS v1 API endpoints.
# Please acknowledge Loic Leray for making this data available in your
# research.
# ---
# See https://github.com/loicleray/OIE_WAHIS.ReportRetriever for documentation
# and explanations.

import argparse
import json
import os
import time
from datetime import date, timedelta
from curl_cffi import requests
import pandas as pd
from tqdm import tqdm

# --- API configuration ---
BASE_URL = "https://wahis.woah.org/api/v1"
API_HEADERS = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'accept-language': 'en',
    'env': 'PRD',
    'type': 'REQUEST',
    'token': '#PIPRD202006#',
    'clientId': 'OIEwebsite',
}

# Reusable session with browser TLS fingerprint (bypasses Cloudflare)
session = requests.Session(impersonate='chrome')


def api_get(path, params=None):
    '''Make an authenticated GET request to the WAHIS API.'''
    url = f"{BASE_URL}{path}"
    resp = session.get(url, headers=API_HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def api_post(path, payload, params=None):
    '''Make an authenticated POST request to the WAHIS API.'''
    url = f"{BASE_URL}{path}"
    if params:
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{param_str}"
    resp = session.post(url, headers=API_HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def get_filter_options():
    '''Returns a dictionary with the options and acceptable values to filter
    WAHIS reports. Fetches from the new v1 API endpoints.'''

    report_filter_options = {}

    filter_endpoints = {
        "country": "/pi/country/list",
        "region": "/pi/country/list-geo-region",
        "diseases": "/pi/disease/first-level-filters",
        "diseaseType": "/pi/disease/second-level-filters",
        "reason": "/pi/catalog/report-reason/list",
        "eventStatus": "/pi/catalog/event-status/list",
        "reportStatus": "/pi/catalog/report-status/list",
    }

    for name, endpoint in filter_endpoints.items():
        try:
            data = api_get(endpoint, params={"language": "en"})
            report_filter_options[name] = data
            print(f"  [{name}] OK ({len(data)} items)")
        except Exception as e:
            print(f"  [{name}] Error: {e}")

    return report_filter_options


def save_filter_options(save_path):
    '''Save a file with contents of get_filter_options() in file path of your
    choosing.'''

    file_name = "WAHIS_filter_options"
    full_path = os.path.join(save_path, file_name + ".json")
    filter_options = get_filter_options()
    print("Creating file with filter options for you to check...")
    with open(full_path, "w") as f:
        json.dump(filter_options, f, indent=2)
    print(f"File saved as {file_name}.json in 'OUTPUTS' folder.")


def resolve_country_ids(country_names):
    '''Convert country names to area IDs used by the new API.'''
    if not country_names:
        return []
    all_countries = api_get("/pi/country/list", params={"language": "en"})
    name_to_id = {c["name"].lower(): c["areaId"] for c in all_countries}
    ids = []
    for name in country_names:
        lower = name.lower()
        if lower in name_to_id:
            ids.append(name_to_id[lower])
        else:
            # Try partial match
            matches = [cid for cname, cid in name_to_id.items() if lower in cname]
            if matches:
                ids.extend(matches)
            else:
                print(f"  Warning: country '{name}' not found in WAHIS")
    return ids


def resolve_disease_ids(disease_names):
    '''Convert disease names to IDs used by the new API.'''
    if not disease_names:
        return []
    all_diseases = api_get("/pi/disease/first-level-filters", params={"language": "en"})
    name_to_ids = {d["name"].strip().lower(): d["ids"] for d in all_diseases}
    ids = []
    for name in disease_names:
        lower = name.strip().lower()
        if lower in name_to_ids:
            ids.extend(name_to_ids[lower])
        else:
            # Try partial match
            matches = [did for dname, did in name_to_ids.items() if lower in dname]
            if matches:
                for m in matches:
                    ids.extend(m)
            else:
                print(f"  Warning: disease '{name}' not found in WAHIS")
    return ids


def resolve_region_country_ids(region_names):
    '''Convert region names to country area IDs.'''
    if not region_names:
        return []
    all_regions = api_get("/pi/country/list-geo-region", params={"language": "en"})
    ids = []
    for region in all_regions:
        if region["name"].lower() in [r.lower() for r in region_names]:
            ids.extend(region["countryIds"])
    return ids


def get_report_list(country=[], region=[], disease=[],
                    start_date="1901-01-01", end_date=str(date.today())):
    '''Returns a list of reports corresponding to the filter results.
    Uses the new /api/v1/pi/event/filtered-list endpoint.'''

    # Resolve names to IDs
    country_ids = resolve_country_ids(country)
    disease_ids = resolve_disease_ids(disease)

    # Regions add to country filter
    if region:
        region_country_ids = resolve_region_country_ids(region)
        # Merge with explicit country IDs (union)
        country_ids = list(set(country_ids + region_country_ids))

    # Build date filter: the API uses submissionDate with {from, to}
    date_filter = None
    if start_date and end_date:
        date_filter = {"from": start_date, "to": end_date}

    PAGE_SIZE = 2000  # max reliable page size for this API
    all_reports = []
    page = 0  # 0-indexed

    while True:
        payload = {
            "eventIds": [],
            "reportIds": [],
            "countries": country_ids,
            "firstDiseases": disease_ids,
            "secondDiseases": [],
            "typeStatuses": [],
            "reasons": [],
            "eventStatuses": [],
            "reportTypes": [],
            "reportStatuses": [],
            "eventStartDate": date_filter,
            "submissionDate": None,
            "animalTypes": [],
            "sortColumn": "submissionDate",
            "sortOrder": "desc",
            "pageSize": PAGE_SIZE,
            "pageNumber": page,
        }

        result = api_post("/pi/event/filtered-list", payload, params={"language": "en"})
        batch = result.get("list", [])
        total = result.get("totalSize", 0)
        all_reports.extend(batch)

        if page == 0:
            print(f"  Total reports available: {total}")

        if len(all_reports) >= total or len(batch) < PAGE_SIZE:
            break
        page += 1

    return {"list": all_reports, "totalSize": len(all_reports)}


def get_report_contents(report_id):
    '''Returns the full report data for a given reportID.
    Uses the new /api/v1/pi/review/report/{id}/all-information endpoint.'''

    try:
        # sleep to reduce server load
        time.sleep(0.5)
        data = api_get(f"/pi/review/report/{report_id}/all-information",
                       params={"language": "en"})
        return data
    except Exception as e:
        print(f"  Error fetching report {report_id}: {e}")
        return None


def flatten_report(report_summary, report_detail):
    '''Flatten a report summary (from filtered-list) and its full detail
    (from all-information) into a single flat dict for DataFrame export.'''

    row = dict(report_summary)  # start with summary fields

    if report_detail is None:
        return row

    # Add event-level information
    event = report_detail.get("event", {})
    if event:
        row["event_country"] = event.get("country", {}).get("name", "")
        row["event_country_iso"] = event.get("country", {}).get("isoCode", "")
        row["event_disease"] = event.get("disease", {}).get("name", "")
        row["event_disease_group"] = event.get("disease", {}).get("group", "")
        row["event_disease_category"] = event.get("disease", {}).get("category", "")
        row["causal_agent"] = event.get("causalAgent", {}).get("name", "")
        row["event_start_date"] = event.get("startDate", "")
        row["event_end_date"] = event.get("endDate", "")
        row["event_confirmation_date"] = event.get("confirmationDate", "")

    # Add outbreak data if present
    outbreaks = report_detail.get("outbreaks", [])
    row["num_outbreaks"] = len(outbreaks)

    # Add control measures
    control_measures = report_detail.get("controlMeasures", [])
    if control_measures:
        row["control_measures"] = ", ".join(
            cm.get("name", "") for cm in control_measures if cm.get("name")
        )

    # Add epidemiological comments
    epi_comments = report_detail.get("epidemiologicalComments", {})
    if isinstance(epi_comments, dict):
        row["epi_comment"] = epi_comments.get("comment", "")

    return row


def flatten_outbreak(report_summary, report_detail, outbreak):
    '''Flatten a single outbreak with its parent report/event data.'''

    row = dict(report_summary)

    # Event-level data
    event = report_detail.get("event", {})
    if event:
        row["event_country"] = event.get("country", {}).get("name", "")
        row["event_country_iso"] = event.get("country", {}).get("isoCode", "")
        row["event_disease"] = event.get("disease", {}).get("name", "")
        row["causal_agent"] = event.get("causalAgent", {}).get("name", "")

    # Outbreak-level data
    row["outbreak_id"] = outbreak.get("outbreakId", "")
    row["outbreak_location"] = outbreak.get("location", "")
    row["outbreak_start_date"] = outbreak.get("startDate", "")
    row["outbreak_end_date"] = outbreak.get("endDate", "")
    row["latitude"] = outbreak.get("latitude", "")
    row["longitude"] = outbreak.get("longitude", "")
    row["outbreak_status"] = outbreak.get("status", "")
    row["epi_unit"] = outbreak.get("epiUnit", "")

    # Species affected
    species = outbreak.get("speciesDetails", [])
    if species:
        row["species"] = ", ".join(
            s.get("speciesName", "") for s in species if isinstance(s, dict)
        )
        # Aggregate case counts
        row["total_susceptible"] = sum(
            s.get("susceptible", 0) or 0 for s in species if isinstance(s, dict))
        row["total_cases"] = sum(
            s.get("cases", 0) or 0 for s in species if isinstance(s, dict))
        row["total_deaths"] = sum(
            s.get("deaths", 0) or 0 for s in species if isinstance(s, dict))
        row["total_killed"] = sum(
            s.get("killed", 0) or 0 for s in species if isinstance(s, dict))

    return row


def main():
    ##############################
    ### Parsing User Arguments ###
    ##############################
    parser = argparse.ArgumentParser(
        description="Gather WAHIS reports based on user's filters.")
    parser.add_argument("-op", "--options", action="store_true",
                        help="Creates a file with the possible filter options.")
    parser.add_argument("-c", "--country", type=str, nargs="*", default=[],
                        help="Countries to filter by. E.G. '-c France Germany Ethiopia'")
    parser.add_argument("-r", "--region", type=str, nargs="*", default=[],
                        help="Regions to filter by. E.G. '-r Africa Asia Europe'")
    parser.add_argument("-d", "--disease", type=str, nargs="*", default=[],
                        help="Disease(s) of interest. E.G. -d 'Anthrax '")
    parser.add_argument("-sd", "--start_date", required=False, type=str,
                        default=str(date.today() - timedelta(days=7)),
                        help="Start date in YYYY-MM-DD format.")
    parser.add_argument("-ed", "--end_date", required=False, type=str,
                        default=str(date.today()),
                        help="End date in YYYY-MM-DD format.")
    parser.add_argument("-s", "--save_rate", default=250, type=int,
                        help="How many reports to process before saving output.")
    parsed_args = parser.parse_args()

    # Create output directory
    CURRENT_DIRECTORY = os.getcwd()
    OUTPUT_DIRECTORY = os.path.join(CURRENT_DIRECTORY, 'OUTPUTS')
    if not os.path.exists(OUTPUT_DIRECTORY):
        os.makedirs(OUTPUT_DIRECTORY)

    # Run save_filter_options() based on CLI input
    if parsed_args.options:
        filter_file = os.path.join(OUTPUT_DIRECTORY, "WAHIS_filter_options.json")
        if not os.path.exists(filter_file):
            save_filter_options(OUTPUT_DIRECTORY)
        else:
            print(f"Filter options file already exists: {filter_file}")
        return

    EXPORT_NAME = "WAHIS_ReportOutbreaks"

    ########################
    ### Main tool logic. ###
    ########################
    if (parsed_args.country or parsed_args.region or parsed_args.disease
            or parsed_args.start_date or parsed_args.end_date):

        # Get list of reports
        print("Fetching report list...")
        reports_response = get_report_list(
            country=parsed_args.country,
            region=parsed_args.region,
            disease=parsed_args.disease,
            start_date=parsed_args.start_date,
            end_date=parsed_args.end_date,
        )

        report_list = reports_response.get('list', [])
        print(f"Found {len(report_list)} reports.")

        if not report_list:
            print("No reports found for the given filters.")
            return

        all_rows = []
        file_save_counter = 1

        for count, report_obj in enumerate(tqdm(report_list, desc='Gathering Reports...'), 1):
            report_id = report_obj.get('reportId')

            # Fetch full report contents
            report_detail = get_report_contents(report_id)

            if report_detail is None:
                print(f"  Skipping report {report_id} (fetch failed)")
                continue

            # Extract outbreaks; create one row per outbreak
            outbreaks = report_detail.get("outbreaks", [])
            if outbreaks:
                for outbreak in outbreaks:
                    row = flatten_outbreak(report_obj, report_detail, outbreak)
                    all_rows.append(row)
            else:
                # No outbreaks: still create a row with report-level data
                row = flatten_report(report_obj, report_detail)
                all_rows.append(row)

            # Save periodically
            if count % parsed_args.save_rate == 0 or count == len(report_list):
                if all_rows:
                    df = pd.json_normalize(all_rows)
                    output_path = os.path.join(
                        OUTPUT_DIRECTORY,
                        f"{EXPORT_NAME}_{file_save_counter}"
                    )
                    try:
                        df.to_excel(f"{output_path}.xlsx", index=False)
                        print(f"\n  Saved {output_path}.xlsx ({len(df)} rows)")
                    except Exception:
                        df.to_csv(f"{output_path}.csv", index=False)
                        print(f"\n  Saved {output_path}.csv ({len(df)} rows)")
                    del df
                    all_rows.clear()
                    file_save_counter += 1

    print("Done.")


if __name__ == "__main__":
    main()
