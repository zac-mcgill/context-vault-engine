# Quickstart

## 1. Clone

```bash
git clone https://github.com/zac-mcgill/knowledge-system.git
cd knowledge-system
```

Requires Python 3.10+ and PyYAML:

```bash
pip install pyyaml
```


## 2. Initialise a Vault

Create a new working vault:

```bash
python run.py init my-vault
```

This:

* copies the demo vault
* removes generated artefacts
* updates configuration automatically

---

## 3. Run

Validate and analyse your vault:

```bash
python run.py validate
python run.py analyse
python run.py improve
python run.py report
```

## 3. What Happens

| Command | What it does |
| --- | --- |
| `python run.py validate` | Checks every markdown note against the vault schema. Prints pass/fail per file. Exits 0 if all files pass, 1 if any fail. |
| `python run.py analyse` | Prints seven structured analyses to stdout: completeness by domain, subdomain weak points, difficulty vs completeness, critical gaps, section deficiency heatmap, structural balance, and a prioritised action list. |
| `python run.py improve` | Scans all partial notes, scores them by difficulty and missing sections, and prints ranked upgrade tasks with specific writing instructions per note. |
| `python run.py report` | Generates `Vault Report.md` inside the vault's `Vault Files/` directory. Contains executive summary, domain analysis, key insights, critical gaps, section deficiencies, and priority actions. |
| `python run.py init <name>` | Creates a new vault by copying the demo vault, removes generated files, and updates configuration automatically. |

`validate`, `analyse`, and `improve` are read-only — they never modify files. `report` writes one markdown file.

---

## 4. MCP Server (Optional)

The MCP server exposes a read-only API over your active vault. It reads `config/config.yaml` automatically — no additional configuration is required.

### Requirements

```bash
pip install fastapi uvicorn pyyaml
```

### Start

```bash
python mcp/server/mcp_server.py
```

The server starts on `http://127.0.0.1:8000` and automatically loads whichever vault is set in `config/config.yaml`.

### Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/vaults` | GET | List the active vault |
| `/query` | POST | Query notes with filters |
| `/note` | GET | Retrieve a single note |
| `/stats` | GET | Aggregate a field across the vault |
| `/health` | GET | Server health and metrics |
| `/contract` | GET | Run system contract checks |

No manual config edits are needed. After `python run.py init my-vault`, the MCP server will serve the new vault automatically.
