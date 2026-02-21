# Repurpose

An AI-powered drug repurposing platform that identifies existing drugs that could be repositioned to treat diseases. Given a disease name, the pipeline automatically finds protein targets, retrieves 3D structures, searches for approved drugs, runs molecular docking simulations, and generates AI-powered analysis reports — all streamed to the UI in real time.

## How It Works

The platform runs a 5-step automated pipeline:

1. **Target Identification** — Queries the Open Targets GraphQL API to find the top disease-associated protein targets ranked by association score
2. **Structure Retrieval** — Fetches 3D protein structures from RCSB PDB (with AlphaFold fallback for predicted structures)
3. **Drug Search** — Queries ChEMBL for approved and clinical-phase compounds targeting each protein, extracting SMILES, mechanisms of action, and clinical phase data
4. **Molecular Docking** — Runs NVIDIA DiffDock simulations for each protein-drug pair to predict binding affinity, producing confidence scores and 3D ligand poses
5. **AI Report Generation** — Feeds top docking results to Claude, which generates mechanistic explanations, risk/benefit assessments, and a prioritized ranking of drug candidates

Results stream to the frontend via Server-Sent Events (SSE), so each step renders as it completes.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, TypeScript, TailwindCSS, Framer Motion |
| 3D Visualization | 3Dmol.js (protein viewer), Three.js, smiles-drawer (2D molecules) |
| Backend | FastAPI (Python), Uvicorn, Pydantic |
| Docking Engine | NVIDIA NIM DiffDock |
| AI Analysis | Claude (Anthropic API) |
| Data Sources | Open Targets, RCSB PDB, AlphaFold, ChEMBL, UniProt |
| Database | Supabase |

## Project Structure

```
repurpose/
├── src/
│   ├── app/
│   │   ├── page.tsx              # Landing page
│   │   ├── research/page.tsx     # Disease input & search config
│   │   ├── pipeline/page.tsx     # Real-time pipeline visualization
│   │   └── results/page.tsx      # Final results & recommendations
│   └── components/               # MolViewer, MoleculeCard, PipelineStepper, etc.
├── backend/
│   ├── main.py                   # FastAPI app with CORS
│   ├── config.py                 # Environment/settings loader
│   ├── routes/
│   │   └── pipeline.py           # Batch + SSE streaming endpoints
│   └── services/
│       ├── open_targets.py       # Disease → protein targets
│       ├── rcsb.py               # PDB structures + AlphaFold fallback
│       ├── chembl.py             # Drug/compound search
│       ├── nvidia_nim.py         # DiffDock batch docking
│       └── claude.py             # AI report generation
```

## Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- API keys for: NVIDIA NIM, Anthropic (Claude), Supabase

### Environment Variables

Create a `.env` file in the project root:

```env
NEXT_PUBLIC_SUPABASE_URL=<your-supabase-url>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY=<your-supabase-key>
NVIDIA_NIM_API_KEY=<your-nvidia-nim-key>
ANTHROPIC_API_KEY=<your-anthropic-key>
```

### Frontend

```bash
npm install
npm run dev        # http://localhost:3000
```

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs available at http://localhost:8000/docs.

## Usage

1. Open http://localhost:3000 and click through to the research page
2. Enter a disease (e.g. "pancreatic cancer")
3. Choose a mode — **Explore** (all targets), **Target** (specific protein), or **Drug** (specific compound)
4. Click **Run Analysis** — the pipeline page streams progress in real time
5. View the full results page with docking scores, 3D visualizations, and AI-generated recommendations
