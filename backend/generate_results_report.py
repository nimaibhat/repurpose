import asyncio
import httpx
from datetime import datetime


async def run_pipeline_and_generate_report(disease: str = "pancreatic cancer"):
    """Run the pipeline and generate a formatted text report."""
    
    print(f"Running pipeline for: {disease}")
    print("This may take several minutes...\n")
    
    async with httpx.AsyncClient(timeout=600.0) as client:
        resp = await client.post(
            "http://localhost:8001/api/pipeline/",
            json={"disease": disease}
        )
        
        if resp.status_code != 200:
            print(f"Error: {resp.status_code}")
            print(resp.text)
            return
        
        result = resp.json()
    
    # Generate formatted report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append(f"DRUG REPURPOSING PIPELINE RESULTS")
    report_lines.append(f"Disease: {result['disease']}")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    # Summary
    report_lines.append(f"Total Targets Found: {len(result['targets'])}")
    report_lines.append(f"Total Structures Retrieved: {len(result['structures'])}")
    report_lines.append(f"Total Compounds Identified: {len(result['drugs'])}")
    report_lines.append(f"Total Docking Simulations: {len(result['docking_results'])}")
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    # Group docking results by target protein
    by_target = {}
    for dr in result['docking_results']:
        target = dr['target_symbol']
        if target not in by_target:
            by_target[target] = []
        by_target[target].append(dr)
    
    # For each target, show all compounds and their scores
    for target_symbol in sorted(by_target.keys()):
        # Get target info
        target_info = next((t for t in result['targets'] if t['symbol'] == target_symbol), None)
        structure_info = next((s for s in result['structures'] if s['symbol'] == target_symbol), None)
        
        report_lines.append(f"TARGET PROTEIN: {target_symbol}")
        if target_info:
            report_lines.append(f"  Name: {target_info['name']}")
            report_lines.append(f"  Association Score: {target_info['score']}")
        if structure_info:
            report_lines.append(f"  Structure: {structure_info['pdb_id']} ({structure_info['source']})")
            if structure_info.get('resolution'):
                report_lines.append(f"  Resolution: {structure_info['resolution']} Å")
        
        compounds = by_target[target_symbol]
        report_lines.append(f"  Compounds Tested: {len(compounds)}")
        report_lines.append("")
        
        # Sort compounds by confidence (highest first)
        compounds.sort(key=lambda x: x['confidence_score'], reverse=True)
        
        for i, compound in enumerate(compounds, 1):
            report_lines.append(f"    {i}. {compound['drug_name'] or 'Unknown'}")
            report_lines.append(f"       Confidence Score: {compound['confidence_score']:.4f}")
            if 'raw_confidence' in compound:
                report_lines.append(f"       Raw Score: {compound['raw_confidence']:.4f}")
            report_lines.append(f"       SMILES: {compound['smiles'][:60]}...")
            report_lines.append(f"       Poses Generated: {compound.get('num_poses', 'N/A')}")
            report_lines.append("")
        
        report_lines.append("-" * 80)
        report_lines.append("")
    
    # Show targets without compounds
    targets_without_compounds = [
        t['symbol'] for t in result['targets']
        if t['symbol'] not in by_target
    ]
    
    if targets_without_compounds:
        report_lines.append(f"TARGETS WITHOUT SUCCESSFUL DOCKING ({len(targets_without_compounds)}):")
        report_lines.append("")
        for symbol in targets_without_compounds[:20]:  # Show first 20
            target_info = next((t for t in result['targets'] if t['symbol'] == symbol), None)
            if target_info:
                report_lines.append(f"  - {symbol}: {target_info['name']}")
        if len(targets_without_compounds) > 20:
            report_lines.append(f"  ... and {len(targets_without_compounds) - 20} more")
        report_lines.append("")
    
    # Save to file
    output_file = f"pipeline_results_{disease.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"Report saved to: {output_file}")
    print(f"\nTotal targets with docking results: {len(by_target)}")
    print(f"Total docking simulations: {len(result['docking_results'])}")
    
    return output_file


if __name__ == "__main__":
    asyncio.run(run_pipeline_and_generate_report("pancreatic cancer"))
