**GURPS AI Game Master**  
Architecture & Implementation Blueprint

*A Discord Bot with Structured RAG, Deterministic Rules Engine, and Multi-Player Campaign Management*

Version 1.0 — March 2026

# **1\. Project Overview**

This document is a complete technical blueprint for building a GURPS 4th Edition AI Game Master that runs as a Discord bot. It is designed to be handed to an AI coding assistant (or a human developer) as a self-contained specification. Every architectural decision, data structure, module interface, and implementation sequence is defined here.

## **1.1 Design Philosophy**

The core insight driving this architecture is separation of concerns between three distinct responsibilities:

* **The LLM narrates and interprets:** It reads player input, decides what mechanical actions to resolve, describes the results, and advances the story. It never does math.

* **The rules engine computes:** All dice rolls, success/failure checks, damage calculations, and state mutations happen in deterministic Python code. The LLM cannot override or fudge these results.

* **The RAG layer provides rules knowledge:** When the LLM needs to know how a specific GURPS rule works, it gets the exact text from a structured index — not from its training data, which is unreliable for GURPS specifics.

This separation is what makes the GM trustworthy. Players will test the system by attempting unusual maneuvers, edge-case advantage interactions, and creative tactics. If the LLM is doing mental math on damage reduction, it will get it wrong. If the rules engine handles it, it will be correct every time.

## **1.2 Target Architecture Summary**

| Layer | Responsibility | Technology |
| :---- | :---- | :---- |
| Discord Interface | Message routing, threading, permissions | discord.py |
| Game Orchestrator | Turn flow, player management, session lifecycle | Python (custom) |
| LLM Controller | Prompt assembly, LLM calls, response parsing | LiteLLM or direct API |
| Rules Engine | Dice, combat, skills, advantages, damage | Python (deterministic) |
| RAG Index | GURPS rules retrieval with structured queries | LlamaIndex \+ ChromaDB |
| State Manager | Characters, scenes, campaign persistence | SQLite \+ in-memory cache |

# **2\. Project Structure**

The repository follows a strict modular layout. Every component lives in its own directory with a clear interface boundary. No module should import from another module’s internal files — only from its public interface (typically \_\_init\_\_.py exports).

## **2.1 Directory Layout**

gurps-gm/

├── bot/                    \# Discord interface layer

│   ├── \_\_init\_\_.py

│   ├── client.py           \# Discord client, event handlers

│   ├── commands.py         \# Slash commands (/roll, /status, /newchar)

│   ├── threads.py          \# Thread creation and scene management

│   └── formatters.py       \# Discord embed builders

├── orchestrator/           \# Game flow controller

│   ├── \_\_init\_\_.py

│   ├── game\_loop.py        \# Main turn processing pipeline

│   ├── action\_parser.py    \# Classifies player intent into action types

│   └── session.py          \# Session start/stop/save/load

├── llm/                    \# LLM interaction layer

│   ├── \_\_init\_\_.py

│   ├── controller.py       \# Prompt assembly, API calls, response parsing

│   ├── prompts/            \# All prompt templates (Jinja2 or plain text)

│   │   ├── base\_gm.txt        \# Core GM personality

│   │   ├── combat\_context.txt \# Injected during combat

│   │   ├── social\_context.txt \# Injected during social encounters

│   │   ├── action\_classify.txt \# For the action parser

│   │   └── summarize.txt      \# Session summary generator

│   └── response\_parser.py  \# Extracts structured data from LLM output

├── engine/                 \# Deterministic GURPS rules engine

│   ├── \_\_init\_\_.py

│   ├── dice.py             \# All dice rolling functions

│   ├── skills.py           \# Skill checks, contests, defaults

│   ├── combat.py           \# Attack, defense, damage, conditions

│   ├── advantages.py       \# Advantage/disadvantage effect registry

│   ├── magic.py            \# Spell casting (if campaign uses magic)

│   └── tables.py           \# Lookup tables (size/speed, range, hit location)

├── rag/                    \# Structured GURPS knowledge retrieval

│   ├── \_\_init\_\_.py

│   ├── ingest.py           \# PDF/text chunking and indexing

│   ├── query.py            \# Structured query builder

│   └── index\_config.py     \# ChromaDB/LlamaIndex configuration

├── state/                  \# Campaign and character persistence

│   ├── \_\_init\_\_.py

│   ├── character.py        \# Character data model

│   ├── scene.py            \# Scene state tracking

│   ├── campaign.py         \# Campaign-level persistence

│   └── db.py               \# SQLite interface

├── data/

│   ├── gurps/              \# Your GURPS PDF/text source files

│   └── settings/           \# Campaign-specific setting files

├── rag\_index/              \# Persisted vector index (gitignored)

├── saves/                  \# Campaign save files (gitignored)

├── tests/                  \# Unit tests per module

├── .env                    \# API keys (gitignored)

├── config.yaml             \# Bot and game configuration

├── main.py                 \# Entry point

└── requirements.txt

# **3\. Rules Engine (engine/)**

This is the mechanical heart of the system. Every function in this module is pure, deterministic Python (except for the random dice rolls). The LLM never performs calculations — it requests them from the engine and narrates the results.

## **3.1 Core Dice Module (engine/dice.py)**

All randomness in GURPS flows through 3d6. This module provides every roll type the system needs.

### **Functions to Implement**

| Function | Parameters | Returns |
| :---- | :---- | :---- |
| roll\_3d6() | None | RollResult(total, dice\[3\], is\_critical\_success, is\_critical\_failure) |
| success\_check(skill\_level) | int | CheckResult(roll, target, margin, success, critical) |
| quick\_contest(skill\_a, skill\_b) | int, int | ContestResult(roll\_a, roll\_b, margin\_a, margin\_b, winner) |
| damage\_roll(dice\_str) | '2d+1', '1d-1', etc. | int (minimum 1 for crushing, 0 allowed for other) |
| reaction\_roll(modifiers) | list\[int\] | ReactionResult(total, level\_name) |
| fright\_check(will, modifier) | int, int | FrightResult(roll, margin, table\_result) |

### **Critical Success/Failure Thresholds**

These must be exact per GURPS B348. Do not let the LLM decide what counts as critical.

* Critical Success: Roll of 3 or 4 always. Roll of 5 if effective skill is 15+. Roll of 6 if effective skill is 16+.

* Critical Failure: Roll of 18 always. Roll of 17 if effective skill is 15 or less. Any roll that fails by 10+ on a success roll.

## **3.2 Combat Module (engine/combat.py)**

Combat is where GURPS complexity peaks and where the rules engine earns its keep. This module handles the full attack-defense-damage-injury pipeline.

### **Attack Resolution Pipeline**

Every attack flows through this exact sequence. Implement each step as a separate function so they can be tested independently:

* Step 1 — Attack Roll: success\_check(effective\_skill) where effective\_skill \= base\_skill \+ maneuver\_modifier \+ range\_modifier \+ size\_modifier \+ situation\_modifiers.

* Step 2 — Defense Roll: If attack succeeds, defender chooses active defense. Dodge \= success\_check(dodge\_score). Parry \= success\_check(parry\_score). Block \= success\_check(block\_score). Some attacks allow no defense.

* Step 3 — Hit Location: If no specific target was declared, roll 3d6 on the hit location table (B552). If attacker targeted a specific location, apply the hit penalty to the attack roll (already included in Step 1).

* Step 4 — Damage Roll: Roll the weapon’s damage dice (e.g., 2d+1 cutting). This is raw damage before DR.

* Step 5 — Damage Resistance: Subtract the target’s DR for the hit location. If result is 0 or less, no penetration (exception: minimum 1 for crushing).

* Step 6 — Injury Calculation: Multiply penetrating damage by the wound modifier for the damage type and hit location. Cutting to torso \= x1.5. Impaling to torso \= x2. Crushing to skull \= x4. This is the actual HP lost.

* Step 7 — Wound Effects: Check for knockdown (HT roll if injury \> HP/2 in one hit), stunning (automatic for head hits over HP/10), major wounds (B420), and death checks (at \-1xHP, \-2xHP, etc.).

### **Data Structures**

Define these as Python dataclasses or Pydantic models. The LLM receives them as formatted text; the engine works with them as typed objects.

@dataclass

class AttackAction:

    attacker\_id: str

    target\_id: str

    weapon: Weapon

    maneuver: str          \# 'attack', 'all\_out\_attack\_strong', 'deceptive\_attack', etc.

    target\_location: str   \# 'torso', 'skull', 'arm', etc. or 'random'

    modifiers: list\[Modifier\]  \# situational mods

@dataclass

class CombatResult:

    attack\_roll: CheckResult

    defense\_roll: Optional\[CheckResult\]

    defense\_type: Optional\[str\]

    hit\_location: str

    raw\_damage: int

    dr: int

    penetrating\_damage: int

    wound\_modifier: float

    injury: int

    effects: list\[str\]     \# \['knockdown\_check', 'stunned', 'death\_check\_1'\]

### **Maneuver Registry**

Implement a dictionary mapping maneuver names to their mechanical effects. This is critical because players will attempt every maneuver in the book and the LLM needs to know what modifiers to apply.

| Maneuver | Attack Modifier | Defense Effect | Notes |
| :---- | :---- | :---- | :---- |
| Attack | \+0 | Normal defenses | Standard action |
| All-Out Attack (Strong) | \+0 | No active defense this turn | \+2 damage or \+1 per die |
| All-Out Attack (Determined) | \+4 | No active defense this turn | Best for low-skill fighters |
| All-Out Defense (Dodge) | Cannot attack | \+2 to Dodge | Can Dodge multiple times |
| Deceptive Attack | \-N to skill | Defender gets \-N/2 to defense | N chosen by attacker, min 2 |
| Feint | Quick Contest | Margin applied as defense penalty | Uses one maneuver |
| Move and Attack | \-4 (or \-2 with technique) | Normal defenses | Effective skill capped at 9 |
| Wait/Trigger | \+0 | Normal defenses | Interrupts on condition |

## **3.3 Lookup Tables (engine/tables.py)**

GURPS uses several reference tables that must be implemented as data, not computed by the LLM. Store these as Python dictionaries or lookup functions.

* Hit Location Table (B552): Maps 3d6 roll to body part, DR modifier, wound multiplier per damage type.

* Size and Speed/Range Table (B550): Maps linear measurement to modifier. Used constantly in ranged combat.

* Fright Check Table (B360): Maps margin of failure to fright effect.

* Reaction Table (B560-561): Maps reaction roll total to NPC disposition.

* Critical Hit Table (B556): Maps roll to critical hit effect.

* Critical Miss Table (B556): Maps roll to critical miss effect.

* Critical Head Blow Table (B556): Separate table for head hits.

# **4\. Structured RAG System (rag/)**

This is the most important architectural difference from a naive implementation. The goal is not “search GURPS PDFs for relevant text” — it is “retrieve the exact rule that governs this specific mechanical situation.”

## **4.1 Chunking Strategy**

Do not use default chunking (split every N tokens). GURPS rules have structure that must be preserved. Use a custom chunking approach:

* **Chapter-aware splitting:** Each chunk belongs to exactly one chapter/section. Never split a rule explanation across chunks.

* **Metadata tags on every chunk:** Each chunk gets tagged with: source\_book, chapter, section, topic\_type (one of: advantage, disadvantage, skill, spell, combat\_maneuver, equipment, general\_rule, table, example), and keywords.

* **Table preservation:** Tables must be kept intact as single chunks. A hit location table split across two chunks is useless.

* **Cross-reference linking:** When a chunk says “see p. B420”, add that page reference as metadata so the retrieval system can pull both chunks.

## **4.2 Ingestion Pipeline (rag/ingest.py)**

The ingestion script should process your GURPS source material in this order:

* Step 1: Extract text from PDFs (use pymupdf or pdfplumber for table-aware extraction).

* Step 2: Parse section headers to identify chapter/section boundaries.

* Step 3: Classify each section by topic\_type using pattern matching (advantage names are Title Case with point costs in brackets, skills have attribute/difficulty notations, etc.).

* Step 4: Generate metadata tags for each chunk.

* Step 5: Build the vector index with metadata stored alongside embeddings.

* Step 6: Build a separate keyword index (BM25 or similar) for exact-match lookups like advantage names.

## **4.3 Structured Query Builder (rag/query.py)**

This is the critical innovation. The player’s chat message should never be used as a raw vector search query. Instead, the system should:

* Step 1: The LLM (via the action\_classify prompt) identifies what rule knowledge is needed. For example, a player saying “I try a Deceptive Attack to the skull” generates a structured query: {topic\_type: 'combat\_maneuver', keywords: \['Deceptive Attack'\], related: \['hit\_location', 'skull'\]}.

* Step 2: The query builder translates this into a metadata-filtered vector search. First filter by topic\_type, then search by keyword similarity within that subset.

* Step 3: Follow cross-references. If the returned chunk references another rule, pull that chunk too.

* Step 4: Return the retrieved text formatted for injection into the LLM prompt.

## **4.4 Hybrid Retrieval**

Use both vector search (for semantic similarity) and keyword search (for exact matches). When a player mentions “Combat Reflexes”, you want the exact advantage description, not the five most semantically similar paragraphs. The keyword index handles this; the vector index handles fuzzier queries like “what happens when I fall off a building.”

Implementation: Use ChromaDB with metadata filtering for the vector layer, and a simple BM25 index (rank\_bm25 Python package) for the keyword layer. Merge results with keyword matches ranked higher when exact matches exist.

# **5\. State Management (state/)**

GURPS characters are complex objects with many interacting properties. The state system must track everything the rules engine needs to resolve any action, and present it to the LLM in a format that fits within context limits.

## **5.1 Character Data Model (state/character.py)**

Every player character and significant NPC needs a persistent character object. Define this as a Pydantic model for validation and serialization.

### **Required Fields**

| Category | Fields | Notes |
| :---- | :---- | :---- |
| Identity | name, player\_discord\_id, point\_total | Links character to Discord user |
| Primary Attributes | ST, DX, IQ, HT | Integer values, typically 8–18 |
| Secondary Attributes | HP, FP, Will, Per, Basic Speed, Basic Move | Derived but can be bought up/down |
| Current State | current\_hp, current\_fp, conditions\[\] | Conditions: stunned, prone, unconscious, etc. |
| Skills | dict\[str, SkillEntry\] | SkillEntry: level, attribute, difficulty, defaults\[\] |
| Advantages/Disadvs | list\[Advantage\] | Each has name, level, point\_cost, mechanical\_effects |
| Equipment | list\[Item\] | Item has name, weight, DR (if armor), damage (if weapon), location |
| Combat Stats | dodge, parry\_skills\[\], block\_skill | Calculated from attributes \+ equipment |
| Active Effects | list\[ActiveEffect\] | Temporary: All-Out Attack, feint penalty, spell duration |

### **Character State Serialization**

The character object needs two serialization formats:

* **Full JSON (for SQLite storage):** Complete data with all fields. Used for save/load.

* **LLM Summary (for prompt injection):** A condensed text block that gives the LLM everything it needs to narrate without overwhelming the context. Example format:

\[Bjorn Ironhand\] ST 14 DX 12 IQ 10 HT 12 | HP 14/14 FP 12/12

Skills: Broadsword-14, Shield-13, Brawling-13, Stealth-11

Advantages: Combat Reflexes, High Pain Threshold

Equipment: Broadsword (2d+1 cut / 1d+2 cr), Medium Shield (DB 2), Chain Mail (DR 4/2\*)

Dodge 10, Parry 11 (Broadsword), Block 11

Status: healthy, no active effects

## **5.2 Scene State (state/scene.py)**

The scene state is rebuilt every turn and injected into the LLM prompt. It is the LLM’s primary source of truth about what is happening right now.

### **Scene State Structure**

@dataclass

class SceneState:

    scene\_id: str

    description: str            \# Current scene narration

    scene\_type: str             \# 'combat', 'exploration', 'social', 'downtime'

    characters\_present: list\[CharacterSummary\]

    recent\_actions: list\[ActionRecord\]   \# Last 5 turns

    active\_effects: list\[str\]            \# Environmental: darkness, rain, etc.

    combat\_state: Optional\[CombatState\]  \# Only during combat

@dataclass

class CombatState:

    round\_number: int

    turn\_order: list\[str\]       \# Character IDs sorted by Basic Speed

    current\_turn: str           \# Who is acting now

    active\_maneuvers: dict      \# character\_id \-\> declared maneuver this turn

    position\_notes: str         \# Relative positions (narrative, not grid)

## **5.3 Campaign Persistence (state/campaign.py \+ state/db.py)**

Use SQLite for all persistence. It is file-based (perfect for Pi), requires no server, and handles concurrent reads well enough for a Discord bot.

### **Database Schema**

| Table | Purpose | Key Fields |
| :---- | :---- | :---- |
| characters | All PC and NPC character data | id, name, discord\_user\_id, data\_json, campaign\_id |
| campaigns | Campaign metadata | id, name, setting, created\_at, gm\_discord\_id |
| scenes | Scene history | id, campaign\_id, description, scene\_type, created\_at |
| action\_log | Complete action history | id, scene\_id, character\_id, action\_json, result\_json, timestamp |
| session\_summaries | LLM-generated summaries | id, campaign\_id, summary\_text, message\_range, created\_at |
| custom\_rules | GM house rules and setting rules | id, campaign\_id, rule\_name, rule\_text |

### **Session Summary System**

Every 15–20 messages, the system should automatically generate a session summary using the LLM. This summary replaces older conversation history in the context window, preventing context overflow while preserving narrative continuity. The summary prompt should instruct the LLM to capture: what happened (plot events), mechanical changes (HP lost, items used, conditions gained), NPC relationships changed, and any unresolved situations.

# **6\. LLM Controller (llm/)**

The LLM layer is the interface between structured game data and natural language. Its job is prompt assembly, API communication, and response parsing. It should be model-agnostic — switching from one LLM provider to another should require changing one configuration value.

## **6.1 Prompt Architecture**

Instead of one monolithic system prompt, use a layered prompt that is assembled fresh each turn. This gives precise control over what the LLM knows and prioritizes.

### **Prompt Layers (assembled in this order)**

| Layer | Source | When Included | Approx Tokens |
| :---- | :---- | :---- | :---- |
| 1\. Base GM Personality | prompts/base\_gm.txt | Always | 300–500 |
| 2\. Setting Context | campaign.setting field | Always | 200–400 |
| 3\. GURPS Rules (RAG) | Retrieved chunks | When rules are needed | 500–1500 |
| 4\. Scene State | SceneState object | Always | 200–600 |
| 5\. Character Summaries | Active characters | Always | 100–300 per character |
| 6\. Session Summary | Latest auto-summary | Always (replaces old history) | 300–500 |
| 7\. Recent Messages | Last 5–10 turns | Always | 500–1500 |
| 8\. Current Turn Context | Player message \+ action parse | Always | 100–300 |

### **Base GM Prompt (prompts/base\_gm.txt)**

This prompt defines personality and behavioral rules. Keep it focused on GM behavior, not rules mechanics (the engine handles those).

You are a Game Master for a GURPS 4th Edition campaign. Your responsibilities:

NARRATION: Describe scenes vividly but concisely. Use all senses. Keep responses

under 300 words unless a dramatic moment warrants more.

MECHANICAL HONESTY: When the rules engine provides results (dice rolls, damage,

success/failure), report them exactly. Show the numbers. Never fudge or reinterpret

mechanical results. Say 'You rolled a 14 against your Broadsword-13, missing by 1.'

PLAYER AGENCY: Always ask what the player wants to do. Never take actions for PCs.

NPCs act based on their established personality and the situation.

RULE REFERENCES: When RAG results are provided, use them to adjudicate correctly.

If no RAG result is available and you are unsure of a rule, say so and make a

reasonable ruling, flagging it as a house ruling.

STRUCTURED OUTPUT: When you need the rules engine to resolve something, output a

JSON block tagged with \`\`\`engine\_request\`\`\` containing the action to resolve.

When narrating results, include a \`\`\`scene\_update\`\`\` JSON block with any state

changes (HP lost, conditions gained, items used, etc.).

## **6.2 Action Classification**

Before the main GM prompt runs, a lightweight LLM call classifies the player’s message into an action type. This determines what rules to retrieve and whether the engine needs to be invoked.

| Action Type | Examples | Engine Needed? | RAG Needed? |
| :---- | :---- | :---- | :---- |
| combat\_attack | 'I swing at the orc', 'I shoot him' | Yes | If unusual maneuver |
| combat\_defense | 'I dodge', 'I parry with my shield' | Yes | Rarely |
| skill\_check | 'I pick the lock', 'I try to persuade him' | Yes | If skill is unusual |
| dialogue | 'I say: We come in peace' | No | No |
| exploration | 'I search the room', 'I open the door' | Maybe (Per check) | No |
| character\_action | 'What are my stats?', 'I use a healing potion' | Maybe | If advantage/item question |
| meta | 'What happened last session?', 'Can I retcon?' | No | No |
| rules\_question | 'How does Deceptive Attack work?' | No | Yes |

## **6.3 Engine Request/Response Protocol**

The LLM communicates with the rules engine through structured JSON blocks embedded in its output. The orchestrator parses these, runs them through the engine, and feeds results back.

### **Example Flow**

Player says: “I do a Deceptive Attack (-4) at the goblin’s skull with my broadsword.”

LLM outputs:

\`\`\`engine\_request

{

  "action": "attack",

  "attacker": "bjorn",

  "target": "goblin\_1",

  "weapon": "broadsword",

  "maneuver": "deceptive\_attack",

  "deceptive\_penalty": 4,

  "target\_location": "skull"

}

\`\`\`

The orchestrator runs this through the engine, gets a CombatResult, and feeds it back to the LLM as:

ENGINE RESULT: Attack roll 9 vs effective skill 10 (Broadsword 14, \-4 deceptive,

\-7 skull, \+3 from Combat Reflexes bonus does not apply to attack). SUCCESS by 1\.

Goblin defends: Dodge roll 12 vs effective Dodge 6 (base 8, \-2 deceptive penalty).

FAILURE. Hit location: Skull. Damage roll: 2d+1 cut \= 9\. DR 2 (skull). Penetrating

damage: 7\. Wound modifier x4 (skull, cutting). Injury: 28 HP. Goblin is at \-20 HP.

Death check required at \-1xHP, \-2xHP, \-3xHP, \-4xHP. Automatic death at \-5xHP (8).

The LLM then narrates this dramatically while including the mechanical details.

# **7\. Discord Interface (bot/)**

The Discord layer handles all communication with players. It should be a thin layer that routes messages to the orchestrator and formats responses for Discord.

## **7.1 Channel Architecture**

| Channel/Thread | Purpose | Who Sees It |
| :---- | :---- | :---- |
| \#game-session | Main game channel | All players |
| Scene threads (auto-created) | Active scene play | All players in scene |
| DM with bot | Private GM notes, secret rolls, player secrets | Individual player only |
| \#gm-log (optional) | Raw engine output, debug info | GM only |

## **7.2 Slash Commands**

| Command | Parameters | Effect |
| :---- | :---- | :---- |
| /roll | dice\_expression (e.g., '3d6', '2d+1') | Rolls dice publicly with result |
| /skill | skill\_name, modifier (optional) | Makes a skill check for your character |
| /status | None | Shows your character summary embed |
| /newchar | name | Starts character creation wizard (DM conversation) |
| /scene | description | GM only: starts a new scene thread |
| /combat\_start | None | GM only: initiates combat, rolls initiative |
| /combat\_end | None | GM only: ends combat mode |
| /save | None | GM only: forces a save checkpoint |
| /recap | None | Shows the latest session summary |

## **7.3 Response Formatting**

Discord has a 2000-character message limit. For longer GM responses, split into multiple messages: narrative first, then mechanical results in a separate embed. Use Discord embeds for structured data like character sheets, combat results, and status updates.

### **Embed Templates**

* Combat Result Embed: Shows attacker, defender, rolls, damage, and outcome in a color-coded embed (green \= hit, red \= miss, yellow \= critical).

* Character Status Embed: Shows HP/FP bars, active conditions, and key stats.

* Skill Check Embed: Shows skill name, effective level, roll, margin, and result.

# **8\. Game Orchestrator (orchestrator/)**

The orchestrator is the central coordinator. It receives a player message, determines what needs to happen, invokes the right components in the right order, and sends the result back through Discord.

## **8.1 Main Turn Processing Pipeline**

Every player message goes through this pipeline:

* Step 1 — Receive: Discord message arrives. Extract player ID, channel context, and message content.

* Step 2 — Load State: Fetch the player’s character, current scene state, and combat state (if in combat) from the state manager.

* Step 3 — Classify Action: Send the message to the action classifier (lightweight LLM call). Get back an action type and any identified mechanical parameters.

* Step 4 — Retrieve Rules (if needed): Based on the action classification, query the RAG system for relevant GURPS rules.

* Step 5 — Assemble Prompt: Build the full layered prompt with all context: GM personality, setting, rules, scene state, character summaries, recent history, and the current action.

* Step 6 — LLM Call: Send the assembled prompt to the LLM. Parse the response for engine\_request blocks and scene\_update blocks.

* Step 7 — Execute Engine Requests: If the LLM output contains engine\_request blocks, run them through the rules engine. Collect results.

* Step 8 — Second LLM Call (if engine was invoked): Feed the engine results back to the LLM for narration. This is a short follow-up call, not a full prompt rebuild.

* Step 9 — Update State: Apply any scene\_update changes to the state manager. Save character changes, update scene description, log the action.

* Step 10 — Send Response: Format the LLM’s narration and any mechanical results into Discord messages/embeds. Send them to the appropriate channel/thread.

* Step 11 — Auto-Summary Check: If the message count since the last summary exceeds the threshold (15–20), trigger an async summary generation.

## **8.2 Combat Turn Management**

When combat is active, the orchestrator enforces turn order:

* Initiative is determined by Basic Speed (highest goes first). Ties broken by DX, then random.

* On each character’s turn, the bot prompts them for their maneuver choice.

* If a player takes too long (configurable timeout, suggest 5 minutes), the bot sends a reminder. After 10 minutes, the character takes a Do Nothing maneuver.

* NPC turns are handled by the LLM, using the NPC’s stats and personality to decide actions. The engine still resolves all rolls.

* After all characters have acted, increment the round counter and start the next round.

# **9\. Configuration (config.yaml)**

All tunable parameters live in a single YAML file. No magic numbers in code.

\# config.yaml

bot:

  discord\_token\_env: AI\_DM\_BOT\_KEY

  command\_prefix: /

  main\_channel: game-session

llm:

  provider: anthropic          \# or openai, xai (grok)

  model: claude-sonnet-4-20250514

  api\_key\_env: ANTHROPIC\_API\_KEY

  max\_tokens: 1500

  temperature: 0.7

  classifier\_model: claude-haiku-4-5-20251001  \# cheaper model for action classification

rag:

  index\_path: rag\_index/gurps

  top\_k: 5

  use\_hybrid: true             \# vector \+ keyword search

  chunk\_max\_tokens: 512

game:

  system: gurps4e

  setting: generic\_fantasy      \# or custom setting name

  auto\_summary\_interval: 20     \# messages between auto-summaries

  combat\_turn\_timeout: 300      \# seconds before reminder

  combat\_afk\_timeout: 600       \# seconds before auto-Do Nothing

  max\_recent\_messages: 8        \# conversation history in prompt

state:

  db\_path: saves/campaign.db

  backup\_interval: 3600         \# seconds between auto-backups

# **10\. Implementation Order**

Build in this exact sequence. Each phase produces a testable, working system. Do not skip ahead. Each phase should be a separate git branch merged to main only when stable.

## **Phase 1: Skeleton (Day 1\)**

* Set up the repository with the directory structure from Section 2\.

* Implement main.py with basic Discord bot connection using discord.py.

* Bot responds to messages in the game channel with a hardcoded reply.

* Set up .env handling, config.yaml loading, and basic logging.

**Test:** Bot comes online, responds to a message. Commit.

## **Phase 2: Rules Engine Core (Day 1–2)**

* Implement engine/dice.py with all roll functions and unit tests.

* Implement engine/tables.py with hit location and critical tables.

* Implement engine/combat.py with the full attack resolution pipeline.

* Write unit tests for every function. Test edge cases: critical hits, minimum damage, death checks.

**Test:** Run pytest. Every mechanical function produces correct GURPS results. Commit.

## **Phase 3: State System (Day 2\)**

* Implement state/character.py with the full character data model.

* Implement state/db.py with SQLite schema creation and CRUD operations.

* Implement state/scene.py with scene state tracking.

* Create 2–3 test characters as JSON fixtures.

**Test:** Create characters, save to DB, load them back, verify all fields. Commit.

## **Phase 4: Basic LLM Integration (Day 2–3)**

* Implement llm/controller.py with prompt assembly and API calls.

* Write the base\_gm.txt prompt.

* Wire the Discord bot to send player messages through the LLM controller and return responses.

* No engine integration yet — just conversation.

**Test:** Chat with the bot in Discord. It responds in character as a GURPS GM. Commit.

## **Phase 5: Orchestrator \+ Engine Integration (Day 3–4)**

* Implement orchestrator/game\_loop.py with the full pipeline from Section 8\.

* Implement orchestrator/action\_parser.py with the classification prompt.

* Implement llm/response\_parser.py to extract engine\_request and scene\_update blocks.

* Wire the engine into the orchestrator: LLM requests mechanical resolution, engine computes, result feeds back.

**Test:** Player attacks an NPC in Discord. Bot rolls dice, calculates damage correctly, narrates the result. Commit.

## **Phase 6: RAG System (Day 4–5)**

* Implement rag/ingest.py with structured chunking for your GURPS PDFs.

* Implement rag/query.py with metadata-filtered hybrid retrieval.

* Run ingestion on your GURPS source material.

* Wire RAG into the orchestrator: action classifier triggers rule retrieval when needed.

**Test:** Ask the bot 'How does Deceptive Attack work?' It retrieves the correct rule and explains it accurately. Commit.

## **Phase 7: Multi-Player \+ Threading (Day 5–6)**

* Implement bot/threads.py for auto-thread creation on new scenes.

* Implement combat turn ordering in the orchestrator.

* Add DM handling for private rolls and player secrets.

* Test with 2–3 Discord accounts (or test accounts).

**Test:** Run a 3-round combat with 2 players. Turn order is correct, each player acts in sequence, results are mechanically accurate. Commit.

## **Phase 8: Polish \+ Deploy (Day 6–7)**

* Implement all slash commands from Section 7.2.

* Add Discord embed formatters for combat results, character status, and skill checks.

* Implement auto-session summaries.

* Set up systemd service on the Raspberry Pi (same approach as your original plan).

* Run a full test session with friends.

**Test:** Complete a full evening game session with real players. Identify and log issues for iteration. Commit.

# **11\. Extensibility Points**

After the core system is working, these are the most valuable additions, in priority order:

## **11.1 Custom Settings and House Rules**

The custom\_rules database table allows the GM to teach the bot setting-specific or house rules. These get loaded into the prompt as an additional layer between the base GM personality and the RAG results. Example: “In this campaign, magic costs double FP” or “This setting uses the TL8 equipment list.” A slash command /houserule add \<rule\_text\> writes to this table.

## **11.2 Character Creation Wizard**

A DM-based interactive flow that walks a player through GURPS character creation: choosing attributes, advantages, disadvantages, and skills within a point budget. The engine validates point costs; the LLM provides guidance and suggestions based on the campaign setting. This is complex but high-value since GURPS character creation is one of the biggest barriers for new players.

## **11.3 NPC Generation**

A system for the LLM to generate stat blocks for NPCs on the fly, using the engine to validate point costs and the RAG layer to pull appropriate templates. Store generated NPCs in the characters table for reuse.

## **11.4 Map/Position Tracking**

For tactical combat, a simple hex/grid overlay sent as an image embed in Discord. This is a significant undertaking and should only be attempted after the text-based combat system is rock-solid. Consider using Pillow to render a simple grid with character positions.

## **11.5 Multi-Campaign Support**

The database schema already supports multiple campaigns. The Discord interface would need a /campaign switch \<name\> command and per-channel campaign binding. This is straightforward once the single-campaign flow is stable.

# **12\. Known Failure Modes and Mitigations**

These are the most likely ways the system will break during real play. Plan for them.

| Failure Mode | Symptom | Mitigation |
| :---- | :---- | :---- |
| Context window overflow | LLM starts forgetting earlier events or characters | Auto-summary system (Section 5.3). Monitor token count per prompt. Alert GM if approaching limit. |
| RAG retrieves wrong rule | Bot applies wrong modifier or misunderstands a rule | Structured queries with metadata filtering. Keyword search for exact matches. Allow GM override with /ruling command. |
| LLM ignores engine results | Bot narrates a hit as a miss or changes damage numbers | Parser validates that the narration includes the engine result numbers. Flag discrepancies in \#gm-log. |
| LLM invents rules | Bot describes a mechanic that doesn't exist in GURPS | System prompt explicitly forbids rule invention. RAG results are labeled as authoritative. Flag when no RAG result is found. |
| Player confusion about turns | Players post out of turn in combat | Bot enforces turn order: only processes messages from the current turn's player during combat. Politely reminds others to wait. |
| API rate limits or outages | Bot stops responding | Implement retry with exponential backoff. Cache the last scene state. Show a friendly 'thinking...' status. |
| Database corruption | Character data lost | Auto-backup every hour. WAL mode for SQLite. On corruption, restore from backup. |

# **13\. Testing Strategy**

Each module has its own test requirements. Tests should be written alongside implementation, not after.

## **13.1 Unit Tests (tests/)**

* **engine/dice.py:** Test all roll functions. Verify critical success/failure thresholds against B348. Run 10,000 rolls to verify distribution.

* **engine/combat.py:** Test the full attack pipeline with known inputs. Verify every step: attack roll, defense, hit location, damage, DR, injury, wound effects. Test edge cases: DR higher than damage, crushing minimum 1, skull wound multiplier.

* **engine/tables.py:** Verify every lookup table against the book. Particularly important for hit location and critical tables.

* **state/character.py:** Test serialization/deserialization. Verify that derived stats (dodge, parry) are calculated correctly from attributes and equipment.

* **rag/query.py:** Test that structured queries return the correct chunks for known rules. Test edge cases: rules that span multiple chunks, cross-references.

## **13.2 Integration Tests**

* **Orchestrator pipeline:** Feed a canned player message through the full pipeline (classify → retrieve → LLM → engine → narrate). Verify the output contains correct mechanical results.

* **Multi-turn combat:** Simulate a 3-round combat between 2 characters. Verify turn order, HP tracking, condition application, and death check triggers.

* **Session persistence:** Start a session, make changes, save, restart the bot, load — verify all state is preserved.

## **13.3 Playtesting Protocol**

Before each play session with real players, run through this checklist:

* Create a test combat with a pre-built character vs. a simple NPC. Verify attack, defense, and damage flow.

* Ask the bot a rules question that requires RAG retrieval. Verify accuracy.

* Check that /status, /roll, and /skill commands all work.

* Verify that the session summary from the last session loads correctly.

* Confirm the bot is running on the Pi with systemctl status gurps-gm.