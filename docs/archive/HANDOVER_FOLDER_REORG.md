# Handover: Folder Reorganization Session
## 2026-02-22

## Status at Handover
- [x] Research completed (folder org best practices)
- [x] Surveys completed (docs/ and D: drive inventoried)
- [x] HybridRAG3 docs/ reorganization -- DONE (9 numbered subfolders, all refs updated)
- [x] D: drive reorganization -- DONE (see notes below)

### Remaining Manual Steps
- Move `D:\Claude_Code_Autonomous_Framework.docx` to `D:\Docs\Guides\` (locked by Office, close Word first)
- Move `D:\waiver_cheat_sheet_v4b.xlsx` to `D:\Docs\Cheat_Sheets\` (locked by Excel, close Excel first)
- Delete `D:\~$waiver_cheat_sheet_v4b.xlsx` (Office lock file, close Excel first)
- Optional: clean `D:\tmp\` if `transfer_test_src2` is no longer needed

---

## Strategy Summary

Using **Numbered Lifecycle + Topic Hybrid** for docs/ (research-backed best practice for software projects), and **Function-Separated Root** for D: drive.

Key principles:
- Numbered prefixes (01_, 02_...) for stable sort order
- Group by purpose/audience, NOT file type
- Max 3 levels deep from any organizing root
- Keep archive/, research/, logs/ intact (already organized)
- DO NOT TOUCH: HybridRAG3 paths, RAG Source Data, RAG Indexed Data

---

## Plan A: HybridRAG3 docs/ Folder

### New Structure
```
docs/
  01_setup/                    -- Installation, prerequisites
    INSTALL_AND_SETUP.md
    CLAUDE.md
  02_architecture/             -- How the system works internally
    ARCHITECTURE_DIAGRAM.md
    TECHNICAL_THEORY_OF_OPERATION_RevA.md
    THEORY_OF_OPERATION_RevA.md
    SECURITY_THEORY_OF_OPERATION_RevA.md
    SOFTWARE_STACK.md
    INTERFACES.md
    FORMAT_SUPPORT.md
    HybridRAG_v3_Block_Diagram.html
    HybridRAG_v3_Network_Topology.html
  03_guides/                   -- User-facing docs
    USER_GUIDE.md
    GUI_GUIDE.md
    README.md
    SHORTCUT_SHEET.md
    GLOSSARY.md
    QUOTING_AND_ENCODING_SURVIVAL_GUIDE.txt
  04_demo/                     -- Demo preparation materials
    DEMO_PREP.md
    DEMO_GUIDE.md
    DEMO_BATTLE_SIMULATION.md
    DEMO_QA_PREP.md
    DEMO_QA_RESEARCH_FINDINGS.md
    DEMO_LEARNING_PATH.md
  05_security/                 -- Security, compliance, model audit
    HYBRIDRAG3_SECURITY_AUDIT_NIST_800_171.md
    SECURITY_AUDIT_ROADMAP.txt
    DEFENSE_MODEL_AUDIT.md
    GIT_REPO_RULES.md
    waiver_cheat_sheet_v4b.xlsx
  06_hardware/                 -- Hardware stack docs
    STACK_LAPTOP.md
    STACK_PERSONAL_DESKTOP.md
    STACK_WORKSTATION.md
  07_career/                   -- Job market research
    AI_FIELD_ENGINEER_FDE_JOBS.md
    AI_JOB_MARKET_COLORADO_SPRINGS.md
  08_learning/                 -- Study materials, landscape research
    PYTHON_STUDY_GUIDE.md
    STUDY_GUIDE.md
    RAG_LANDSCAPE_2026.md
  09_project_mgmt/             -- Plans, roadmaps, Office docs
    HybridRAG_v3_Master_Game_Plan.docx
    HybridRAG3_Product_Roadmap.docx
    HybridRAG3_Setup_Guide.docx
    HybridRAG3_Software_Audit.xlsx
    HandoverZip_2_21_26_9_30_PM.zip
  archive/                     -- KEEP AS-IS (historical docs, handovers, reports)
  research/                    -- KEEP AS-IS (research deep-dives)
  logs/                        -- KEEP AS-IS (app logs)
```

### Move Commands (docs/)
```bash
# Create folders
mkdir -p docs/01_setup docs/02_architecture docs/03_guides docs/04_demo docs/05_security docs/06_hardware docs/07_career docs/08_learning docs/09_project_mgmt

# 01_setup
mv docs/INSTALL_AND_SETUP.md docs/01_setup/
mv docs/CLAUDE.md docs/01_setup/

# 02_architecture
mv docs/ARCHITECTURE_DIAGRAM.md docs/02_architecture/
mv docs/TECHNICAL_THEORY_OF_OPERATION_RevA.md docs/02_architecture/
mv docs/THEORY_OF_OPERATION_RevA.md docs/02_architecture/
mv docs/SECURITY_THEORY_OF_OPERATION_RevA.md docs/02_architecture/
mv docs/SOFTWARE_STACK.md docs/02_architecture/
mv docs/INTERFACES.md docs/02_architecture/
mv docs/FORMAT_SUPPORT.md docs/02_architecture/
mv docs/HybridRAG_v3_Block_Diagram.html docs/02_architecture/
mv docs/HybridRAG_v3_Network_Topology.html docs/02_architecture/

# 03_guides
mv docs/USER_GUIDE.md docs/03_guides/
mv docs/GUI_GUIDE.md docs/03_guides/
mv docs/README.md docs/03_guides/
mv docs/SHORTCUT_SHEET.md docs/03_guides/
mv docs/GLOSSARY.md docs/03_guides/
mv docs/QUOTING_AND_ENCODING_SURVIVAL_GUIDE.txt docs/03_guides/

# 04_demo
mv docs/DEMO_PREP.md docs/04_demo/
mv docs/DEMO_GUIDE.md docs/04_demo/
mv docs/DEMO_BATTLE_SIMULATION.md docs/04_demo/
mv docs/DEMO_QA_PREP.md docs/04_demo/
mv docs/DEMO_QA_RESEARCH_FINDINGS.md docs/04_demo/
mv docs/DEMO_LEARNING_PATH.md docs/04_demo/

# 05_security
mv docs/HYBRIDRAG3_SECURITY_AUDIT_NIST_800_171.md docs/05_security/
mv docs/SECURITY_AUDIT_ROADMAP.txt docs/05_security/
mv docs/DEFENSE_MODEL_AUDIT.md docs/05_security/
mv docs/GIT_REPO_RULES.md docs/05_security/
mv docs/waiver_cheat_sheet_v4b.xlsx docs/05_security/

# 06_hardware
mv docs/STACK_LAPTOP.md docs/06_hardware/
mv docs/STACK_PERSONAL_DESKTOP.md docs/06_hardware/
mv docs/STACK_WORKSTATION.md docs/06_hardware/

# 07_career
mv docs/AI_FIELD_ENGINEER_FDE_JOBS.md docs/07_career/
mv docs/AI_JOB_MARKET_COLORADO_SPRINGS.md docs/07_career/

# 08_learning
mv docs/PYTHON_STUDY_GUIDE.md docs/08_learning/
mv docs/STUDY_GUIDE.md docs/08_learning/
mv docs/RAG_LANDSCAPE_2026.md docs/08_learning/

# 09_project_mgmt
mv docs/HybridRAG_v3_Master_Game_Plan.docx docs/09_project_mgmt/
mv docs/HybridRAG3_Product_Roadmap.docx docs/09_project_mgmt/
mv docs/HybridRAG3_Setup_Guide.docx docs/09_project_mgmt/
mv docs/HybridRAG3_Software_Audit.xlsx docs/09_project_mgmt/
mv docs/HandoverZip_2_21_26_9_30_PM.zip docs/09_project_mgmt/
```

---

## Plan B: D: Drive Reorganization

### Protected Paths (DO NOT MOVE)
- D:\HybridRAG3 -- primary repo
- D:\HybridRAG3_Educational -- active educational repo
- D:\RAG Source Data -- referenced by HybridRAG3 config
- D:\RAG Indexed Data -- referenced by HybridRAG3 config
- D:\System Volume Information -- Windows system
- D:\$RECYCLE.BIN -- Windows system
- D:\Autorun.inf, .VolumeIcon.* -- drive identity files

### Actions
1. **Delete Office temp files** (safe, these are lock files from closed docs):
   - ~$aude_Code_Autonomous_Framework.docx
   - ~$bridRAG3_Claude_Tuning_Playbook_v2.docx
   - ~$bridRAG3_Master_Optimization_Directive_v3.docx
   - ~$rk_Laptop_PowerShell_Reference.docx
   - ~$waiver_cheat_sheet_v4b.xlsx

2. **Move loose files to Docs/**:
   - D:\Claude_Code_Autonomous_Framework.docx -> D:\Docs\Guides\
   - D:\waiver_cheat_sheet_v4b.xlsx -> D:\Docs\Cheat_Sheets\
   - D:\DRIVE_CLEANUP_REPORT.md -> D:\Docs\

3. **Move test/stale clones to Archive/**:
   - D:\HybridRAG3_Clone_for_Test_2_21_26 -> D:\Archive\Test_Clones\
   - D:\HybridRAG3_Clone_for_Test2_2_21_26 -> D:\Archive\Test_Clones\
   - D:\HybridRAG3_QA_Sprint2 -> D:\Archive\Test_Clones\

4. **Organize Docs/ into subfolders**:
   ```
   D:\Docs\
     Guides\               -- How-to docs, frameworks, references
     Handovers\            -- Handover zips and docs
     Cheat_Sheets\         -- Quick reference sheets
     Plans\                -- Optimization directives, sprint plans
     Research\             -- Cost of Code, CUI routing, etc.
   ```

5. **Consolidate KnowledgeBase/ into Projects/**:
   - D:\KnowledgeBase\LimitlessApp -> D:\Projects\KnowledgeBase\LimitlessApp

6. **Merge Misc/Downloads** into a single location or clean if empty

7. **Clean tmp/** if contents are stale

### D: Drive Final Structure
```
D:\
  HybridRAG3\                -- PRIMARY REPO (untouched)
  HybridRAG3_Educational\    -- Educational repo (untouched)
  RAG Source Data\            -- Source data (untouched)
  RAG Indexed Data\           -- Indexed data (untouched)
  Projects\                   -- Active project workspaces
    A_Team\
    AI_Project\
    KnowledgeBase\
    LimitlessApp\
    localai_project\
    rag-downloader\
    reddit\
    softwarerecs.stackexchange.com\
    Study_Sources\
  Docs\                       -- All documentation and reference
    Guides\
    Handovers\
    Cheat_Sheets\
    Plans\
    Research\
  Tools\                      -- Shared utilities and scripts
  Archive\                    -- Inactive/historical
    Test_Clones\
    archive_clutter\
    HybridRAG3_API_MOD\
    HybridRAG3_Research\
    HybridRAG3_VariousVersions\
    HybridRAG3_Window3_GUI\
    HybridRAG3_Window4_GUI\
    MiscOld\
    RAG_Staging\
    Seagate\
    T2venv\
    TestDestination\
    TestSource\
  Misc\                       -- Downloads, unsorted
  tmp\                        -- Temporary workspace
```

---

## CLAUDE.md References to Update
After moving files, these CLAUDE.md references need updating:
- `docs/GIT_REPO_RULES.md` -> `docs/05_security/GIT_REPO_RULES.md`
- `docs/DEFENSE_MODEL_AUDIT.md` -> `docs/05_security/DEFENSE_MODEL_AUDIT.md` (wait, this says "MODEL_AUDIT.md" in CLAUDE.md)

Check these files for internal cross-references:
- CLAUDE.md (project root)
- docs/CLAUDE.md (docs-level instructions)
- Any README that links to docs/

---

## If Session Ends Mid-Work
1. Check which tasks are marked completed in the task list above
2. The move commands in Plan A and Plan B can be run manually or by a new session
3. After all moves, grep for broken references: `grep -r "docs/" D:\HybridRAG3\CLAUDE.md`
4. Update CLAUDE.md path references to include new subfolder prefixes
