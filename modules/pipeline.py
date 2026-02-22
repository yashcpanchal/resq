"""
P1: ACAPS/FTS Data Engineering — Pipeline Module

Ingests humanitarian crisis data and calculates neglect scores.
Output target: data/neglect_scores.json
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
import csv
import os
from collections import defaultdict
from typing import Any
from dotenv import load_dotenv

from databricks import sql

# Path to the FTS funding CSV relative to the project root.
_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "funding",
    "fts_requirements_funding_globalcluster_global.csv",
)


def calculate_funding_scores() -> dict[str, float]:
    """Fetch funding gaps by querying the Databricks table.

    Returns:
        A dict mapping country code to its funding_gap,
        e.g. ``{"AFG": 0.42, "SDN": 0.78, ...}``.
    """
    load_dotenv()
    connection = sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOSTNAME"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN"),
        auth_type="pat" # Explicitly tell it you're using a Personal Access Token
    )
    
    cursor = connection.cursor()

    query = """
        SELECT country, funding_gap
        FROM workspace.`final-data`.final_scores
        ORDER BY funding_gap DESC
    """

    cursor.execute(query)
    result = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.close()
    connection.close()

    return result


async def get_crisis_scores() -> list[dict[str, Any]]:
    load_dotenv()
    connection = sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOSTNAME"),
        http_path=os.getenv("DATABRICKS_HTTP_PATH"),
        access_token=os.getenv("DATABRICKS_TOKEN"),
        auth_type="pat" # Explicitly tell it you're using a Personal Access Token
    )
    
    cursor = connection.cursor()

    query = """
        SELECT country, final_score
        FROM workspace.`final-data`.final_scores
        ORDER BY final_score DESC
    """

    cursor.execute(query)
    result = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.close()
    connection.close()

    return result
