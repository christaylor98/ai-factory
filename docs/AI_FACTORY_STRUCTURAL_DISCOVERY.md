# AI-Factory Full Structural Discovery

**Discovery Type:** Analysis Prompt - Rewrite Preparation  
**Status:** Non-Destructive  
**Date:** 2026-02-13  
**Scope:** Complete structural and semantic analysis of ai-factory codebase

---

## Executive Summary

The ai-factory codebase is a **heavily layered workflow orchestration system** disguised as a prompt execution engine. The actual "prompt in → result out" path is buried under multiple levels of abstraction, document loading, state management, and orchestration logic.

**Key Finding:** The minimal prompt execution path requires ~50-100 lines of code, but the current implementation spans ~11,300 lines across 71 Python files with deep coupling to workflow engine remnants.

---

## File Tree Overview

```
src/ai_factory/
├── ai/                         # Provider abstraction (CORE)
│   ├── provider.py             # 228 lines - AI provider interface
│   └── prompts.py              # Prompt loading utilities
│
├── cli*.py                     # 5 CLI entrypoints (FRAGMENTED)
│   ├── cli.py                  # 481 lines - step-runner CLI
│   ├── cli_simple.py           # 47 lines - engine run/single-step
│   ├── cli_exec.py             # 260 lines - primitives CLI
│   ├── cli_engine_v1.py        # 101 lines - engine v1 CLI
│   └── cli_step_runner.py      # 90 lines - step-runner wrapper
│
├── director/                   # Workflow orchestration (ORCHESTRATION)
│   ├── autonomous.py           # 344 lines - autonomous execution core
│   └── director.py             # 186 lines - preflight + autonomous dispatch
│
├── discovery/                  # Discovery utilities (TOOLING)
│   └── __init__.py             # 364 lines
│
├── docs/                       # Document loading system (ORCHESTRATION)
│   ├── loader.py               # 176 lines - multi-doc loading + fingerprinting
│   ├── parser.py               # 216 lines - S-expression parser
│   └── validator.py            # 220 lines - document validation
│
├── engine.py                   # 768 lines - Full orchestrator (ORCHESTRATION)
├── engine_v1.py                # 63 lines - Pruned orchestrator remnant (LEGACY)
│
├── evaluation/                 # Task evaluation logic (ORCHESTRATION)
│   └── evaluator.py            # Task success/failure determination
│
├── execution/                  # Execution subsystem (MIXED)
│   ├── ai_executor.py          # 1057 lines - AI task execution with retries
│   ├── artifacts.py            # Artifact storage management
│   ├── command_validator.py    # Command validation rules
│   ├── confidence.py           # 218 lines - Confidence scoring
│   ├── escalation.py           # Escalation management
│   ├── executor.py             # 367 lines - Multi-provider AI execution
│   ├── logger.py               # AI call logging
│   ├── mode.py                 # Execution mode detection
│   ├── patch_apply.py          # 237 lines - Patch application logic
│   ├── risk.py                 # Risk acceptance framework
│   ├── runner.py               # Command execution primitives
│   ├── state.py                # Execution state tracking
│   ├── stop_conditions.py      # Stop condition checking
│   └── task_generator.py       # Task generation from AI responses
│
├── finops/                     # Cost tracking (INFRASTRUCTURE)
│   └── finops.py               # 235 lines - Cost derivation from ledger
│
├── ledger/                     # Ledger system (ORCHESTRATION)
│   ├── ledger.py               # 287 lines - LEDGER.is append-only log
│   └── build_step_tracker.py   # Build step completion tracking
│
├── planning/                   # Planning system (ORCHESTRATION)
│   ├── build_step_generator.py # 260 lines - Generate build steps from INTENT/REQUIREMENTS
│   ├── build_step_schema.py    # Build step data structures
│   ├── plan_guards.py          # Plan validation guards
│   ├── plan_parser.py          # PLAN.is parsing
│   ├── task_derivation.py      # Task derivation logic
│   ├── task_generator.py       # 406 lines - Generate tasks from PLAN.is
│   ├── task_schema.py          # Task data structures
│   └── validation.py           # Planning output validation
│
├── primitives/                 # File/command primitives (CORE)
│   ├── command_ops.py          # 129 lines - Command execution
│   └── file_ops.py             # 344 lines - File CRUD operations
│
├── requirements/               # Requirements parsing (TOOLING)
│   └── parser.py               # REQUIREMENTS.is parsing
│
├── status/                     # Status view (TOOLING)
│   └── status.py               # 772 lines - Workspace status display
│
├── step_runner/                # Step runner subsystem (MIXED)
│   ├── executors.py            # 596 lines - Shell/LLM execution
│   ├── jsonl_ledger.py         # JSONL ledger writer
│   ├── runner.py               # 366 lines - Sequential step execution
│   ├── step_parser.py          # 235 lines - Step document parsing
│   └── validation.py           # Step output validation
│
├── system_config.py            # 128 lines - System configuration (CORE)
│
├── tracking/                   # Completion tracking (ORCHESTRATION)
│   ├── build_steps.py          # Build step logging
│   └── requirements.py         # Requirement completion logging
│
├── traceability/               # Requirement tracing (TOOLING)
│   └── __init__.py             # 325 lines
│
└── util/                       # Utilities (INFRASTRUCTURE)
    └── __init__.py

17 directories, 71 files, 11,312 total lines
```

---

## Module Responsibility Map

### Core Prompt Execution (Minimal Path)
1. **ai/provider.py** - Direct model invocation (ClaudeProvider, OpenAIProvider)
2. **system_config.py** - Provider selection and credential loading
3. **step_runner/executors.py** - LLMExecutor with multi-provider support

### Workflow / Orchestration Remnants (Baggage)
1. **engine.py** - Full orchestrator with document gate, build_step generation, task execution loop
2. **director/director.py** - Preflight checks, autonomous core dispatch
3. **director/autonomous.py** - Task execution loop with stop conditions
4. **docs/loader.py** - Multi-document loading (ARCHITECTURE, REQUIREMENTS, INTENT, PLAN, PROCESS, IMPLEMENTATION)
5. **docs/validator.py** - Document consistency validation
6. **planning/build_step_generator.py** - AI-driven build step generation
7. **planning/task_generator.py** - PLAN.is-driven task generation
8. **planning/plan_parser.py** - PLAN.is parsing and build order extraction
9. **ledger/ledger.py** - Append-only ledger for all operations
10. **ledger/build_step_tracker.py** - Build step completion state
11. **tracking/** - Requirement and build step completion logs
12. **execution/state.py** - Execution state persistence
13. **execution/stop_conditions.py** - Stop condition detection
14. **evaluation/evaluator.py** - Task success evaluation

### Infrastructure / Support (Reusable)
1. **primitives/file_ops.py** - File CRUD with ledger integration
2. **primitives/command_ops.py** - Command execution with ledger integration
3. **execution/runner.py** - Low-level command execution
4. **execution/command_validator.py** - Command safety validation
5. **execution/artifacts.py** - Artifact storage management
6. **execution/logger.py** - AI call logging
7. **finops/finops.py** - Cost aggregation from ledger
8. **system_config.py** - Environment-based provider configuration

### Dead / Suspicious Code
1. **engine_v1.py** - Marked as "pruned" but still contains orchestration remnants
2. **cli_simple.py** - Duplicate CLI with only 2 commands (run, single-step)
3. **execution/confidence.py** - Complex confidence scoring unused in step-runner
4. **execution/escalation.py** - Escalation framework unused in step-runner
5. **execution/risk.py** - Risk acceptance framework unused in step-runner
6. **execution/mode.py** - Execution mode detection unused in step-runner
7. **Multiple CLI entrypoints** - 5 different CLI files with overlapping functionality

---

## Dependency Graph Summary

### Import Coupling Analysis

**High-Coupling Modules (imported by 5+ modules):**
- `ai_factory.ledger.ledger.Ledger` - 13 imports
- `ai_factory.ai.provider.AIProvider` - 8 imports
- `ai_factory.docs.loader.load_documents` - 6 imports

**Circular Dependencies:**
- None detected (good isolation at module level)

**Tight Coupling Patterns:**
```
engine.py
  → docs/loader.py (document loading)
  → ledger/ledger.py (state tracking)
  → planning/build_step_generator.py (AI calls)
  → planning/task_generator.py (AI calls)
  → evaluation/evaluator.py (task evaluation)
  → execution/patch_apply.py (file changes)
  → execution/runner.py (command execution)
  → tracking/* (completion logs)

director/autonomous.py
  → execution/stop_conditions.py (control flow)
  → execution/state.py (state persistence)
  → planning/task_derivation.py (task generation)
  → execution/ai_executor.py (task execution)

step_runner/runner.py
  → step_parser.py (step parsing)
  → executors.py (execution)
  → validation.py (output validation)
  → jsonl_ledger.py (ledger)
```

---

## Execution Flow Description

### 1. CLI Entrypoint Landscape

**Five competing entrypoints:**

a) **cli.py** (481 lines) - Primary step-runner CLI
   - Commands: step-run, prompt, prompt-file, exec, models
   - Direct to StepRunner or LLMExecutor
   - No orchestration layer

b) **cli_simple.py** (47 lines) - Engine wrapper
   - Commands: run, single-step
   - Dispatches to Engine class (full orchestration)

c) **cli_exec.py** (260 lines) - Primitives CLI
   - Commands: create-file, update-file, read-file, list-files, run-command
   - Direct to primitives with ledger logging

d) **cli_engine_v1.py** (101 lines) - Legacy engine CLI
   - Single command (run workspace)
   - Loads EngineV1 (mostly gutted)

e) **cli_step_runner.py** (90 lines) - Step-runner wrapper
   - Single command: step-run
   - Direct to StepRunner

**Recommendation:** 4 of these 5 CLIs are redundant.

### 2. Minimal Prompt Execution Path (Actual)

For a bare prompt (no step document, no orchestration):

```
cli.py:prompt command
  ↓
LLMExecutor(model=model)
  ↓
Auto-detect provider (Anthropic, OpenAI, Gemini, Codex, Copilot, Stub)
  ↓
_anthropic_execute() OR _openai_execute() OR ... OR _stub_execute()
  ↓
API call with prompt
  ↓
Return ExecutionResult(output=response, cost_usd=cost)
```

**Total Lines Touched:** ~200 (all in step_runner/executors.py)

**Dependencies:**
- anthropic SDK (optional)
- openai SDK (optional)
- google-genai SDK (optional)
- subprocess (for Codex/Copilot CLI)

**No Ledger, No Documents, No State, No Orchestration**

### 3. Full Orchestration Path (Engine)

For engine.run():

```
cli_simple.py:run command
  ↓
Engine(workspace_root, system_config)
  ↓
_validate_documents() - Load ARCHITECTURE, REQUIREMENTS, INTENT, PLAN, PROCESS, IMPLEMENTATION
  ↓
Compute document fingerprint (SHA256 of all .is files)
  ↓
Check for pivot (fingerprint change detection)
  ↓
generate_build_step() - AI call to propose next build step
  ↓
generate_tasks() - AI call to derive tasks from PLAN.is
  ↓
For each task:
    _execute_task()
      ↓
    execute_command() with artifact capture
      ↓
    evaluator.evaluate_task() - AI call to check success
      ↓
    Record in ledger, tracking logs, state manager
  ↓
Record run completion
```

**Total Lines Touched:** ~3000+ (spanning 20+ modules)

**Dependencies:**
- All .is documents must exist and be valid
- Ledger must be writable
- Multiple AI calls per task
- Complex state management
- Multi-level error handling

### 4. Step Runner Path (Middle Ground)

For step-run command:

```
cli.py:step-run command
  ↓
StepRunner(workspace_root, run_dir)
  ↓
parse_step_document() - Parse step doc (S-expression format)
  ↓
For each step:
    create_executor(executor_spec) - Shell or LLM
      ↓
    executor.execute(prompt)
      ↓
    validator.validate(output, acceptance_criteria)
      ↓
    If fail + policy.on_failure=fix:
        Build fix prompt
          ↓
        executor.execute(fix_prompt)
          ↓
        validator.validate(output)
    ↓
    Record in JSONL ledger
  ↓
Return RunResult(end_state, successful_steps, failed_steps)
```

**Total Lines Touched:** ~800 (step_runner/ module)

**Dependencies:**
- Step document (custom format)
- JSONL ledger (separate from LEDGER.is)
- Validation logic
- No document gate, no orchestration

---

## Workflow Remnant Inventory

### Document Loading System (Orchestration Baggage)

**Files:**
- `docs/loader.py` - 176 lines
- `docs/parser.py` - 216 lines
- `docs/validator.py` - 220 lines

**Purpose:**
- Load 6 .is files: ARCHITECTURE, REQUIREMENTS, INTENT, PLAN, PROCESS, IMPLEMENTATION
- Compute fingerprint for pivot detection
- Validate document structure and consistency

**Coupling:**
- Required by: engine.py, planning/build_step_generator.py, planning/task_generator.py
- Imports: docs/parser (S-expression parsing)

**Workflow Logic:**
- Pivot detection: Halt if document fingerprint changes mid-run
- Document gate: Block execution if documents missing or invalid
- Multi-document consistency checks

**Not Used By:**
- step_runner (has own step_parser)
- cli.py prompt commands
- primitives

**Verdict:** Pure orchestration. Not needed for prompt execution.

### Planning System (Orchestration Baggage)

**Files:**
- `planning/build_step_generator.py` - 260 lines
- `planning/task_generator.py` - 406 lines
- `planning/plan_parser.py` - ~170 lines
- `planning/build_step_schema.py` - Data structures
- `planning/task_schema.py` - Data structures
- `planning/validation.py` - Output validation

**Purpose:**
- Generate build steps from INTENT + REQUIREMENTS (AI call)
- Generate tasks from PLAN.is build order (AI call)
- Parse PLAN.is (build-order ...) structure
- Validate AI-generated plans and tasks

**Coupling:**
- Used by: engine.py, director/autonomous.py
- Imports: ai/provider, docs/loader, ledger/ledger

**Workflow Logic:**
- Task generation REFUSES to work without PLAN.is
- Extracts (build-order ...) from PLAN.is
- Queries ledger for completed build steps
- Generates tasks ONLY for next incomplete build step
- AI calls with document context

**Not Used By:**
- step_runner
- cli.py commands
- primitives

**Verdict:** Pure orchestration. Entire PLAN.is concept is workflow engine.

### Ledger System (Orchestration Baggage)

**Files:**
- `ledger/ledger.py` - 287 lines (LEDGER.is)
- `ledger/build_step_tracker.py` - Build step state
- `step_runner/jsonl_ledger.py` - JSONL ledger (separate!)
- `tracking/build_steps.py` - Build step logs
- `tracking/requirements.py` - Requirement completion logs

**Purpose:**
- Record ALL operations in append-only LEDGER.is (S-expression format)
- Track build step completion state
- Track requirement completion state
- Separate JSONL ledger for step-runner runs

**Coupling:**
- Used by: engine.py, director, planning, execution, primitives, status
- 13 modules import Ledger

**Workflow Logic:**
- Every operation must write ledger entry
- Build step state tracked for resume capability
- Pivot detection relies on ledger + fingerprint
- Two separate ledger formats (LEDGER.is vs runs/*.jsonl)

**Observation:**
- step_runner uses its own JSONL ledger (simpler format)
- primitives use LEDGER.is ledger
- Dual ledger system suggests architectural mismatch

**Verdict:** Ledger concept is valuable (audit trail), but current implementation is orchestration-coupled.

### State Management (Orchestration Baggage)

**Files:**
- `execution/state.py` - Execution state persistence
- `execution/stop_conditions.py` - Stop condition framework
- `ledger/build_step_tracker.py` - Build step state

**Purpose:**
- Persist execution state across runs
- Detect stop conditions (escalation, all-tasks-complete, single-step-complete)
- Resume execution from previous state

**Coupling:**
- Used by: engine.py, director/autonomous.py

**Workflow Logic:**
- Checks for stop conditions before each task
- Records advancement state after each task
- Enables resume from last advancement
- Single-step mode halts after one advancement

**Not Used By:**
- step_runner
- cli.py prompt commands
- primitives

**Verdict:** Pure orchestration control flow.

### Evaluation System (Orchestration Baggage)

**Files:**
- `evaluation/evaluator.py` - Task success determination

**Purpose:**
- Evaluate task success based on acceptance criteria
- Make AI calls to assess evidence
- Return success/failure determination

**Coupling:**
- Used by: engine.py

**Workflow Logic:**
- Collects evidence: command results, file changes, artifacts
- Makes AI call with evidence + acceptance criteria
- Returns binary success/failure + reasoning

**Not Used By:**
- step_runner (has own validation.py)
- All other subsystems

**Observation:**
- step_runner/validation.py is separate, simpler validation
- evaluation/evaluator.py is AI-powered task evaluation
- Duplication of validation concepts

**Verdict:** Orchestration-specific evaluation. Simpler validation exists in step_runner.

---

## Prompt Execution Path (Minimal Ideal)

### Current Reality

**Minimal working path for "prompt in → result out":**

```python
# ~200 lines total from step_runner/executors.py

from step_runner.executors import LLMExecutor

executor = LLMExecutor(model="claude-sonnet-4-5-20250929")
result = executor.execute("What is 2+2?")
print(result.output)  # "4"
```

**What it does:**
1. Auto-detect provider (Anthropic key → ClaudeProvider)
2. Make API call
3. Return response

**What it does NOT require:**
- Document loading
- Ledger writing
- State persistence
- Build step generation
- Task generation
- Evaluation
- Orchestration

### Hidden Complexity

**LLMExecutor chains:**
1. Check environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
2. Try providers in priority order
3. Fall back to stub mode if no provider available
4. Support 6 providers: Anthropic, OpenAI, Gemini, Codex CLI, Copilot CLI, Stub
5. Handle retries for rate limits (Gemini)
6. Calculate costs per provider
7. Return ExecutionResult with metadata

**Actual provider abstraction:**
```python
# ai/provider.py has this interface
class AIProvider(ABC):
    def call(self, prompt, model, max_tokens, temperature) -> CallResult
```

**But step_runner/executors.py reimplements everything:**
- _anthropic_execute()
- _openai_execute()
- _gemini_execute()
- _codex_execute()
- _copilot_execute()
- _stub_execute()

**Duplication:** ai/provider.py has ClaudeProvider, OpenAIProvider, CopilotProvider BUT they're not used by step_runner!

---

## Baggage Surface Area Estimate

### Lines of Code by Category

| Category | Files | Lines | % of Total |
|----------|-------|-------|-----------|
| **Core Prompt Execution** | 3 | ~800 | 7% |
| **Workflow Orchestration** | 25 | ~5500 | 49% |
| **Infrastructure/Support** | 15 | ~2500 | 22% |
| **Dead/Suspicious Code** | 10 | ~1500 | 13% |
| **Tooling (discovery/status)** | 5 | ~1000 | 9% |
| **TOTAL** | 71 | 11,312 | 100% |

### Orchestration Burden

**If objective is "simple prompt runner":**
- **Keep:** 800 lines (step_runner + provider abstraction)
- **Remove:** 5500 lines (orchestration)
- **Review:** 2500 lines (infrastructure - some reusable)
- **Delete:** 1500 lines (dead code)

**Reduction potential: ~80% of codebase is orchestration or dead code.**

### Dependency Burden

**External Python Dependencies (from pyproject.toml):**
- anthropic - AI provider
- openai - AI provider  
- google-genai - AI provider
- python-dotenv - Environment loading
- pytest - Testing (dev)

**Orchestration-specific (not needed for prompt runner):**
- None (all dependencies are actually used by step_runner)

**Observation:** Dependency footprint is clean. Bloat is in internal architecture, not external deps.

---

## Risk Assessment for Removal

### High Risk (Interconnected Systems)

**1. Ledger System**
- **Risk:** 13 modules import Ledger
- **Impact:** Removing ledger breaks primitives, planning, tracking, engine
- **Mitigation:** Ledger is valuable concept; simplify to single format (JSONL vs S-expression)

**2. Document Loading**
- **Risk:** Core to engine.py and planning system
- **Impact:** Removing breaks orchestration but NOT step-runner
- **Mitigation:** Already isolated from step-runner; safe to remove for prompt-only use

**3. AI Provider Abstraction**
- **Risk:** Dual implementation (ai/provider.py vs executors.py)
- **Impact:** Consolidation needed; current duplication causes confusion
- **Mitigation:** Pick one implementation; step_runner's is more complete

### Medium Risk (Partially Coupled)

**4. Primitives (file_ops, command_ops)**
- **Risk:** Used by both orchestration AND step-runner
- **Impact:** Removing ledger integration breaks orchestration; keeping it works for both
- **Mitigation:** Keep primitives, make ledger optional parameter

**5. Step Parser**
- **Risk:** Custom S-expression format for step documents
- **Impact:** Required if keeping step-runner mode; not needed for bare prompts
- **Mitigation:** Orthogonal to prompt execution; can coexist

### Low Risk (Isolated Modules)

**6. Planning System**
- **Risk:** Zero coupling to step-runner
- **Impact:** Only used by engine.py and director
- **Mitigation:** Safe to remove for prompt-only rewrite

**7. Evaluation System**
- **Risk:** Only used by engine.py
- **Impact:** step-runner has its own validation
- **Mitigation:** Safe to remove

**8. Director/Autonomous**
- **Risk:** High-level orchestration only
- **Impact:** Not used by step-runner or primitives
- **Mitigation:** Safe to remove

**9. Tracking/State/Stop Conditions**
- **Risk:** Orchestration control flow only
- **Impact:** Not used by step-runner
- **Mitigation:** Safe to remove

### Zero Risk (Dead Code)

**10. Multiple CLI Entrypoints**
- **Risk:** None; redundant entry points
- **Impact:** Consolidation improves clarity
- **Mitigation:** Keep one CLI, remove others

**11. engine_v1.py**
- **Risk:** Marked as "pruned" legacy
- **Impact:** Contains only utility functions (generate_run_id, enforce_workspace_root)
- **Mitigation:** Extract utilities, delete module

**12. Unused execution/ modules**
- **Risk:** confidence.py, escalation.py, risk.py, mode.py unused
- **Impact:** No references in step-runner or primitives
- **Mitigation:** Safe to delete

---

## Conceptual Complexity Assessment

### Current Mental Model Required

**To understand ai-factory, a developer must learn:**

1. **Six .is file formats:** ARCHITECTURE, REQUIREMENTS, INTENT, PLAN, PROCESS, IMPLEMENTATION
2. **Two ledger formats:** LEDGER.is (S-expression) vs runs/*.jsonl
3. **Three execution modes:** run, single-step, step-run
4. **Five CLI entrypoints:** cli.py, cli_simple.py, cli_exec.py, cli_engine_v1.py, cli_step_runner.py
5. **Two validation systems:** evaluation/evaluator.py (AI-powered) vs step_runner/validation.py
6. **Two provider systems:** ai/provider.py vs step_runner/executors.py
7. **Document fingerprinting:** SHA256-based pivot detection
8. **Build step lifecycle:** Generation → Task derivation → Execution → Evaluation → Completion tracking
9. **State management:** Execution state, stop conditions, resume capability
10. **Primitives integration:** Ledger-tracked file/command operations

### Proposed Mental Model (Minimal)

**For a prompt execution engine:**

1. **Provider abstraction:** Single interface to multiple AI providers
2. **Prompt in → Response out:** Direct execution path
3. **Optional ledger:** Simple JSONL audit trail (not mandatory)
4. **Optional step runner:** Sequential execution of multi-step documents

**Concepts eliminated:** 6 .is files, pivot detection, build steps, tasks, evaluation, state persistence, stop conditions, orchestration

**Complexity reduction: 90% fewer concepts**

---

## Conclusion

### What ai-factory Actually Is

**Current state:** A sophisticated autonomous workflow orchestration system with:
- Multi-document planning framework (PLAN.is driven)
- AI-powered build step and task generation
- Document consistency gates with pivot detection
- Multi-level state tracking and resume capability
- AI-powered task evaluation
- Stop condition framework
- Dual ledger systems
- Five CLI entrypoints

**Hidden inside:** A simple prompt execution engine (step_runner) that can:
- Execute prompts against multiple AI providers
- Run multi-step documents sequentially
- Validate outputs against acceptance criteria
- Log operations to JSONL ledger

### Architectural Mismatch

**The mismatch:**
- step_runner is a ~800-line prompt execution engine
- engine.py is a ~3000-line workflow orchestrator
- They share code (primitives) but have completely different architectures
- Duplication: Two provider systems, two ledgers, two validation systems

**Root cause:** Evolution from workflow engine → toward simpler execution
- engine.py = original vision (autonomous orchestration)
- step_runner = newer, simpler vision (sequential execution)
- Legacy never fully removed

### Path Forward (If Goal Is Prompt Runner)

**Keep:**
- step_runner/ module (~800 lines)
- primitives/ module (~500 lines) with optional ledger
- ai/provider.py OR step_runner/executors.py (pick one, not both)
- system_config.py for provider selection

**Remove:**
- engine.py, engine_v1.py
- director/
- docs/ (loader, parser, validator)
- planning/
- evaluation/
- tracking/
- execution/state.py, stop_conditions.py, escalation.py, confidence.py, risk.py, mode.py
- 4 of 5 CLI files

**Result:** ~2000-line prompt execution engine with step-runner capabilities

**Trade-offs:**
- Lose: Autonomous orchestration, AI-powered planning, resume capability, pivot detection
- Gain: Simplicity, clarity, maintainability, 80% less code

---

## Appendix: Key Symbol Reference

### Core Classes

**Execution:**
- `AIProvider` (ai/provider.py) - Abstract provider interface
- `ClaudeProvider` (ai/provider.py) - Anthropic Claude implementation
- `LLMExecutor` (step_runner/executors.py) - Multi-provider executor
- `ShellExecutor` (step_runner/executors.py) - Shell command executor
- `ExecutionResult` (step_runner/executors.py) - Execution output container

**Orchestration:**
- `Engine` (engine.py) - Full orchestrator with document gate
- `Director` (director/director.py) - Preflight + autonomous dispatch
- `AutonomousCore` (director/autonomous.py) - Task execution loop
- `StepRunner` (step_runner/runner.py) - Sequential step executor

**Document Loading:**
- `DocumentSet` (docs/loader.py) - Loaded .is files + fingerprint
- `DocumentLoader` (docs/loader.py) - Document loading + fingerprinting
- `ISParser` (docs/parser.py) - S-expression parser
- `DocumentValidator` (docs/validator.py) - Document consistency checks

**Planning:**
- `BuildStep` (planning/build_step_schema.py) - Build step structure
- `Task` (planning/task_schema.py) - Task structure
- `generate_build_step()` (planning/build_step_generator.py) - AI call to create build step
- `generate_tasks()` (planning/task_generator.py) - AI call to create tasks from PLAN.is

**State:**
- `Ledger` (ledger/ledger.py) - LEDGER.is append-only log
- `LedgerWriter` (step_runner/jsonl_ledger.py) - JSONL ledger for step-runner
- `ExecutionStateManager` (execution/state.py) - Resume state persistence
- `StopConditionChecker` (execution/stop_conditions.py) - Stop condition detection

**Primitives:**
- `create_file()` (primitives/file_ops.py) - Create file with ledger entry
- `update_file()` (primitives/file_ops.py) - Update file with ledger entry
- `run_command()` (primitives/command_ops.py) - Execute command with ledger entry

### Key Functions

**Entry Points:**
- `main()` (cli.py) - Primary CLI dispatcher
- `main()` (cli_simple.py) - Engine CLI (run/single-step)
- `main()` (cli_exec.py) - Primitives CLI

**Execution Flow:**
- `Engine.run()` - Full orchestration run
- `Engine.single_step()` - Execute one task then halt
- `StepRunner.run()` - Execute step document
- `LLMExecutor.execute()` - Execute single prompt

---

**End of Discovery Report**
