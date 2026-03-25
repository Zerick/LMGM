# GURPS AI Game Master — Discord Bot

## Project Overview
A GURPS 4th Edition AI Game Master running as a Discord bot on a Raspberry Pi 5 (8GB, aarch64).
Three-layer architecture: **LLM narrates** → **Rules engine computes** → **RAG provides rules knowledge**.
The LLM never does math. The engine never narrates. This separation is non-negotiable.

Full specification: @docs/blueprint.md

## Tech Stack
- Python 3.12+, virtual environment (venv)
- discord.py — Discord interface
- LiteLLM — model-agnostic LLM calls (supports Anthropic, OpenAI, etc.)
- SQLite (WAL mode) — all persistence
- ChromaDB + rank_bm25 — hybrid RAG retrieval
- LlamaIndex — RAG indexing
- Pydantic — data models and validation
- pytest — all testing
- Deployed on Raspberry Pi 5 via systemd

## Project Structure
```
gurps-gm/
├── bot/            # Discord interface (thin layer, routing only)
├── orchestrator/   # Game flow, turn pipeline, action classification
├── llm/            # Prompt assembly, API calls, response parsing
│   └── prompts/    # All prompt templates
├── engine/         # Deterministic GURPS rules (dice, combat, skills, tables)
├── rag/            # Structured GURPS knowledge retrieval
├── state/          # Character, scene, campaign persistence (Pydantic + SQLite)
├── data/           # GURPS source material and campaign settings
├── tests/          # Unit and integration tests, mirrors src structure
├── docs/           # blueprint.md and design docs
├── saves/          # Campaign save files (gitignored)
├── rag_index/      # Persisted vector index (gitignored)
├── .env            # API keys (gitignored)
├── config.yaml     # All tunable parameters, no magic numbers in code
├── main.py         # Entry point
└── requirements.txt
```

## Critical Architecture Rules
1. **Module boundaries are strict.** No module imports another module's internal files. Only import from `__init__.py` exports.
2. **The LLM never computes.** All dice rolls, damage math, DR subtraction, wound multipliers, success/failure thresholds — handled by engine/ only.
3. **The engine never narrates.** It returns structured dataclasses. The LLM turns those into story.
4. **GURPS rules come from RAG, not LLM training data.** When the LLM needs a rule, it gets the exact text from the index.
5. **All config in config.yaml.** No hardcoded values. API keys in .env only.
6. **Pydantic models for all data structures.** Characters, combat results, scene state — typed and validated.

## Design Decisions
These are settled design choices. Read before implementing any phase that touches
the relevant modules.

- **NPC consistency via `notes` field:** The `Character` model has a `notes: str = ""`
  field for freeform personality, voice, relationships, and secrets. Populated manually
  by the GM for important NPCs. Appears in the LLM character summary (via
  `to_llm_summary()`) only when non-empty, so blank mook NPCs waste no tokens.
  Auto-generation of notes from session events is a planned future extensibility
  feature (see blueprint Section 11.3). Never remove this field or make it required.

## Commands
```bash
# Activate virtual environment
source venv/bin/activate

# Run tests (always do this before committing)
pytest tests/ -v

# Run a specific test module
pytest tests/test_dice.py -v

# Start the bot
python main.py

# Check bot status (after deployment)
systemctl status gurps-gm
```

## Testing Rules
- Write tests BEFORE implementation for each feature.
- Every engine/ function must have unit tests covering: normal cases, edge cases, and critical thresholds.
- Run the FULL test suite (`pytest tests/ -v`) before every commit — not just the new tests.
- If a change causes any existing test to fail, stop and fix it before proceeding.
- Test files mirror source structure: `engine/dice.py` → `tests/test_dice.py`.

## Code Style
- Use dataclasses or Pydantic models for all structured data, never raw dicts.
- Type hints on all function signatures.
- Docstrings on all public functions.
- Functions should be small and single-purpose. Each step of the combat pipeline is its own function.
- No wildcard imports. Explicit imports only.
- f-strings for string formatting.

## Git Workflow
- Never work directly on `main`.
- Each implementation phase gets its own branch: `phase-1/skeleton`, `phase-2/rules-engine`, etc.
- Commit after each working feature within a phase, with descriptive messages.
- Merge to main only when ALL tests pass.
- Commit message format: `phase-N: brief description of what was added/changed`

## Session Discipline
- **Start a new Claude Code session after every successful commit.** Fresh context reads the codebase as it actually is, not as the conversation remembers it.
- Before ending a session: run full test suite, commit if green, note any TODOs.
- At the start of each session, read this file and check `git log --oneline -5` for recent context.

## Implementation Phases (current progress)
Phases are implemented in strict order. Do not skip ahead. See @docs/blueprint.md Section 10 for full details.

- [ ] Phase 0: Full environment and repo setup (details below)
- [ ] Phase 1: Skeleton — basic Discord bot connection, responds to messages
- [ ] Phase 2: Rules engine core — dice.py, tables.py, combat.py with full tests
- [ ] Phase 3: State system — character model, SQLite schema, scene tracking
- [ ] Phase 4: Basic LLM integration — prompt assembly, LiteLLM, conversational GM
- [ ] Phase 5: Orchestrator + engine integration — full turn pipeline
- [ ] Phase 6: RAG system — structured chunking, hybrid retrieval
- [ ] Phase 7: Multi-player + threading — turn order, DM handling
- [ ] Phase 8: Polish + deploy — slash commands, embeds, systemd service

## Common Mistakes to Avoid

### Phase 0 Checklist
Complete these steps in order. Each step should work before moving to the next.

**0a — Claude Code on the Pi**
- [ ] Verify Pi is ready: `uname -m` shows aarch64, 64-bit OS, 4GB+ RAM
- [ ] Install Node.js 20+ (required by Claude Code)
- [ ] Install Claude Code via native installer: `curl -fsSL https://claude.ai/install.sh | bash`
- [ ] Authenticate (may need to auth on another machine and scp credentials — see docs)
- [ ] Verify Claude Code runs: `claude --version`

**0b — Anthropic API account**
- [ ] Create account at console.anthropic.com (if not already done)
- [ ] Generate an API key
- [ ] Note the key securely — it goes in `.env` as `ANTHROPIC_API_KEY`
- [ ] Confirm you have API credits available (new accounts get $5 free)

**0c — Discord bot application**
- [ ] Go to discord.com/developers/applications
- [ ] Create a new application (name: "GURPS GM" or similar)
- [ ] Go to Bot tab, create a bot, copy the token
- [ ] Note the token securely — it goes in `.env` as `AI_DM_BOT_KEY`
- [ ] Under OAuth2 > URL Generator: select `bot` scope, select permissions: Send Messages, Manage Threads, Read Message History, Use Slash Commands, Embed Links
- [ ] Use the generated URL to invite the bot to your Discord server

**0d — Repository and project structure**
- [ ] `mkdir ~/gurps-gm && cd ~/gurps-gm && git init`
- [ ] Create full directory structure (all dirs from Project Structure above)
- [ ] Add `__init__.py` to each Python package dir
- [ ] Copy spec into `docs/blueprint.md`
- [ ] Place `CLAUDE.md` in repo root

**0e — Python environment**
- [ ] Create venv: `python3 -m venv venv`
- [ ] Activate: `source venv/bin/activate`
- [ ] Create initial `requirements.txt` with Phase 1-2 deps (discord.py, pytest, pydantic, python-dotenv, pyyaml)
- [ ] `pip install -r requirements.txt`

**0f — Config scaffolding**
- [ ] Create `.env` with `AI_DM_BOT_KEY` and `ANTHROPIC_API_KEY` placeholders
- [ ] Create `.gitignore` (include: .env, venv/, saves/, rag_index/, __pycache__/, *.pyc)
- [ ] Create `config.yaml` with structure from spec Section 9
- [ ] Create placeholder `main.py` that loads config and prints "Bot starting..."

**0g — First commit**
- [ ] `git add -A && git commit -m "phase-0: initial project scaffolding"`
- [ ] Verify: `git log --oneline` shows one clean commit
- [ ] **Start a new session.** Phase 0 is done.

## Common Mistakes to Avoid
- DO NOT let the LLM output override engine results. If the engine says "miss", the narration says "miss".
- DO NOT split GURPS tables across chunks during RAG ingestion. Tables must stay intact.
- DO NOT use raw player messages as vector search queries. Always use structured queries via the action classifier.
- DO NOT put GURPS rules logic in the LLM prompts. Put it in engine/ as Python.
- DO NOT modify files outside the current phase's scope without explicit discussion.
- DO NOT run only new tests. Always run the full suite.
