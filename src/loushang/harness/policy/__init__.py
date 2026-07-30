"""Product-neutral policy subjects, verdicts, evaluators, and matchers.

Implements the policy verdict (§7.5) and policy model (§8) of
docs/internals/architecture/harness/policy-approval-redesign.md. The package
splits the mechanism into focused modules: `decisions` (verdict values),
`subjects` (subjects and command normalization), `evaluators` (protocols,
rules, chains), `matchers` (concrete matchers), `effects_detection`
(heuristic effect detection), and `engine` (the default Product-injected
rule engine). Risk classification, trust rules, allowlists, and product
defaults remain with Product adapters.
"""

from loushang.harness.policy.decisions import (
    PolicyDecision,
    PolicyDisposition,
    PolicyEvaluationError,
)
from loushang.harness.policy.evaluators import (
    MaybeAwaitable,
    PolicyChainStrategy,
    PolicyEvaluator,
    PolicyEvaluatorChain,
    PolicyMatcher,
    PolicyRule,
    RulePolicyEvaluator,
    evaluate_policy,
)
from loushang.harness.policy.matchers import (
    CommandSubstringMatcher,
    CommandTokenSequenceMatcher,
    ExactToolNameMatcher,
    IncompleteCommandMatcher,
    PathSubstringMatcher,
    ShellPayloadSubstringMatcher,
)
from loushang.harness.policy.subjects import (
    CommandPolicySubject,
    CustomPolicySubject,
    PathPolicySubject,
    PolicySubject,
    ToolPolicySubject,
    build_path_policy_subjects,
    build_tool_policy_subject,
    environment_value_from_env,
    executable_search_path_from_env,
    normalize_command_subject,
)

__all__ = [
    "CommandPolicySubject",
    "CommandSubstringMatcher",
    "CommandTokenSequenceMatcher",
    "CustomPolicySubject",
    "ExactToolNameMatcher",
    "IncompleteCommandMatcher",
    "MaybeAwaitable",
    "PathPolicySubject",
    "PathSubstringMatcher",
    "PolicyChainStrategy",
    "PolicyDecision",
    "PolicyDisposition",
    "PolicyEvaluationError",
    "PolicyEvaluator",
    "PolicyEvaluatorChain",
    "PolicyMatcher",
    "PolicyRule",
    "PolicySubject",
    "RulePolicyEvaluator",
    "ShellPayloadSubstringMatcher",
    "ToolPolicySubject",
    "build_path_policy_subjects",
    "build_tool_policy_subject",
    "environment_value_from_env",
    "evaluate_policy",
    "executable_search_path_from_env",
    "normalize_command_subject",
]
