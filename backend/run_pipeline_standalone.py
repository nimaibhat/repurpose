"""
Run the drug repurposing pipeline directly (no web server needed).
This will show all debug output including error logging.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.open_targets import search_disease, get_associated_targets
from services.rcsb import search_pdb, download_pdb, get_resolution
from services.claude import fetch_alphafold_pdb
from services.chembl import search_drugs
from services.nvidia_nim import run_diffdock_batch
from config import get_settings
from pathlib import Path

# Ensure structures directory exists
STRUCTURES_DIR = Path(__file__).parent / "structures"
STRUCTURES_DIR.mkdir(exist_ok=True)

async def main():
    """Run the full pipeline."""
    settings = get_settings()
    disease_name = "pancreatic neoplasm"
    
    print("\n" + "=" * 80)
    print("DRUG REPURPOSING PIPELINE - STANDALONE RUN")
    print("=" * 80)
    print(f"Disease: {disease_name}\n")
    
    # Step 1: Get targets
    print("📌 STEP 1: Finding disease-associated targets...")
    disease_info = await search_disease(disease_name)
    targets = await get_associated_targets(disease_info["id"])
    targets = targets[:100]  # Limit to 100
    print(f"✓ Found {len(targets)} targets for {disease_info['name']}\n")
    
    # Step 2: Get structures
    print("📌 STEP 2: Fetching protein structures...")
    structures = []
    for target in targets:
        symbol = target.get("symbol")
        if not symbol:
            continue
        
        # Try RCSB first
        try:
            pdb_id = await search_pdb(symbol)
            if pdb_id:
                pdb_text = await download_pdb(pdb_id)
                resolution = await get_resolution(pdb_id)
                
                # Save PDB file
                pdb_file_path = STRUCTURES_DIR / f"{pdb_id}.pdb"
                pdb_file_path.write_text(pdb_text)
                
                structures.append({
                    "symbol": symbol,
                    "pdb_id": pdb_id,
                    "resolution": resolution,
                    "source": "rcsb",
                    "file_path": str(pdb_file_path),
                })
                continue  
        except Exception as e:
            print(f"  RCSB failed for {symbol}: {e}")
        
        # Try AlphaFold fallback
        try:
            uniprot_id, pdb_text = await fetch_alphafold_pdb(symbol)
            af_id = f"AF-{uniprot_id}-F1"
            
            # Save AlphaFold PDB file
            pdb_file_path = STRUCTURES_DIR / f"{af_id}.pdb"
            pdb_file_path.write_text(pdb_text)
            
            structures.append({
                "symbol": symbol,
                "pdb_id": af_id,
                "resolution": None,
                "source": "alphafold",
                "file_path": str(pdb_file_path),
            })
        except Exception as e:
            print(f"  AlphaFold failed for {symbol}: {e}")
    
    print(f"✓ Retrieved {len(structures)} structures\n")
    
    # Step 3: Get drugs
    print("📌 STEP 3: Finding drug compounds...")
    all_drugs = []
    symbols_with_structures = {s["symbol"] for s in structures}
    
    for symbol in symbols_with_structures:
        try:
            _, drugs = await search_drugs(symbol, limit=50)
            for drug in drugs:
                drug["target_symbol"] = symbol
                all_drugs.append(drug)
        except Exception as e:
            print(f"  ChEMBL failed for {symbol}: {e}")
    
    print(f"✓ Found {len(all_drugs)} compounds\n")
    
    # Step 4: Run docking
    print("📌 STEP 4: Running molecular docking...")
    print("=" * 80)
    print("🔍 WATCH FOR DEBUG OUTPUT BELOW:")
    print("   🚀 = Starting batch")
    print("   🔴 = Error logged")
    print("   📝 = Flushing errors to file")
    print("   ✅ = Batch complete")
    print("=" * 80 + "\n")
    
    all_results = []
    
    for structure in structures:
        symbol = structure["symbol"]
        pdb_id = structure.get("pdb_id", "AlphaFold")
        
        # Find drugs for this target
        target_drugs = [d for d in all_drugs if d.get("target_symbol") == symbol]
        if not target_drugs:
            continue
        
        # Load PDB file
        pdb_file = Path(structure["file_path"])
        if not pdb_file.exists():
            print(f"⚠️  PDB file not found: {pdb_file}")
            continue
        
        pdb_text = pdb_file.read_text()
        
        # Run docking
        print(f"\n{'='*80}")
        print(f"🧬 {symbol} ({pdb_id}): {len(target_drugs)} compounds")
        print(f"{'='*80}")
        
        try:
            results = await run_diffdock_batch(
                api_key=settings.nvidia_nim_api_key,
                pdb_text=pdb_text,
                drugs=target_drugs,
                pdb_id=pdb_id,
            )
            
            for result in results:
                result["pdb_id"] = pdb_id
                result["target_symbol"] = symbol
            
            all_results.extend(results)
            
        except Exception as e:
            print(f"❌ Docking failed for {symbol}: {e}")
    
    # Summary
    print("\n" + " =" * 80)
    print("📊 FINAL SUMMARY")
    print("=" * 80)
    print(f"Targets: {len(targets)}")
    print(f"Structures: {len(structures)}")
    print(f"Compounds: {len(all_drugs)}")
    print(f"Successful Dockings: {len(all_results)}")
    print(f"\n🔍 Check backend/diffdock_errors.json for detailed error log\n")

if __name__ == "__main__":
    asyncio.run(main())
