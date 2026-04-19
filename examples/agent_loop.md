# Agent Workflow Loop

An external agent (LLM or script) can use the API to drive a closed-loop improvement cycle.

## Loop

1. `GET /tasks` — fetch prioritised upgrade tasks
2. Select the highest priority task
3. Generate or update the note content (external LLM or manual)
4. `GET /validation` — confirm the vault is still schema-compliant
5. Repeat from step 1

## Endpoints

### Get tasks

```
GET http://127.0.0.1:8000/tasks
```

Returns all upgrade tasks ranked by priority. Use `?limit=5` to restrict count, or `?min_priority=2` to filter by threshold.

### Get high-impact gaps

```
GET http://127.0.0.1:8000/gaps
```

Returns only partial notes with priority >= 2.

### Validate after changes

```
GET http://127.0.0.1:8000/validation
```

Returns pass/fail status and any invalid notes.

### Check coverage

```
GET http://127.0.0.1:8000/summary
```

Returns total notes, complete count, partial count, and coverage percentage.

## Example session

```
GET /tasks?limit=1

→ { "total": 8, "tasks": [{ "note": "Complexity Theory", "priority": 2.0, "type": "missing_section", "target": "Key Principles", "missing": ["Key Principles"], "instruction": "Add missing section: Key Principles" }] }

# Agent generates Key Principles section for Complexity Theory

GET /validation

→ { "status": "pass", "invalid_count": 0, "invalid_notes": [] }

GET /summary

→ { "total_notes": 19, "complete": 12, "partial": 7, "coverage": 63 }

# Loop continues with next task
```

## Constraints

- The API is read-only. Content generation happens externally.
- The system enforces structure. It does not generate content.
- All responses are deterministic given the same vault state.
