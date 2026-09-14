"""Development interventions, deliberately separate from conditions A/B/C/D."""

from enum import Enum


class DiagnosticMode(str, Enum):
    NORMAL = "normal"
    NO_POLICY = "no-policy"
    EMPTY_CONTEXT = "empty-context"
    DENY_ALL = "deny-all"
