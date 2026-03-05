#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the feature registry part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Feature Toggle Registry (src/core/feature_registry.py)
# ============================================================================
#
# WHAT: Single source of truth for every toggleable feature in the
#       application. Both CLI and GUI read this registry for feature
#       names, descriptions, dependencies, and on/off states.
#
# WHY:  Features like hallucination filtering, reranking, and PII
#       scrubbing can be turned on/off by users. Without a central
#       registry, feature state would be scattered across config files,
#       environment variables, and code -- making it hard to see what
#       is enabled and impossible to build a GUI toggle panel.
#
# HOW:  The "Registry Pattern": all features are defined once in
#       FEATURE_CATALOG (a list of FeatureDefinition dataclasses).
#       The FeatureRegistry class reads/writes their on/off state
#       from the YAML config file. To add a new feature, you just
#       add one FeatureDefinition to FEATURE_CATALOG -- the CLI
#       and GUI automatically pick it up.
#
# USAGE (Python):
#       reg = FeatureRegistry("config/default_config.yaml")
#       reg.list_features()                     # Show all with status
#       reg.enable("hallucination-filter")      # Turn feature ON
#       catalog = reg.get_feature_catalog()     # Dict list for GUI
#
# USAGE (PowerShell):
#       rag-features list | enable | disable | status
#
# GUI INTEGRATION:
#       Call get_feature_catalog() to get feature dicts with
#       feature_id, display_name, category, description, enabled state.
#       Render each as a toggle switch grouped by category.
#
# NETWORK ACCESS: NONE
# ============================================================================

import os
import sys
import copy
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


# --- FEATURE DEFINITION DATACLASS ------------------------------------------
# Each feature is defined ONCE here. The GUI and CLI both read this.
# To add a new feature: add a FeatureDefinition to FEATURE_CATALOG below.
# =========================================================================

@dataclass
class FeatureDefinition:
    """
    Describes a single toggleable feature for CLI and GUI rendering.

    Fields explained:
        feature_id:     Unique string ID used in CLI commands (e.g., "reranker")
        display_name:   Human-readable name shown in GUI (e.g., "Cross-Encoder Reranker")
        category:       Grouping for GUI tabs (Quality/Retrieval/Security/Cost)
        description:    One-sentence summary for users
        detail:         Longer explanation for tooltip or detail panel
        impact_note:    Performance impact warning (e.g., "Adds ~2-4s per query")
        config_section: Which YAML section holds the toggle (e.g., "retrieval")
        config_key:     Which key within that section (e.g., "reranker_enabled")
        default:        Default on/off state if not in YAML
        requires:       List of feature_ids that should be enabled first
    """
    feature_id: str
    display_name: str
    category: str
    description: str
    detail: str = ""
    impact_note: str = ""
    config_section: str = ""
    config_key: str = "enabled"
    default: bool = False
    requires: list = field(default_factory=list)


# =========================================================================
# FEATURE CATALOG
# =========================================================================
# Add new features here. The CLI and GUI automatically pick them up.
#
# CATEGORIES (for GUI grouping):
#   "Quality"    -- Features that improve answer accuracy/reliability
#   "Retrieval"  -- Features that affect how documents are searched
#   "Security"   -- Features that protect data and audit actions
#   "Cost"       -- Features that track or limit spending
#   "Output"     -- Features that affect how results are displayed
# =========================================================================

FEATURE_CATALOG: List[FeatureDefinition] = [

    # --- QUALITY -----------------------------------------------------------

    FeatureDefinition(
        feature_id="hallucination-filter",
        display_name="Hallucination Filter",
        category="Quality",
        description=(
            "5-step anti-hallucination pipeline: retrieval gate, "
            "prompt hardening, claim extraction, NLI verification, "
            "and grounding score."
        ),
        detail=(
            "Local NLI model checks every LLM claim against source docs. "
            "Unsupported claims are flagged/blocked/stripped per config. "
            "Runs 100% locally after initial ~440MB model download."
        ),
        impact_note="Adds ~2-4s per query (GPU) or ~3-8s (CPU)",
        config_section="hallucination_guard",
        config_key="enabled",
        default=True,
    ),

    # --- RETRIEVAL ---------------------------------------------------------

    FeatureDefinition(
        feature_id="hybrid-search",
        display_name="Hybrid Search",
        category="Retrieval",
        description=(
            "Combines semantic (meaning) and keyword (exact match) "
            "search for better document retrieval."
        ),
        detail=(
            "Semantic finds related topics; keyword finds exact terms "
            "(part numbers, filenames). Hybrid merges both via RRF. "
            "Best for engineering docs with mixed technical content."
        ),
        impact_note="Minimal (<100ms extra)",
        config_section="retrieval",
        config_key="hybrid_search",
        default=True,
    ),

    FeatureDefinition(
        feature_id="reranker",
        display_name="Cross-Encoder Reranker",
        category="Retrieval",
        description=(
            "Re-scores search results with a more accurate model "
            "before sending them to the LLM. Tunable via "
            "reranker_top_n (default 12 candidates)."
        ),
        detail=(
            "Re-reads each search result more carefully and re-orders "
            "by true relevance. Improves accuracy for technical queries. "
            "Tune reranker_top_n: 12 = balanced, 8 = fast, 20 = thorough."
        ),
        impact_note="Adds ~0.3-0.6s per query (12 candidates, CPU)",
        config_section="retrieval",
        config_key="reranker_enabled",
        default=True,
        requires=["hybrid-search"],
    ),

    # --- SECURITY ----------------------------------------------------------

    FeatureDefinition(
        feature_id="pii-scrubber",
        display_name="PII Scrubber",
        category="Security",
        description=(
            "Removes personally identifiable information before "
            "sending text to online APIs."
        ),
        detail=(
            "Scans for emails, phone numbers, SSNs before sending to "
            "external LLMs. Only in online mode. Required for compliance."
        ),
        impact_note="Minimal (<50ms)",
        config_section="security",
        config_key="pii_sanitization",
        default=True,
    ),

    FeatureDefinition(
        feature_id="audit-log",
        display_name="Audit Logging",
        category="Security",
        description=(
            "Records every query, source access, and configuration "
            "change to tamper-evident log files."
        ),
        detail=(
            "Timestamped JSON logs of queries, document access, LLM "
            "responses, and config changes. Required for compliance."
        ),
        impact_note="Minimal (disk I/O only)",
        config_section="security",
        config_key="audit_logging",
        default=True,
    ),

    # --- COST --------------------------------------------------------------

    FeatureDefinition(
        feature_id="cost-tracker",
        display_name="API Cost Tracker",
        category="Cost",
        description=(
            "Tracks token usage and estimated cost for every "
            "online API call."
        ),
        detail=(
            "Logs token counts and calculates cost per query. Enforces "
            "daily budget limits. Only relevant in online API mode."
        ),
        impact_note="None (accounting only)",
        config_section="cost",
        config_key="track_enabled",
        default=True,
    ),
]


# --- FEATURE REGISTRY CLASS ------------------------------------------------

class FeatureRegistry:
    """
    Reads/writes feature toggles in the YAML config file.

    This is the SINGLE interface for both CLI and GUI to manage features.
    The GUI will instantiate this class and call get_feature_catalog()
    to render toggle switches.
    """

    def __init__(self, config_path: str = "config/default_config.yaml"):
        """
        Initialize with path to the YAML config file.

        PARAMETERS:
            config_path: str -- Path to default_config.yaml
                               (relative to project root or absolute)
        """
        self.config_path = Path(config_path)
        self._catalog = {f.feature_id: f for f in FEATURE_CATALOG}

        # Load YAML if it exists
        self._yaml_data = {}
        if self.config_path.exists():
            try:
                import yaml
                self._yaml_data = yaml.safe_load(
                    self.config_path.read_text(encoding="utf-8")
                ) or {}
            except Exception as e:
                print(f"[WARN] Could not load {config_path}: {e}")

    def _get_current_state(self, feature: FeatureDefinition) -> bool:
        """
        Read the current on/off state from YAML config.

        HOW: Each feature has a config_section (e.g., "retrieval") and
        config_key (e.g., "reranker_enabled"). This method walks that
        two-level path in the YAML dict: yaml_data["retrieval"]["reranker_enabled"].
        Returns the feature's default if not found in YAML.
        """
        section = self._yaml_data.get(feature.config_section, {})
        if isinstance(section, dict):
            return bool(section.get(feature.config_key, feature.default))
        return feature.default

    def _set_state(self, feature: FeatureDefinition, enabled: bool):
        """
        Write the on/off state to user_overrides.yaml (not default_config).

        Uses save_config_field() so shipped defaults stay pristine.
        """
        from src.core.config import save_config_field
        dotted_key = "{}.{}".format(feature.config_section, feature.config_key)
        save_config_field(dotted_key, enabled)

        # Update in-memory cache
        if feature.config_section not in self._yaml_data:
            self._yaml_data[feature.config_section] = {}
        self._yaml_data[feature.config_section][feature.config_key] = enabled

    # -----------------------------------------------------------------
    # PUBLIC API (used by CLI and future GUI)
    # -----------------------------------------------------------------

    def get_feature_catalog(self) -> List[Dict[str, Any]]:
        """
        Get all features with current state -- FOR GUI RENDERING.

        Returns a list of dicts, each containing:
            feature_id, display_name, category, description,
            detail, impact_note, enabled (current state),
            default, requires

        The GUI maps each dict to a toggle switch widget.
        """
        catalog = []
        for feat in FEATURE_CATALOG:
            entry = asdict(feat)
            entry["enabled"] = self._get_current_state(feat)
            catalog.append(entry)
        return catalog

    def get_categories(self) -> List[str]:
        """Get unique categories in display order -- FOR GUI TAB RENDERING."""
        seen = []
        for f in FEATURE_CATALOG:
            if f.category not in seen:
                seen.append(f.category)
        return seen

    def list_features(self):
        """
        Print all features grouped by category with current status.
        Used by: rag-features list
        """
        categories = self.get_categories()

        print()
        print("=" * 65)
        print("  HybridRAG3 Feature Toggles")
        print("=" * 65)

        for cat in categories:
            features = [f for f in FEATURE_CATALOG if f.category == cat]
            print(f"\n  [{cat.upper()}]")
            print(f"  {'-' * 60}")

            for feat in features:
                state = self._get_current_state(feat)
                icon = "[ON] " if state else "[OFF]"
                color_hint = "green" if state else "gray"

                print(f"    {icon} {feat.display_name}")
                print(f"          ID: {feat.feature_id}")
                print(f"          {feat.description}")
                if feat.impact_note:
                    print(f"          Performance: {feat.impact_note}")
                print()

        print("=" * 65)
        print("  Commands:")
        print("    rag-features enable <feature-id>")
        print("    rag-features disable <feature-id>")
        print("    rag-features status")
        print("=" * 65)
        print()

    def enable(self, feature_id: str) -> bool:
        """Enable a feature by ID. Returns True if successful."""
        if feature_id not in self._catalog:
            print(f"[FAIL] Unknown feature: '{feature_id}'")
            print(f"       Available: {', '.join(self._catalog.keys())}")
            return False

        feat = self._catalog[feature_id]

        # Check dependencies
        for dep_id in feat.requires:
            if dep_id in self._catalog:
                dep_state = self._get_current_state(self._catalog[dep_id])
                if not dep_state:
                    print(f"[WARN] '{feat.display_name}' works best with "
                          f"'{self._catalog[dep_id].display_name}' enabled.")

        self._set_state(feat, True)
        print(f"[OK] {feat.display_name} -- ENABLED")
        print(f"     {feat.description}")
        if feat.impact_note:
            print(f"     Performance impact: {feat.impact_note}")
        return True

    def disable(self, feature_id: str) -> bool:
        """Disable a feature by ID. Returns True if successful."""
        if feature_id not in self._catalog:
            print(f"[FAIL] Unknown feature: '{feature_id}'")
            print(f"       Available: {', '.join(self._catalog.keys())}")
            return False

        feat = self._catalog[feature_id]

        # Warn about dependents
        for other in FEATURE_CATALOG:
            if feature_id in other.requires:
                other_state = self._get_current_state(other)
                if other_state:
                    print(f"[WARN] '{other.display_name}' depends on this. "
                          f"Consider disabling it too.")

        self._set_state(feat, False)
        print(f"[OK] {feat.display_name} -- DISABLED")
        return True

    def status(self, feature_id: Optional[str] = None):
        """
        Show status of one feature or all features.
        Used by: rag-features status [feature-id]
        """
        if feature_id:
            if feature_id not in self._catalog:
                print(f"[FAIL] Unknown feature: '{feature_id}'")
                return
            feat = self._catalog[feature_id]
            state = self._get_current_state(feat)
            icon = "[ON]" if state else "[OFF]"
            print(f"  {icon} {feat.display_name} ({feat.feature_id})")
            print(f"       {feat.description}")
            if feat.impact_note:
                print(f"       Performance: {feat.impact_note}")
        else:
            self.list_features()

    def is_enabled(self, feature_id: str) -> bool:
        """
        Quick check if a feature is on -- FOR CODE LOGIC.

        Usage in other modules:
            from feature_registry import FeatureRegistry
            reg = FeatureRegistry()
            if reg.is_enabled("hallucination-filter"):
                engine = GroundedQueryEngine(...)
            else:
                engine = QueryEngine(...)
        """
        if feature_id not in self._catalog:
            return False
        return self._get_current_state(self._catalog[feature_id])


# --- CLI ENTRY POINT -------------------------------------------------------
# Called by: python -m feature_registry <command> [feature-id]
# Or from PowerShell: rag-features <command> [feature-id]
# =========================================================================

def main():
    """CLI handler for feature management."""
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        print("""
HybridRAG3 Feature Manager
===========================
Usage:
  python feature_registry.py list                    Show all features
  python feature_registry.py enable <feature-id>     Turn a feature ON
  python feature_registry.py disable <feature-id>    Turn a feature OFF
  python feature_registry.py status [feature-id]     Check status

Feature IDs:
  hallucination-filter   5-step anti-hallucination pipeline
  hybrid-search          Semantic + keyword combined search
  reranker               Cross-encoder result re-scoring
  pii-scrubber           Remove PII before sending to APIs
  audit-log              Tamper-evident query/access logging
  cost-tracker           API token usage and spend tracking
""")
        return

    # Find config path (look in common locations)
    config_candidates = [
        Path("config/default_config.yaml"),
        Path("default_config.yaml"),
        Path(os.environ.get("HYBRIDRAG_CONFIG", "config/default_config.yaml")),
    ]
    config_path = None
    for c in config_candidates:
        if c.exists():
            config_path = str(c)
            break
    if not config_path:
        config_path = "config/default_config.yaml"

    reg = FeatureRegistry(config_path)
    command = args[0].lower()

    if command == "list":
        reg.list_features()

    elif command == "enable" and len(args) > 1:
        reg.enable(args[1])

    elif command == "disable" and len(args) > 1:
        reg.disable(args[1])

    elif command == "status":
        if len(args) > 1:
            reg.status(args[1])
        else:
            reg.status()

    elif command == "catalog-json":
        # Machine-readable output for GUI integration
        import json
        print(json.dumps(reg.get_feature_catalog(), indent=2))

    else:
        print(f"[FAIL] Unknown command: '{command}'")
        print("       Run with 'help' for usage.")


if __name__ == "__main__":
    main()
