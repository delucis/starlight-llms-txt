#!/usr/bin/env python3
# ruff: noqa: ANN001, ANN201, D101, D103, EM101, EM102, RUF100, TRY003
# pylint: disable=invalid-name,too-many-branches,broad-exception-caught,import-error,too-many-lines,too-many-locals,too-many-statements,too-many-boolean-expressions
# fmt: off
"""Fail-closed authorization for self-hosted routes and Zizmor findings."""

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

import yaml

POLICY_SCHEMA_VERSION = 5
IMAGE_DIGEST_RE = re.compile(
    r"ghcr\.io/f5-sales-demo/self-hosted-runner@sha256:[0-9a-f]{64}"
)
DOCKER_POLICY = {
    "host_socket": "/run/f5-actions-runner/container-build/docker.sock",
    "runner_socket": "/run/docker.sock",
    "data_root": "/data/actions-runners/container-build-docker",
    "cache_max": "20g",
    "cgroup_parent": "f5-actions-container-build.slice",
    "minimum_version": "29.2.1",
    "target_version": "29.7.2",
}
DISPATCHER_POLICY = {
    "repositories": [],
    "memory": "48g",
    "cpus": "18",
    "standard_runners": 3,
    "container_build_runners": 1,
    "request_budget": 80,
}

TOP_FIELDS = {
    "schema_version",
    "docker",
    "dispatcher",
    "defaults",
    "profiles",
    "arc_attestations",
    "restricted_routes",
    "hosted_exceptions",
    "repositories",
}
JOB_FIELDS = {
    "runs_on",
    "environment",
    "permissions",
    "allowed_secrets",
    "triggers",
    "if",
}
SECRET_RE = re.compile(
    r"\bsecrets\s*(?:\.\s*([A-Za-z_][A-Za-z0-9_]*)\b|"
    r"\[\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\2\s*\])"
)
SECRET_CONTEXT_RE = re.compile(r"\bsecrets\b")
EXPRESSION_RE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
FORBIDDEN_TRIGGERS = {"pull_request_target", "workflow_run", "repository_dispatch"}
ALLOWED_TRIGGERS = {"schedule", "workflow_dispatch", "push", "pull_request"}
ALLOWED_PERMISSIONS = {
    "contents": {"read", "none"},
    "checks": {"write", "read", "none"},
}
ZIZMOR_EXIT_BY_SEVERITY = {
    "Informational": 11,
    "Low": 12,
    "Medium": 13,
    "High": 14,
}
SOCKETLESS_ROUTE_EXPRESSION = (
    "${{ inputs.socketless_runner_label || "
    "fromJSON(format('[\"self-hosted\",\"Linux\",\"X64\",\"{0}\","
    "\"ubuntu-24.04\"]', github.event.repository.name)) }}"
)
CONTAINER_ROUTE_EXPRESSION = (
    "${{ inputs.container_build_runner_label || "
    "fromJSON(format('[\"self-hosted\",\"Linux\",\"X64\",\"{0}\","
    "\"container-build\"]', github.event.repository.name)) }}"
)
ARC_SOCKET_EXPR = "${{ inputs.socketless_runner_label || 'managed-socketless' }}"
BUILD_EXPR = "${{ inputs.container_build_runner_label || 'managed-container-build' }}"
CANONICAL_SUPER_LINTER_INPUTS = {
    "socketless_runner_label": "${{ github.repository == 'f5-sales-demo/xcsh' && 'xcsh-socketless' || 'managed-socketless' }}",
    "container_build_runner_label": "${{ github.repository == 'f5-sales-demo/xcsh' && 'xcsh-container-build' || 'managed-container-build' }}",
}
XCSH_REPOSITORY = "f5-sales-demo/xcsh"
XCSH_COMPUTE_WORKFLOW = ".github/workflows/compute-benchmark.yml"
XCSH_MANUAL_COMPUTE_ROUTE_EXPRESSION = "${{ needs.prepare.outputs.runner_label }}"
XCSH_MANUAL_COMPUTE_ROUTE_LABELS = {
    "workload": frozenset(
        {
            "xcsh-compute",
            "xcsh-compute-16-vcpu-candidate",
            "xcsh-compute-f32-candidate",
        }
    ),
    "dag-control": frozenset({"xcsh-compute-16-vcpu-candidate"}),
    "dag-candidate-native": frozenset({"xcsh-compute-16-vcpu-candidate"}),
    "dag-candidate-rust": frozenset({"xcsh-compute-16-vcpu-candidate"}),
    "dag-candidate-typescript": frozenset({"xcsh-compute-16-vcpu-candidate"}),
}
XCSH_CANDIDATE_RESTRICTED_GRANTS = {
    label: frozenset(
        (XCSH_REPOSITORY, XCSH_COMPUTE_WORKFLOW, job_id)
        for job_id, labels in XCSH_MANUAL_COMPUTE_ROUTE_LABELS.items()
        if label in labels
    )
    for label in (
        "xcsh-compute-16-vcpu-candidate",
        "xcsh-compute-f32-candidate",
    )
}
# fmt: off
XCSH_CANDIDATE_GRANT_IDENTITIES = frozenset().union(*XCSH_CANDIDATE_RESTRICTED_GRANTS.values())
DOCS_ICONS_REPOSITORY = "f5-sales-demo/docs-icons"
DOCS_SOCKETLESS_ROUTE_EXPRESSION = "${{ github.repository == 'f5-sales-demo/docs-icons' && 'docs-socketless' || 'managed-socketless' }}"  # fmt: skip
DOCS_SOCKETLESS_ROUTE_LABELS = {DOCS_ICONS_REPOSITORY: "docs-socketless"}
BENCHMARK_TRUST_GUARD = (
    "github.event_name == 'pull_request' && "
    "github.event.action == 'labeled' && "
    "github.event.label.name == 'compute-benchmark-approved' && "
    "github.event.pull_request.head.repo.full_name == github.repository"
)
TRUSTED_COMPUTE_ROUTE_EXPRESSIONS = {
    "terraform-provider-xcsh-compute": (
        "${{ github.event.pull_request.head.repo.full_name == github.repository && "
        "'terraform-provider-xcsh-compute' || 'ubuntu-latest' }}"
    ),
}
REUSABLE_RUNNER_WORKFLOWS = {
    "f5-sales-demo/docs-control/.github/workflows/github-pages-deploy.yml",
    "f5-sales-demo/docs-control/.github/workflows/super-linter.yml",
}
REUSABLE_DEFINITION_ROUTES = {
    (".github/workflows/github-pages-deploy.yml", "trust-gate"): (
        "ubuntu-24.04",
        SOCKETLESS_ROUTE_EXPRESSION,
    ),
    (".github/workflows/github-pages-deploy.yml", "build"): (
        "container-build",
        CONTAINER_ROUTE_EXPRESSION,
    ),
    (".github/workflows/github-pages-deploy.yml", "deploy"): (
        "ubuntu-24.04",
        SOCKETLESS_ROUTE_EXPRESSION,
    ),
    (".github/workflows/super-linter.yml", "trust-gate"): (
        "ubuntu-24.04",
        ARC_SOCKET_EXPR,
    ),
    (".github/workflows/super-linter.yml", "lint"): (
        "container-build",
        BUILD_EXPR,
    ),
    (".github/workflows/super-linter.yml", "shell-unit-tests"): (
        "ubuntu-24.04",
        ARC_SOCKET_EXPR,
    ),
}


DOCS_ARC_COHORT = frozenset(
    f"f5-sales-demo/{name}"
    for name in (
        "docs",
        "docs-builder",
        "docs-icons",
        "docs-theme",
        "i18n-core",
        "starlight-llms-txt",
    )
)
MANAGED_ARC_COHORT = frozenset(
    f"f5-sales-demo/{name}"
    for name in (
        "administration",
        "api-protection",
        "api-specs",
        "apt-repo",
        "bot-advanced",
        "bot-standard",
        "cdn",
        "cdn-simulator",
        "console",
        "csd",
        "ddos",
        "demo-resource-template",
        "demo-resources",
        "devcontainer",
        "dns",
        "docs-control",
        "marketplace",
        "marketplace-claude-code",
        "multi-cloud-networking",
        "nginx",
        "observability",
        "origin-server",
        "starlight-mega-menu",
        "traffic-generator",
        "vscode-xcsh",
        "waf",
        "was",
        "webapp-api-protection",
        "xcsh-action",
        "xcsh-chrome-extension",
    )
)
ARC_SHARED_CONTRACTS = (
    (
        DOCS_ARC_COHORT,
        {
            "socketless": {
                "label": "docs-socketless",
                "profile": "ubuntu-24.04",
            },
            "container-build": {
                "label": "docs-container-build",
                "profile": "container-build",
            },
        },
    ),
    (
        MANAGED_ARC_COHORT,
        {
            "socketless": {
                "label": "managed-socketless",
                "profile": "ubuntu-24.04",
            },
            "container-build": {
                "label": "managed-container-build",
                "profile": "container-build",
            },
        },
    ),
    (
        frozenset({"f5-sales-demo/api-specs-enriched"}),
        {
            "socketless": {
                "label": "managed-socketless",
                "profile": "ubuntu-24.04",
            },
            "container-build": {
                "label": "managed-container-build",
                "profile": "container-build",
            },
            "compute": {
                "label": "api-specs-enriched-compute",
                "profile": "ubuntu-24.04",
            },
        },
    ),
    (
        frozenset({"f5-sales-demo/terraform-provider-xcsh"}),
        {
            "socketless": {
                "label": "managed-socketless",
                "attestation": "terraform-provider-xcsh-d8",
            },
            "container-build": {
                "label": "managed-container-build",
                "profile": "container-build",
            },
            "compute": {
                "label": "terraform-provider-xcsh-compute",
                "attestation": "terraform-provider-xcsh-d16",
            },
        },
    ),
    (
        frozenset({"f5-sales-demo/xcsh"}),
        {
            "socketless": {
                "label": "xcsh-socketless",
                "profile": "ubuntu-24.04",
            },
            "container-build": {
                "label": "xcsh-container-build",
                "profile": "container-build",
            },
            "compute": {
                "label": "xcsh-compute",
                "profile": "ubuntu-24.04",
            },
        },
    ),
)
XCSH_CANDIDATE_SCALE_SETS = {
    "compute-16-vcpu-candidate": {
        "label": "xcsh-compute-16-vcpu-candidate",
        "attestation": "xcsh-compute-16-vcpu-candidate",
    },
    "compute-f32-candidate": {
        "label": "xcsh-compute-f32-candidate",
        "attestation": "xcsh-compute-f32-candidate",
    },
}
RESERVED_ARC_LABELS = frozenset(
    {
        "api-specs-enriched-compute",
        "docs-container-build",
        "docs-socketless",
        "managed-container-build",
        "managed-socketless",
        "terraform-provider-xcsh-compute",
        "xcsh-container-build",
        "xcsh-compute",
        "xcsh-compute-16-vcpu-candidate",
        "xcsh-compute-f32-candidate",
        "xcsh-socketless",
    }
)


def expected_arc_scale_sets(repository):
    """Return the exact shared-label contract for a governed ARC cohort."""
    for cohort, contract in ARC_SHARED_CONTRACTS:
        if repository in cohort:
            return contract
    return None


def arc_scale_sets_match_contract(repository, scale_sets):
    """Accept the stable contract or xcsh's exact temporary benchmark extension."""
    expected = expected_arc_scale_sets(repository)
    if scale_sets == expected:
        return True
    if repository != XCSH_REPOSITORY or expected is None:
        return False
    return scale_sets == {**expected, **XCSH_CANDIDATE_SCALE_SETS}


def validate_xcsh_candidate_grants(repository, scale_sets, restricted_routes):
    """Require the exact manual-job grant set for each xcsh candidate label."""
    expected_scale_sets = expected_arc_scale_sets(repository)
    candidate_contract = (
        repository == XCSH_REPOSITORY
        and expected_scale_sets is not None
        and scale_sets == {**expected_scale_sets, **XCSH_CANDIDATE_SCALE_SETS}
    )
    if not candidate_contract:
        return
    for label, expected in XCSH_CANDIDATE_RESTRICTED_GRANTS.items():
        grants = (restricted_routes or {}).get(label, [])
        actual = {
            (grant.get("repository"), grant.get("workflow"), grant.get("job"))
            for grant in grants
            if isinstance(grant, dict)
        }
        if actual != expected:
            raise PolicyError(f"xcsh candidate grants are invalid for {label}")


class PolicyError(ValueError):
    pass


def benchmark_trust_guard_is_allowed(repository, relative, job_id, route_label, guard):
    """Require the generic same-repository guard for direct restricted routes."""
    del repository, relative, job_id, route_label
    return guard == BENCHMARK_TRUST_GUARD


def validate_zizmor_result(exit_code, findings):
    """Validate Zizmor's documented findings exit contract before authorization."""
    if not isinstance(findings, list):
        raise PolicyError("Zizmor output must be a JSON array")
    if not findings:
        if exit_code != 0:
            raise PolicyError("Zizmor empty output requires exit 0")
        return
    if exit_code == 0:
        raise PolicyError("Zizmor exit 0 requires an empty finding array")

    expected_exit = 0
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise PolicyError(f"Zizmor finding {index} must be an object")
        determinations = finding.get("determinations")
        if not isinstance(determinations, dict):
            raise PolicyError(
                f"Zizmor finding {index} determinations must be an object"
            )
        severity = determinations.get("severity")
        if severity not in ZIZMOR_EXIT_BY_SEVERITY:
            raise PolicyError(
                f"Zizmor finding {index} has invalid severity: {severity!r}"
            )
        expected_exit = max(expected_exit, ZIZMOR_EXIT_BY_SEVERITY[severity])

    if exit_code != expected_exit:
        raise PolicyError(
            f"Zizmor findings require exit {expected_exit}, received {exit_code}"
        )


def strict_object(value, allowed, context):
    if not isinstance(value, dict):
        raise PolicyError(f"{context} must be an object")
    unknown = set(value) - set(allowed)
    if unknown:
        raise PolicyError(f"{context} has unknown fields: {sorted(unknown)}")
    return value


def governed_repositories(path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        repos = raw["repo_classes"]["repos"]
    except Exception as exc:
        raise PolicyError(f"cannot read governance inventory {path}: {exc}") from exc
    valid_mapping = isinstance(repos, dict) and bool(repos)
    valid_entries = valid_mapping and all(
        isinstance(name, str) and isinstance(repo_class, str)
        for name, repo_class in repos.items()
    )
    if not valid_entries:
        raise PolicyError(
            "governance repo_classes.repos must be a non-empty string mapping"
        )
    return {f"f5-sales-demo/{name}" for name in repos}


# pylint: disable-next=too-many-locals
def validate_arc_contract(attestations, restricted_routes):
    """Validate immutable ARC runtime attestations and exact job grants."""
    if not isinstance(attestations, dict):
        raise PolicyError("arc_attestations must be an object")
    fields = {
        "label",
        "runner_profile",
        "image",
        "vm_size",
        "cpu_limit",
        "memory_limit_bytes",
        "docker_socket",
        "repositories",
    }
    labels = set()
    for name, spec in attestations.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", name):
            raise PolicyError("ARC attestation names must be safe strings")
        if not isinstance(spec, dict) or set(spec) != fields:
            raise PolicyError("ARC attestation fields are incomplete or unknown")
        label = spec["label"]
        repositories = spec["repositories"]
        if (
            not isinstance(label, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", label)
            or label in labels
            or not isinstance(spec["runner_profile"], str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", spec["runner_profile"])
            or not isinstance(spec["image"], str)
            or not IMAGE_DIGEST_RE.fullmatch(spec["image"])
            or not isinstance(spec["vm_size"], str)
            or not spec["vm_size"].startswith("Standard_")
            or not isinstance(spec["cpu_limit"], int)
            or spec["cpu_limit"] <= 0
            or not isinstance(spec["memory_limit_bytes"], int)
            or spec["memory_limit_bytes"] <= 0
            or not isinstance(spec["docker_socket"], bool)
            or not isinstance(repositories, list)
            or not repositories
            or len(repositories) != len(set(repositories))
            or not all(
                isinstance(item, str) and item.count("/") == 1 for item in repositories
            )
        ):
            raise PolicyError(f"ARC attestation is malformed: {name}")
        labels.add(label)
    if not isinstance(restricted_routes, dict):
        raise PolicyError("restricted_routes must be an object")
    grant_fields = {"repository", "workflow", "job"}
    for label, grants in restricted_routes.items():
        if label not in labels or not isinstance(grants, list) or not grants:
            raise PolicyError("restricted route must name an attested label and grants")
        identities = set()
        for grant in grants:
            if not isinstance(grant, dict) or set(grant) != grant_fields:
                raise PolicyError("restricted route grant fields are invalid")
            identity = (grant["repository"], grant["workflow"], grant["job"])
            if (
                not all(isinstance(item, str) and item for item in identity)
                or not grant["workflow"].startswith(".github/workflows/")
                or identity in identities
            ):
                raise PolicyError("restricted route grant is malformed or duplicated")
            identities.add(identity)


def repository_runner_routes(
    workflows,
    profiles,
    default_profile,
    repository,
    arc_attestations=None,
    restricted_routes=None,
):
    """Return one strict route-to-profile model for legacy or ARC runners."""
    runner = workflows.get("runner", {})
    if not isinstance(runner, dict) or set(runner) - {"profiles", "arc_scale_sets"}:
        raise PolicyError("repository runner policy has unknown fields")
    scale_sets = runner.get("arc_scale_sets")
    if scale_sets is not None:
        if "profiles" in runner:
            raise PolicyError(
                "repository runner policy cannot combine ARC scale sets and legacy profiles"
            )
        if not isinstance(scale_sets, dict) or not scale_sets:
            raise PolicyError("repository ARC scale sets must be a non-empty object")
        profiles_by_label = {}
        attestations = arc_attestations or {}
        attestations_by_label = {}
        for name, spec in scale_sets.items():
            if not isinstance(name, str) or not re.fullmatch(
                r"[a-z0-9][a-z0-9.-]*", name
            ):
                raise PolicyError("repository ARC scale sets must use safe route names")
            if not isinstance(spec, dict) or set(spec) not in (
                {"label", "profile"},
                {"label", "attestation"},
            ):
                raise PolicyError("ARC scale set must name one profile or attestation")
            label = spec.get("label")
            profile = spec.get("profile")
            if not isinstance(label, str) or not re.fullmatch(
                r"[a-z0-9][a-z0-9.-]*", label
            ):
                raise PolicyError("ARC scale set label must be a safe string")
            attestation_name = spec.get("attestation")
            if attestation_name is not None:
                attestation = attestations.get(attestation_name)
                if (
                    not isinstance(attestation, dict)
                    or attestation.get("label") != label
                    or repository not in attestation.get("repositories", [])
                ):
                    raise PolicyError(
                        "ARC scale set attestation does not authorize repository"
                    )
                profile = default_profile
                attestations_by_label[label] = attestation
            elif not isinstance(profile, str) or profile not in profiles:
                raise PolicyError("ARC scale set profile must be defined")
            if label in profiles_by_label:
                raise PolicyError(f"duplicate ARC scale set label: {label}")
            profiles_by_label[label] = profile
        expected = expected_arc_scale_sets(repository)
        if expected is not None and not arc_scale_sets_match_contract(
            repository, scale_sets
        ):
            raise PolicyError(f"{repository} ARC scale-set contract is invalid")
        validate_xcsh_candidate_grants(repository, scale_sets, restricted_routes)
        if expected is None:
            leaked = set(profiles_by_label) & RESERVED_ARC_LABELS
            if leaked:
                message = "reserved ARC scale-set label escaped its cohort"
                raise PolicyError(f"{message}: {sorted(leaked)}")
        grants_by_label = {
            label: {
                (grant["repository"], grant["workflow"], grant["job"])
                for grant in grants
            }
            for label, grants in (restricted_routes or {}).items()
        }
        return {
            "kind": "arc",
            "profiles_by_route": profiles_by_label,
            "attestations_by_label": attestations_by_label,
            "restricted_grants": grants_by_label,
        }

    allowed = runner.get("profiles", [default_profile])
    valid_profiles = isinstance(allowed, list) and bool(allowed)
    known_profiles = valid_profiles and all(
        isinstance(profile, str) and profile in profiles for profile in allowed
    )
    unique_profiles = known_profiles and len(set(allowed)) == len(allowed)
    required_profiles = unique_profiles and {
        default_profile,
        "container-build",
    }.issubset(allowed)
    if not required_profiles:
        raise PolicyError(
            "repository runner profiles must be a unique array of existing profiles "
            "that includes the default and container-build"
        )
    basename = repository.split("/", 1)[1]
    profiles_by_route: dict[tuple, str] = {}
    specs_by_route: dict[tuple, object] = {}
    for profile in allowed:
        spec = profiles[profile]
        labels = spec.get("labels", [profile]) if isinstance(spec, dict) else None
        if (
            not isinstance(labels, list)
            or len(labels) != 1
            or not isinstance(labels[0], str)
        ):
            raise PolicyError(
                f"profile {profile!r} must define exactly one route label"
            )
        for repository_label in (basename, "${{ github.event.repository.name }}"):
            route = ("self-hosted", "Linux", "X64", repository_label, labels[0])
            if route in profiles_by_route and specs_by_route[route] != spec:
                raise PolicyError(
                    f"route label {labels[0]!r} maps to non-equivalent profiles"
                )
            profiles_by_route.setdefault(route, profile)
            specs_by_route.setdefault(route, spec)
    return {"kind": "legacy", "profiles_by_route": profiles_by_route}


def canonical_caller_label(value, repository):
    """Resolve the exact governed caller expression for the repository under audit."""
    for name, expression in CANONICAL_SUPER_LINTER_INPUTS.items():
        if value != expression:
            continue
        prefix = "xcsh" if repository == XCSH_REPOSITORY else "managed"
        suffix = "container-build"
        if name == "socketless_runner_label":
            suffix = "socketless"
        return f"{prefix}-{suffix}"
    return value


def canonical_route_label(value, repository):
    value = tuple(value) if isinstance(value, list) else value
    value = canonical_caller_label(value, repository)
    if value == DOCS_SOCKETLESS_ROUTE_EXPRESSION:
        return DOCS_SOCKETLESS_ROUTE_LABELS.get(repository, "managed-socketless")
    for label, expression in TRUSTED_COMPUTE_ROUTE_EXPRESSIONS.items():
        if value == expression:
            return label
    return value


def trusted_dynamic_route_labels(repository, relative, job_id, runs_on, workflow):
    """Resolve the one manual xcsh route expression in its exact job context."""
    triggers = workflow_on(workflow)
    if (
        repository != XCSH_REPOSITORY
        or relative != XCSH_COMPUTE_WORKFLOW
        or runs_on != XCSH_MANUAL_COMPUTE_ROUTE_EXPRESSION
        or not isinstance(triggers, dict)
        or set(triggers) != {"workflow_dispatch"}
    ):
        return None
    return XCSH_MANUAL_COMPUTE_ROUTE_LABELS.get(job_id)


def resolve_route(runs_on, routes, repository=None):
    route = tuple(runs_on) if isinstance(runs_on, list) else runs_on
    if repository is not None:
        route = canonical_route_label(route, repository)
    return routes["profiles_by_route"].get(route)


def canonical_routes(routes):
    return tuple(routes["profiles_by_route"])


def reusable_definition_profile(repository, relative, job_id, runs_on):
    """Resolve only the governed reusable definitions' exact route expressions."""
    if repository != "f5-sales-demo/docs-control":
        return None
    expected = REUSABLE_DEFINITION_ROUTES.get((relative, job_id))
    if expected is None or runs_on != expected[1]:
        return None
    return expected[0]


def validate_reusable_runner_inputs(job, routes, default_profile, repository):
    """Validate policy-approved scalar labels passed to governed reusable calls."""
    uses = job.get("uses")
    target = uses.rsplit("@", 1)[0] if isinstance(uses, str) and "@" in uses else uses
    if target not in REUSABLE_RUNNER_WORKFLOWS:
        return
    inputs = job.get("with", {})
    if not isinstance(inputs, dict):
        raise PolicyError("reusable workflow with inputs must be an object")
    names = ("socketless_runner_label", "container_build_runner_label")
    values = {name: inputs.get(name, "") for name in names}
    supplied = {name for name, value in values.items() if value not in (None, "")}
    if supplied and supplied != set(names):
        raise PolicyError("ARC reusable runner labels must be supplied together")
    if not supplied:
        if routes["kind"] == "arc":
            raise PolicyError("ARC reusable workflow call requires both runner labels")
        return
    if routes["kind"] != "arc":
        raise PolicyError(
            "legacy reusable workflow calls cannot override runner labels"
        )
    conditional = set()
    for name, value in values.items():
        if value == CANONICAL_SUPER_LINTER_INPUTS[name]:
            conditional.add(name)
    if conditional:
        if conditional != set(names) or not target.endswith("/super-linter.yml"):
            message = "conditional ARC runner labels must be supplied together"
            raise PolicyError(message)
        for name in names:
            values[name] = canonical_caller_label(values[name], repository)
    expected_profiles = {
        "socketless_runner_label": default_profile,
        "container_build_runner_label": "container-build",
    }
    for name, expected_profile in expected_profiles.items():
        value = values[name]
        if not isinstance(value, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9.-]*", value
        ):
            raise PolicyError(f"{name} must be a safe scalar label")
        if routes["profiles_by_route"].get(value) != expected_profile:
            raise PolicyError(f"{name} does not match its policy-approved profile")


def permissions_within_ceiling(permissions, context):
    if not isinstance(permissions, dict):
        raise PolicyError(f"{context} must be an object")
    for scope, access in permissions.items():
        if scope not in ALLOWED_PERMISSIONS or access not in ALLOWED_PERMISSIONS[scope]:
            raise PolicyError(
                f"{context} exceeds the permission ceiling: {scope}={access}"
            )


# pylint: disable-next=too-many-locals
def load_policy(path, governance_path, repository):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PolicyError(f"cannot read policy {path}: {exc}") from exc
    strict_object(raw, TOP_FIELDS, "policy")
    if raw.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise PolicyError(f"unsupported schema_version: {raw.get('schema_version')!r}")
    if raw.get("docker") != DOCKER_POLICY:
        raise PolicyError(f"policy docker contract must equal {DOCKER_POLICY!r}")
    if raw.get("dispatcher") != DISPATCHER_POLICY:
        raise PolicyError(
            f"policy dispatcher contract must equal {DISPATCHER_POLICY!r}"
        )
    repositories = raw.get("repositories")
    governed = governed_repositories(governance_path)
    if not isinstance(repositories, dict) or set(repositories) != governed:
        missing = (
            sorted(governed - set(repositories or {}))
            if isinstance(repositories, dict)
            else sorted(governed)
        )
        extra = (
            sorted(set(repositories or {}) - governed)
            if isinstance(repositories, dict)
            else []
        )
        raise PolicyError(
            f"policy/governance repository mismatch: missing={missing}, extra={extra}"
        )
    if repository not in repositories:
        raise PolicyError(f"repository {repository!r} is not present in policy")
    profiles = raw.get("profiles")
    default_profile = raw.get("defaults", {}).get("profile")
    if (
        not isinstance(profiles, dict)
        or not isinstance(default_profile, str)
        or default_profile not in profiles
    ):
        raise PolicyError("policy default profile must name an existing profile")
    validate_arc_contract(raw.get("arc_attestations"), raw.get("restricted_routes"))
    result = {}
    workflows = repositories[repository]
    if not isinstance(workflows, dict):
        raise PolicyError("repository policy must be a workflow object")
    routes = repository_runner_routes(
        workflows,
        profiles,
        default_profile,
        repository,
        raw["arc_attestations"],
        raw["restricted_routes"],
    )
    for workflow, jobs in workflows.items():
        if workflow == "runner":
            continue
        if not isinstance(workflow, str) or not workflow.startswith(
            ".github/workflows/"
        ):
            raise PolicyError(f"invalid workflow key: {workflow!r}")
        if not isinstance(jobs, dict) or not jobs:
            raise PolicyError(f"{workflow} must contain jobs")
        for job_id, spec in jobs.items():
            strict_object(spec, JOB_FIELDS, f"{workflow}/{job_id}")
            if set(spec) != JOB_FIELDS:
                raise PolicyError(
                    f"{workflow}/{job_id} must define exactly {sorted(JOB_FIELDS)}"
                )
            configured_route = spec["runs_on"]
            route_type_is_valid = (
                isinstance(configured_route, str)
                if routes["kind"] == "arc"
                else isinstance(configured_route, list)
                and all(isinstance(item, str) for item in configured_route)
            )
            if (
                not route_type_is_valid
                or resolve_route(configured_route, routes) is None
            ):
                raise PolicyError(
                    f"{workflow}/{job_id}.runs_on must be one canonical repository route"
                )
            if not isinstance(spec["permissions"], dict):
                raise PolicyError(f"{workflow}/{job_id}.permissions must be an object")
            permissions_within_ceiling(
                spec["permissions"], f"{workflow}/{job_id}.permissions"
            )
            if (
                not isinstance(spec["allowed_secrets"], list)
                or not all(
                    isinstance(secret, str)
                    and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", secret)
                    for secret in spec["allowed_secrets"]
                )
                or len(set(spec["allowed_secrets"])) != len(spec["allowed_secrets"])
            ):
                raise PolicyError(
                    f"{workflow}/{job_id}.allowed_secrets must be a unique array"
                )
            if not isinstance(spec["triggers"], dict) or not all(
                isinstance(x, str) for x in spec["triggers"]
            ):
                raise PolicyError(
                    f"{workflow}/{job_id}.triggers must be an exact trigger mapping"
                )
            unknown_triggers = set(spec["triggers"]) - ALLOWED_TRIGGERS
            if unknown_triggers:
                raise PolicyError(
                    f"{workflow}/{job_id} has untrusted trigger(s): {sorted(unknown_triggers)}"
                )
            result[(workflow, job_id)] = spec
    return result, default_profile, routes


def route_component(item):
    if isinstance(item, dict) and set(item) == {"Key"} and isinstance(item["Key"], str):
        return item["Key"]
    raise PolicyError(f"malformed route component: {item!r}")


def normalize_location(location):
    if not isinstance(location, dict):
        raise PolicyError("location must be an object")
    symbolic = location.get("symbolic")
    if not isinstance(symbolic, dict):
        raise PolicyError("location.symbolic is missing")
    key = symbolic.get("key")
    if not isinstance(key, dict) or set(key) != {"Local"}:
        raise PolicyError("location.symbolic.key must identify exactly one Local path")
    local = key.get("Local")
    if not isinstance(local, dict) or set(local) != {"verbatim_path"}:
        raise PolicyError("location Local key must contain only verbatim_path")
    path = local.get("verbatim_path") if isinstance(local, dict) else None
    if not isinstance(path, str):
        raise PolicyError("location.symbolic.key.Local.verbatim_path is missing")
    route_container = symbolic.get("route")
    route = route_container.get("route") if isinstance(route_container, dict) else None
    if not isinstance(route, list):
        raise PolicyError("location.symbolic.route.route must be an array")
    parts = [route_component(item) for item in route]
    if parts.count("jobs") != 1:
        raise PolicyError(f"route must contain exactly one jobs component: {parts}")
    index = parts.index("jobs")
    if index + 2 >= len(parts) or parts[index + 2 :] != ["runs-on"]:
        raise PolicyError(f"route must identify exactly one job runs-on: {parts}")
    normalized = PurePosixPath(path).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    path_parts = PurePosixPath(normalized).parts
    if PurePosixPath(normalized).is_absolute() or ".." in path_parts:
        raise PolicyError(
            f"finding path is not a safe repository-relative path: {path!r}"
        )
    workflow_roots = (".github/workflows/", "workflows/")
    if not normalized.startswith(workflow_roots):
        raise PolicyError(
            f"finding path is outside governed workflow roots: {normalized!r}"
        )
    return normalized, parts[index + 1], parts


def workflow_on(workflow):
    return workflow.get("on", workflow.get(True))


def trigger_names(workflow):
    value = workflow_on(workflow)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return sorted(value)
    if isinstance(value, dict) and all(isinstance(x, str) for x in value):
        return sorted(value)
    raise PolicyError("workflow on must be a string, string array, or mapping")


def effective_permissions(workflow, job):
    value = job.get("permissions", workflow.get("permissions"))
    if value is None:
        raise PolicyError("effective permissions are implicit")
    if isinstance(value, str) and value in {"read-all", "write-all"}:
        raise PolicyError("permissions shortcuts are forbidden")
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and v in {"read", "write", "none"} for k, v in value.items()
    ):
        raise PolicyError("effective permissions must be an explicit scope mapping")
    permissions_within_ceiling(value, "effective permissions")
    return value


def strip_wrapping_parentheses(expression):
    expression = expression.strip()
    while expression.startswith("(") and expression.endswith(")"):
        depth = 0
        wraps_all = True
        for index, character in enumerate(expression):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth < 0:
                    return expression
                if depth == 0 and index != len(expression) - 1:
                    wraps_all = False
                    break
        if depth != 0 or not wraps_all:
            break
        expression = expression[1:-1].strip()
    return expression


def split_boolean(expression, operator):
    parts = []
    depth = 0
    start = 0
    index = 0
    while index < len(expression):
        character = expression[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise PolicyError("job if expression has unbalanced parentheses")
        elif depth == 0 and expression.startswith(operator, index):
            parts.append(expression[start:index].strip())
            start = index + len(operator)
            index += len(operator) - 1
        index += 1
    if depth != 0:
        raise PolicyError("job if expression has unbalanced parentheses")
    parts.append(expression[start:].strip())
    return parts


def condition_excludes_pull_request(expression):
    """Conservatively prove every branch excludes pull_request execution."""
    if not isinstance(expression, str) or "${{" in expression:
        return False
    expression = strip_wrapping_parentheses(expression)
    if expression == "github.event_name != 'pull_request'":
        return True
    disjunction = split_boolean(expression, "||")
    if len(disjunction) > 1:
        return all(condition_excludes_pull_request(branch) for branch in disjunction)
    conjunction = split_boolean(expression, "&&")
    if len(conjunction) > 1:
        return any(condition_excludes_pull_request(branch) for branch in conjunction)
    return False


def walk(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, (*path, str(index)))
    elif isinstance(value, str):
        yield path, value


def secret_references(text):
    names = set()
    for expression in EXPRESSION_RE.finditer(text):
        body = expression.group(1)
        covered = []
        for match in SECRET_RE.finditer(body):
            names.add(match.group(1) or match.group(3))
            covered.append(match.span())
        for context in SECRET_CONTEXT_RE.finditer(body):
            if not any(
                start <= context.start() and context.end() <= end
                for start, end in covered
            ):
                raise PolicyError(
                    "dynamic or malformed secrets expression is forbidden"
                )
    return names


# pylint: disable-next=too-many-locals
def validate_job(_repository, workflow, job, spec, _default_profile, _routes):
    errors = []
    runs_on = job.get("runs-on")
    expected_route = spec["runs_on"]
    if runs_on != expected_route:
        errors.append(f"runs-on must equal {expected_route!r}, got {runs_on!r}")
    if job.get("environment") != spec["environment"]:
        errors.append(f"environment mismatch: {job.get('environment')!r}")
    try:
        permissions = effective_permissions(workflow, job)
        if permissions != spec["permissions"]:
            errors.append(f"permissions mismatch: {permissions!r}")
    except PolicyError as exc:
        errors.append(str(exc))
    try:
        triggers = trigger_names(workflow)
        if triggers != sorted(spec["triggers"]):
            errors.append(f"trigger mismatch: {triggers!r}")
        if workflow_on(workflow) != spec["triggers"]:
            errors.append("complete trigger structure does not exactly match policy")
        if set(triggers) & FORBIDDEN_TRIGGERS:
            errors.append(
                f"forbidden trigger(s): {sorted(set(triggers) & FORBIDDEN_TRIGGERS)}"
            )
        unknown_triggers = set(triggers) - ALLOWED_TRIGGERS
        if unknown_triggers:
            errors.append(f"untrusted trigger(s): {sorted(unknown_triggers)}")
        on = workflow_on(workflow)
        if "push" in triggers:
            push = on.get("push") if isinstance(on, dict) else None
            if not isinstance(push, dict) or push.get("branches") != ["main"]:
                errors.append("push must be bounded exactly to main")
    except PolicyError as exc:
        errors.append(str(exc))
    if job.get("if") != spec["if"]:
        errors.append("job if expression does not exactly match policy")
    if "pull_request" in trigger_names(
        workflow
    ) and not condition_excludes_pull_request(job.get("if")):
        errors.append("job if does not provably exclude pull_request execution")
    references = set()
    for path, text in walk(job):
        try:
            names = secret_references(text)
        except PolicyError as exc:
            errors.append(f"{exc} at {'.'.join(path)}")
            continue
        references.update(names)
        if names and ("run" in path or not ({"env", "with"} & set(path))):
            errors.append(f"secret reference in unsupported location {'.'.join(path)}")
    if references != set(spec["allowed_secrets"]):
        errors.append(f"secret set mismatch: {sorted(references)!r}")
    for step in job.get("steps", []):
        if (
            isinstance(step, dict)
            and isinstance(step.get("uses"), str)
            and step["uses"].split("@", 1)[0] == "actions/checkout"
            and step.get("with", {}).get("persist-credentials") is not False
        ):
            errors.append(  # noqa: PERF401 - conditional validation is clearer inline
                "checkout must use literal persist-credentials: false"
            )
    return errors


# pylint: disable-next=too-many-locals
def inventory(root, repository, policy, default_profile, routes):
    """Inventory jobs whose exact route is authorized by repository policy.

    Per-job entries add stricter exception constraints; they are not a job allowlist.
    """
    actual = {}
    paths = (
        *(root / ".github/workflows").glob("*.y*ml"),
        *(root / "workflows").glob("*.y*ml"),
    )
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        try:
            workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise PolicyError(f"cannot parse {relative}: {exc}") from exc
        if not isinstance(workflow, dict) or not isinstance(
            workflow.get("jobs", {}), dict
        ):
            raise PolicyError(f"malformed workflow {relative}")
        basename = repository.split("/", 1)[1]
        for job_id, job in workflow.get("jobs", {}).items():
            if not isinstance(job, dict):
                raise PolicyError(f"malformed job {relative}/{job_id}")
            if "uses" in job:
                validate_reusable_runner_inputs(job, routes, default_profile, repository)  # fmt: skip
            runs_on = job.get("runs-on")
            identity = (repository, relative, job_id)
            dynamic_route_labels = trusted_dynamic_route_labels(
                repository,
                relative,
                job_id,
                runs_on,
                workflow,
            )
            is_candidate_job = identity in XCSH_CANDIDATE_GRANT_IDENTITIES
            is_manual_route = runs_on == XCSH_MANUAL_COMPUTE_ROUTE_EXPRESSION
            if is_candidate_job and not is_manual_route:
                message = (
                    "xcsh candidate job requires the exact manual route expression"
                )
                raise PolicyError(f"{relative}/{job_id}: {message}")
            if is_manual_route and dynamic_route_labels is None:
                message = "xcsh manual route requires its workflow_dispatch job context"
                raise PolicyError(f"{relative}/{job_id}: {message}")
            if (
                any(
                    identity in grants
                    for grants in routes.get("restricted_grants", {}).values()
                )
                and isinstance(runs_on, str)
                and ("matrix." in runs_on or "github.event.inputs" in runs_on)
            ):
                raise PolicyError(
                    f"{relative}/{job_id}: restricted-route repositories forbid matrix or dispatch-controlled runs-on"
                )
            resolved_profile = resolve_route(runs_on, routes, repository)
            if dynamic_route_labels is not None:
                profiles_by_route = routes["profiles_by_route"]
                dynamic_profiles = set(map(profiles_by_route.get, dynamic_route_labels))
                if None not in dynamic_profiles and len(dynamic_profiles) == 1:
                    resolved_profile = next(iter(dynamic_profiles))
            internal_profile = reusable_definition_profile(
                repository, relative, job_id, runs_on
            )
            if resolved_profile is None:
                resolved_profile = internal_profile
            self_hosted = resolved_profile is not None or (
                isinstance(runs_on, list) and "self-hosted" in runs_on
            )
            arc_prefix = f"{basename}-" if routes["kind"] == "arc" else None
            suspicious = (
                isinstance(runs_on, str)
                and resolved_profile is None
                and (
                    "self-hosted" in runs_on
                    or (arc_prefix is not None and runs_on.startswith(arc_prefix))
                )
            )
            if suspicious:
                raise PolicyError(
                    f"expression or scalar self-hosted runs-on at {relative}/{job_id}"
                )
            if self_hosted:
                key = (relative, job_id)
                if resolved_profile is None:
                    raise PolicyError(
                        f"{relative}/{job_id}: runs-on must use the canonical repository route"
                    )
                canonical_label = canonical_route_label(runs_on, repository)
                route_labels = dynamic_route_labels or frozenset({canonical_label})
                for route_label in route_labels:
                    grants = routes.get("restricted_grants", {}).get(route_label)
                    if grants is None:
                        continue
                    if identity not in grants:
                        raise PolicyError(
                            f"{relative}/{job_id}: restricted runner route is not allowlisted"
                        )
                    if runs_on == route_label and not benchmark_trust_guard_is_allowed(
                        repository,
                        relative,
                        job_id,
                        route_label,
                        job.get("if"),
                    ):
                        raise PolicyError(
                            f"{relative}/{job_id}: direct restricted route requires the exact same-repository benchmark guard"
                        )
                # The exact repository route is the ordinary-job authorization.
                # A per-job entry adds stricter permissions, trigger, and secret checks.
                if key in policy:
                    errors = validate_job(
                        repository,
                        workflow,
                        job,
                        policy[key],
                        default_profile,
                        routes,
                    )
                    if errors:
                        raise PolicyError(f"{relative}/{job_id}: " + "; ".join(errors))
                if internal_profile is None:
                    actual[key] = workflow
    unused = sorted(set(policy) - set(actual))
    if unused:
        raise PolicyError(f"unused policy entries: {unused}")
    return set(actual)


def validate(findings, root, repository, policy_path, governance_path):
    if not isinstance(findings, list):
        raise PolicyError("Zizmor output must be a JSON array")
    policy, default_profile, repository_routes = load_policy(
        policy_path, governance_path, repository
    )
    actual = inventory(root, repository, policy, default_profile, repository_routes)
    if repository_routes["kind"] == "arc":
        if findings:
            raise PolicyError(
                "unexpected Zizmor finding for internally validated ARC scalar routes"
            )
        return [
            (workflow, job_id, ["jobs", job_id, "runs-on"])
            for workflow, job_id in sorted(actual)
        ]

    found = []
    routes = []
    for finding in findings:
        ident = finding.get("ident") if isinstance(finding, dict) else None
        if ident != "self-hosted-runner":
            raise PolicyError(f"unapproved finding: {ident!r}")
        locations = finding.get("locations") if isinstance(finding, dict) else None
        if not isinstance(locations, list) or len(locations) != 1:
            raise PolicyError("each finding must have exactly one location")
        workflow, job_id, route = normalize_location(locations[0])
        key = (workflow, job_id)
        if key not in actual:
            raise PolicyError(f"finding route is not approved: {workflow}/{job_id}")
        found.append(key)
        routes.append((workflow, job_id, route))
    counts = Counter(found)
    duplicates = sorted(key for key, count in counts.items() if count != 1)
    if duplicates:
        raise PolicyError(f"duplicate findings: {duplicates}")
    if set(found) != actual:
        raise PolicyError(
            f"finding/job mismatch: missing={sorted(actual - set(found))}, extra={sorted(set(found) - actual)}"
        )
    return routes


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--governance", type=Path, required=True)
    parser.add_argument("--zizmor-exit", type=int, required=True)
    parser.add_argument("findings", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.repository or args.repository.count("/") != 1:
        print(
            "workflow security validation failed: "
            "an exact --repository owner/name is required",
            file=sys.stderr,
        )
        return 1
    try:
        findings = json.loads(args.findings.read_text(encoding="utf-8"))
        validate_zizmor_result(args.zizmor_exit, findings)
        routes = validate(
            findings, Path.cwd(), args.repository, args.policy, args.governance
        )
    except (OSError, ValueError) as exc:
        print(f"workflow security validation failed: {exc}", file=sys.stderr)
        return 1
    for workflow, job_id, route in routes:
        print(
            f"approved {args.repository}:{workflow}:{job_id} route={json.dumps(route)}"
        )
    print(f"validated {len(routes)} governed self-hosted-runner route(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
