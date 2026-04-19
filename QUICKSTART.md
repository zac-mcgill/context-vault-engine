# Quickstart

## 1. Clone

```bash
git clone <repo-url> knowledge-system
cd knowledge-system
pip install -r requirements.txt
```

---

## 2. Initialise a Vault

```bash
python run.py init my-vault
```

This creates a fully valid vault and updates configuration automatically.

---

## 3. Generate Templates (Optional but Recommended)

```bash
python run.py templates
```

Templates are derived from the schema and ensure structural consistency.

---

## 4. Run the Pipeline

```bash
python run.py validate
python run.py analyse
python run.py improve
python run.py report
```

---

## 5. Start API Server (Optional)

```bash
python mcp/server/mcp_server.py
```

---

## 6. Query the System

* http://127.0.0.1:8000/summary
* http://127.0.0.1:8000/validation
* http://127.0.0.1:8000/tasks
* http://127.0.0.1:8000/tasks?limit=5
* http://127.0.0.1:8000/gaps
* http://127.0.0.1:8000/notes
