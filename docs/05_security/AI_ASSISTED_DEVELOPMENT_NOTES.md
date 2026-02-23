# AI-Assisted Development Notes
<!-- Bond -->

**Date: 2026-02-22** | HybridRAG3 Project | 6-Week Build

## Project Stats

- **Builder:** RF Field Engineer, zero prior coding experience
- **Timeline:** 6 weeks (nights, weekends, personal time)
- **Result:** 74,958 total lines across 207 Python files
  - 42,298 lines production code
  - 15,236 lines test code (40 test files)
  - 21,556 lines commentary (34% documentation ratio)

## Industry Comparison

| Metric | This Project | Industry Norm |
|--------|-------------|---------------|
| Time to working system | 6 weeks | 9-18 months (senior dev) |
| Codebase size | 42K production LOC | Comparable to Kotaemon (25K), larger than PrivateGPT (5K) or Quivr (6K) |
| Test coverage | 15,236 lines, 40 files | Most internal tools ship with zero tests |
| Documentation ratio | 34% | Industry average 15-20% |
| Effective LOC/day | ~1,370-1,900 | Senior dev with AI: 80-100 |
| Dual-mode (offline + online) | Yes | Most open-source RAGs are one or the other |
| NDAA/ITAR compliant model stack | Yes | Most projects don't consider this |

## Who Did What

| Work | Who |
|------|-----|
| Python syntax, patterns, boilerplate | AI (~95%) |
| Architecture decisions | Human (~90%) |
| Requirements / feature selection | Human (100%) |
| Domain constraints (NDAA, ITAR, offline) | Human (100%) |
| Testing and bug catching | Split ~50/50 |
| Integration and debugging | Split ~60 human / 40 AI |

The industry term for this workflow is **AI-assisted systems engineering**. The
AI writes code. The human architects the system. Neither alone produces the
result. Hand the same AI tools to a software engineer with no RF/defense domain
knowledge and no understanding of organizational constraints, and they would
build a LangChain wrapper that calls OpenAI -- which cannot be deployed in
restricted environments.

## What This Is Not

"Vibe coding" means prompting AI with vague ideas, accepting whatever it
generates, no testing, no architecture, ship and pray.

This project has:

- 40 test files with 15,236 lines of test code
- 400-question golden eval set with injection traps
- NDAA/ITAR compliance audit with documented disqualifications
- Zero-trust offline-first architecture
- Hallucination guard with NLI verification
- 34% documentation ratio (double industry average)
- Eval-protected files that cannot be modified (scoring is locked)
- SHA-256 verified file transfers with atomic writes
- 98% pass rate on 400-question eval including injection attacks

Vibe coders don't write eval suites. Vibe coders don't build hallucination
guards. Vibe coders don't audit model supply chains for export control
compliance.

**"Run the eval suite. 400 questions including injection attacks. 98% pass
rate. Then show me yours."**

## On Code Transparency

There was a culture in software engineering of intentionally not writing
comments so that hardware engineers couldn't understand the code -- or even
other software engineers -- creating artificial job security through
manufactured complexity. A "black magic" facade.

AI eliminates that gatekeeping. When any engineer can use AI to translate and
add commentary to previously opaque code, the mystique disappears. The code
becomes auditable by the domain experts who actually understand whether the
algorithms are correct.

The result: teams are now questioning obviously wrong algorithms and techniques
that went unchallenged for years because nobody outside the original author
could read the code. The cat is out of the bag.

## Architecture Value

The lasting value of this project is not the Python code -- it is the pattern:

- How to deploy AI on air-gapped or restricted networks
- How to use only approved models (NDAA/ITAR clean)
- How to detect hallucinations before they reach the user
- How to maintain an audit trail for every query and cost
- How to make the system usable by non-technical staff via GUI

This architecture is buildable and maintainable by engineering staff who will
use it. It does not require a dedicated software team to keep alive.

## Codebase Breakdown by Function

| Function | Files | Code | Commentary | Total | Doc% |
|----------|------:|-----:|-----------:|------:|-----:|
| Test Suite | 40 | 15,236 | 4,479 | 23,718 | 22.7% |
| GUI Application | 19 | 4,859 | 1,310 | 7,201 | 21.2% |
| Bulk Transfer & Tools | 15 | 3,306 | 1,736 | 5,792 | 34.4% |
| Sync & Work Validation | 26 | 3,086 | 1,031 | 4,754 | 25.0% |
| Diagnostics & IBIT | 11 | 2,376 | 758 | 3,547 | 24.2% |
| File Parsers | 28 | 1,928 | 1,462 | 3,987 | 43.1% |
| Core RAG Pipeline | 8 | 1,820 | 1,797 | 4,164 | 49.7% |
| Hallucination Guard | 12 | 1,629 | 1,136 | 3,185 | 41.1% |
| Scripts & Model Mgmt | 10 | 1,454 | 739 | 2,590 | 33.7% |
| API & HTTP | 6 | 1,261 | 756 | 2,392 | 37.5% |
| Config & Boot | 5 | 1,257 | 1,004 | 2,648 | 44.4% |
| Monitoring & Logging | 3 | 361 | 187 | 639 | 34.1% |
| Cost Tracking | 1 | 277 | 220 | 562 | 44.3% |
| File Validation | 1 | 92 | 91 | 217 | 49.7% |
| Other (root files) | 22 | 3,356 | 4,850 | 9,562 | 59.1% |
| **TOTAL** | **207** | **42,298** | **21,556** | **74,958** | **33.8%** |

## Open-Source RAG Comparison

| Project | Type | Python LOC |
|---------|------|--------:|
| simple-local-rag | Tutorial | ~500 |
| PrivateGPT | Offline-first | 5,006 |
| Quivr | Online SaaS | 6,102 |
| Kotaemon | Hybrid | 25,773 |
| **HybridRAG3** | **Hybrid dual-mode** | **42,298** |
| Haystack | Framework | 100,517 |
| RAGFlow | Enterprise platform | 123,983 |

Source: GitHub repos via CodeTabs API, February 2026.

## Origin Story: Why an RF Engineer Built a RAG System

### The Problem

The company deployed a general-purpose AI in 2025, but it has no access to
program data. Every engineering program sits on terabytes of documents --
specs, test reports, calibration guides, design reviews, procedures -- and
engineers waste hours every day searching for and sorting through them.
The information exists. Finding it is the bottleneck.

Software engineering teams should have been jumping at this. They have the
Python foundations, the CS background, the tooling. But defense companies are
slow-walking AI adoption, and the people best positioned to build it aren't
building it.

So an RF field engineer decided to do it himself.

### The Path

1. **Identified RAG** as the answer to "how do I connect AI to our program
   data" -- not fine-tuning, not retraining, just retrieval over existing
   documents.

2. **Discovered offline AI** (Ollama + local models) as the path for
   air-gapped and restricted environments where cloud APIs aren't available.

3. **Then discovered online API endpoints** could be approved through proper
   channels, and designed the system to support both modes -- offline for
   restricted sites, online for approved environments, seamless switching.

4. **Started with LangChain** because every tutorial and example points to it.
   Hit compatibility issue after compatibility issue. The ecosystem moves fast,
   documentation lags, and version conflicts cascade. Coming from field
   engineering where systems must be troubleshootable, modular, and portable,
   this was unacceptable.

5. **Scrapped LangChain entirely** and built a custom stack from simple,
   auditable components -- even though nobody else seemed to be using this
   approach. Direct Ollama HTTP calls, raw SQLite vector store, no framework
   magic. Every piece can be inspected and understood.

6. **Discovered the 500-line AI context limit.** Early AI coding assistants
   could only reason about ~500 lines at a time. Rather than fight it, turned
   it into a design constraint: all classes stay under 500 lines. This means
   any class in the system can be fully audited or troubleshot by AI in one
   pass. The limitation became an architectural advantage.

7. **Learned that latest isn't safest.** Corporations prefer time-tested,
   stable versions. Had to pin older revisions of most dependencies after
   discovering the company's software approval store. Latest features don't
   matter if the version isn't approved for use.

8. **Hit the NDAA/ITAR wall.** Had to scrap good AI models like Qwen because
   they're made in China and banned under NDAA. Had to scrap Llama/Meta under
   ITAR restrictions. Found creative alternatives with approved publishers
   (Microsoft phi4, Mistral, Google gemma3). Every model in the stack has a
   documented country of origin and license audit.

9. **Committed to modularity without patches.** No monkey-patching, no
   workarounds that hide the real fix. Spent more time up front on clean
   interfaces. Every module can be swapped without touching its neighbors.

10. **Built diagnostics that evolved to military avionics standards.** Started
    with simple health checks, ended up with IBIT (Initial Built-In Test)
    inspired by avionics power-on self-test patterns. Pre-flight and post-flight
    checks run before and after every software modification.

11. **Security audits became routine.** Realized that keeping the system
    deployable in a defense environment means continuous security posture
    management, not a one-time review. Audited the full dependency chain,
    pinned versions, documented every approval.

### The Lesson

The barrier to AI adoption in defense isn't technical. The models exist. The
frameworks exist. The hardware exists. The barrier is organizational -- and
the people closest to the problem (the engineers who waste hours searching for
data every day) are not the people who traditionally build software tools.

AI-assisted development changes that equation. A domain expert who understands
the problem, the constraints, and the deployment environment can now direct AI
to build the solution. The 500-line class limit, the NDAA audit, the offline-
first architecture, the hallucination guard -- none of those came from software
engineering best practices. They came from an RF engineer applying field
engineering discipline to a software problem.

The cat is out of the bag.
