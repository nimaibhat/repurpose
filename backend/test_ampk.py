import asyncio
import httpx

async def check_ampk_ranking():
    # First, search for pancreatic cancer to get its EFO ID
    search_query = """
    query DiseaseSearch($name: String!) {
      search(queryString: $name, entityNames: ["disease"], page: {size: 1, index: 0}) {
        hits {
          id
          name
        }
      }
    }
    """
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Search for the disease
            resp = await client.post(
                "https://api.platform.opentargets.org/api/v4/graphql",
                json={"query": search_query, "variables": {"name": "pancreatic cancer"}}
            )
            resp.raise_for_status()
            body = resp.json()
            
            if 'errors' in body or not body.get('data'):
                print("Error searching for disease:", body)
                return
            
            hits = body['data']['search']['hits']
            if not hits:
                print("Disease 'pancreatic cancer' not found")
                return
            
            efo_id = hits[0]['id']
            disease_name = hits[0]['name']
            print(f"Found disease: {disease_name} ({efo_id})\n")
            
    except Exception as e:
        print(f"Error searching for disease: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Now get the associated targets with the correct EFO ID
    query = """
    query AssociatedTargets($efoId: String!) {
      disease(efoId: $efoId) {
        associatedTargets(page: {size: 100, index: 0}) {
          rows {
            target {
              approvedSymbol
              approvedName
            }
            score
          }
        }
      }
    }
    """
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.platform.opentargets.org/api/v4/graphql",
                json={"query": query, "variables": {"efoId": efo_id}}
            )
            resp.raise_for_status()
            body = resp.json()
            
            if 'errors' in body:
                print("GraphQL Error:", body['errors'])
                return
            
            data = body.get('data') if body else None
            if not data or not data.get('disease'):
                print("Error: No disease data in response")
                print("Full response:", body)
                return
            
            rows = data['disease'].get('associatedTargets', {}).get('rows', [])
            
            if not rows:
                print("Warning: No targets returned in the response")
                return
    except Exception as e:
        print(f"Error querying API: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n=== TOP 100 PANCREATIC CANCER TARGETS ===\n")
    
    ampk_genes = ['PRKAA1', 'PRKAA2', 'PRKAB1', 'PRKAB2', 'PRKAG1', 'PRKAG2', 'PRKAG3']
    rank = 0
    
    for row in rows:
        symbol = row['target'].get('approvedSymbol')
        if symbol:
            rank += 1
            score = round(row['score'], 4)
            name = row['target'].get('approvedName', 'N/A')
            
            if symbol in ampk_genes:
                print(f">>> RANK {rank}: {symbol} - {name} (score: {score}) <<<")
                print(f"    ^^^ AMPK SUBUNIT FOUND! ^^^")
            elif rank <= 20:
                print(f"{rank}. {symbol} - {name} (score: {score})")
    
    print("\nSearching entire list for AMPK...")
    found_any = False
    for i, row in enumerate(rows, 1):
        symbol = row['target'].get('approvedSymbol')
        if symbol in ampk_genes:
            score = round(row['score'], 4)
            name = row['target'].get('approvedName', 'N/A')
            print(f"  Found {symbol} at rank {i} (score: {score})")
            found_any = True
    
    if not found_any:
        print("  AMPK genes NOT found in top 100 targets!")

asyncio.run(check_ampk_ranking())
