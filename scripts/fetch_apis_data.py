#!/usr/bin/env python3
import os
import json
import logging
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd

API_USER = os.getenv("TIBSCHOL_API_USERNAME", "")
API_PASS = os.getenv("TIBSCHOL_API_PASSWORD", "")
API_BASE_URL = "https://tibschol.acdh-ch-dev.oeaw.ac.at/apis/api/"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def fetch_data(endpoint, params=None):
    """Fetch data from the given API endpoint."""
    logging.debug("Fetching data from %s", endpoint)
    if not endpoint.startswith("http"):
        endpoint = f"{API_BASE_URL}{endpoint}"
    response = requests.get(
        endpoint, params=params, auth=HTTPBasicAuth(API_USER, API_PASS)
    )

    if response.status_code == 200:
        return response.json()

    logging.error("Error fetching data: %s from %s", response.status_code, response.url)
    return None


def fetch_list_data(endpoint):
    """Fetch paginated list data from the given API endpoint."""
    all_data = []
    while True:
        data = fetch_data(endpoint)
        if data is None or "results" not in data or not data["results"]:
            break
        all_data.extend(data["results"])
        if "next" not in data or not data["next"]:
            break
        endpoint = data["next"]
    return all_data


# Get Instances with relations
if __name__ == "__main__":
    list_data = fetch_list_data("apis_ontology.instance/")
    print(f"Fetched {len(list_data)} instances.")
    pd.DataFrame(list_data).to_csv(
        f"data/tibschol_instances_with_relations.csv", index=False
    )
