import httpx

BASE_URL = "https://api.platform.opentargets.org/api/v4/graphql"
TIMEOUT = 10.0

DISEASE_SEARCH_QUERY = """
query DiseaseSearch($name: String!) {
  search(queryString: $name, entityNames: ["disease"], page: {size: 1, index: 0}) {
    hits {
      id
      name
    }
  }
}
"""

ASSOCIATED_TARGETS_QUERY = """
query AssociatedTargets($efoId: String!) {
  disease(efoId: $efoId) {
    associatedTargets(page: {size: 5, index: 0}) {
      rows {
        target {
          id
          approvedSymbol
          approvedName
        }
        score
      }
    }
  }
}
"""


class OpenTargetsError(Exception):
    pass


async def _post_graphql(query: str, variables: dict) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(BASE_URL, json={"query": query, "variables": variables})
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body:
            raise OpenTargetsError(body["errors"][0].get("message", "GraphQL error"))
        return body["data"]


async def search_disease(disease_name: str) -> dict:
    """Resolve a disease name to its EFO ID. Returns {id, name}."""
    data = await _post_graphql(DISEASE_SEARCH_QUERY, {"name": disease_name})
    hits = data.get("search", {}).get("hits", [])
    if not hits:
        raise OpenTargetsError(f"No disease found for '{disease_name}'")
    return {"id": hits[0]["id"], "name": hits[0]["name"]}


async def get_associated_targets(efo_id: str) -> list[dict]:
    """Get top 5 targets for a disease EFO ID, sorted by association score."""
    data = await _post_graphql(ASSOCIATED_TARGETS_QUERY, {"efoId": efo_id})
    disease = data.get("disease")
    if not disease:
        raise OpenTargetsError(f"No data for disease '{efo_id}'")

    rows = disease.get("associatedTargets", {}).get("rows", [])
    return [
        {
            "ensembl_id": row["target"]["id"],
            "symbol": row["target"].get("approvedSymbol") or row["target"]["id"],
            "name": row["target"]["approvedName"],
            "score": round(row["score"], 4),
        }
        for row in rows
    ]
