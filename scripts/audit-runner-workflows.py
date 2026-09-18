#!/usr/bin/env python3
# ruff: noqa: ANN001, ANN201, ARG001, D103, EM101, EM102, N999, PLR2004, RUF100, TRY003
# pylint: disable=invalid-name,too-many-branches,too-many-locals
# pylint: disable=too-many-boolean-expressions,too-many-lines,too-many-statements
"""Fail closed when workflow routing or remote action pins escape fleet policy."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml  # pylint: disable=import-error

SHA_RE = re.compile(r"[0-9a-f]{40}")
RUNNER_IMAGE_PREFIX = r"ghcr\.io/f5-sales-demo/self-hosted-runner@sha256:"
IMAGE_DIGEST_RE = re.compile(RUNNER_IMAGE_PREFIX + r"[0-9a-f]{64}")
SAFE_RUNNER_LABEL_RE = re.compile(r"[a-z0-9][a-z0-9.-]*")
CANONICAL_REPOSITORY_LABEL = "${{ github.event.repository.name }}"
PULL_REQUEST_EVENT = "github.event_name == 'pull_request' && "
PULL_REQUEST_HEAD_REPO = "github.event.pull_request.head.repo.full_name"
PULL_REQUEST_SOURCE = PULL_REQUEST_HEAD_REPO + " == github.repository"
PULL_REQUEST_GUARD = PULL_REQUEST_EVENT + PULL_REQUEST_SOURCE
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
CALLABLE_DOCKER_GUARD = (
    "github.event_name == 'workflow_dispatch' || "
    "(github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name == github.repository)"
)
DEFAULT_BRANCH_DOCKER_GUARD = (
    "github.event_name == 'workflow_dispatch' || "
    "(github.event_name == 'push' && "
    "(github.ref == format('refs/heads/{0}', "
    "github.event.repository.default_branch) || "
    "startsWith(github.ref, 'refs/tags/v'))) || "
    "(github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name == github.repository)"
)
TAG_ONLY_DOCKER_GUARD = "startsWith(github.ref, 'refs/tags/v')"
SCHEDULED_DEFAULT_BRANCH_DOCKER_GUARD = (
    "github.event_name == 'workflow_dispatch' || "
    "github.event_name == 'schedule' || "
    "(github.event_name == 'push' && "
    "github.ref == format('refs/heads/{0}', github.event.repository.default_branch) && "
    "github.ref_protected == true)"
)
PAGES_DOCKER_GUARD = (
    "github.event_name == 'workflow_dispatch' || "
    "(github.event_name == 'push' && "
    "github.ref == format('refs/heads/{0}', "
    "github.event.repository.default_branch)) || "
    "(github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name == github.repository)"
)
SOCKETLESS_ROUTE_EXPRESSION = (
    "${{ inputs.socketless_runner_label || "
    'fromJSON(format(\'["self-hosted","Linux","X64","{0}",'
    '"ubuntu-24.04"]\', github.event.repository.name)) }}'
)
CONTAINER_ROUTE_EXPRESSION = (
    "${{ inputs.container_build_runner_label || "
    'fromJSON(format(\'["self-hosted","Linux","X64","{0}",'
    '"container-build"]\', github.event.repository.name)) }}'
)
ARC_SOCKET_EXPR = "${{ inputs.socketless_runner_label || 'managed-socketless' }}"
BUILD_EXPR = "${{ inputs.container_build_runner_label || 'managed-container-build' }}"
HOSTED_SOCKET_EXPR = "${{ inputs.socketless_runner_label || 'ubuntu-latest' }}"
HOSTED_BUILD_EXPR = "${{ inputs.container_build_runner_label || 'ubuntu-24.04' }}"
# fmt: off
CANONICAL_SUPER_LINTER_INPUTS = {
    "socketless_runner_label": "${{ github.repository == 'f5-sales-demo/xcsh' && 'xcsh-socketless' || 'managed-socketless' }}",
    "container_build_runner_label": "${{ github.repository == 'f5-sales-demo/xcsh' && 'xcsh-container-build' || 'managed-container-build' }}",
}
# fmt: on
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
# fmt: on
DOCS_ICONS_REPOSITORY = "f5-sales-demo/docs-icons"
DOCS_SOCKETLESS_ROUTE_EXPRESSION = "${{ github.repository == 'f5-sales-demo/docs-icons' && 'docs-socketless' || 'managed-socketless' }}"  # fmt: skip
DOCS_SOCKETLESS_ROUTE_LABELS = {DOCS_ICONS_REPOSITORY: "docs-socketless"}
RELEASE_CHAIN_REPOSITORIES = frozenset(
    {
        "f5-sales-demo/api-specs-enriched",
        "f5-sales-demo/marketplace",
        "f5-sales-demo/multi-cloud-networking",
        "f5-sales-demo/terraform-provider-xcsh",
    }
)
RELEASE_CHAIN_LINKED_ISSUE_ROUTE_EXPRESSION = (
    "${{ (github.repository == 'f5-sales-demo/api-specs-enriched' || "
    "github.repository == 'f5-sales-demo/marketplace' || "
    "github.repository == 'f5-sales-demo/multi-cloud-networking' || "
    "github.repository == 'f5-sales-demo/terraform-provider-xcsh') && "
    "'ubuntu-latest' || (github.repository == 'f5-sales-demo/docs-icons' && "
    "'docs-socketless' || 'managed-socketless') }}"
)
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
            raise AuditError(f"xcsh candidate grants are invalid for {label}")


class AuditError(ValueError):
    """A deterministic workflow policy violation."""


def workflow_on(value):
    return value.get("on", value.get(True)) if isinstance(value, dict) else None


def benchmark_trust_guard_is_allowed(repository, relative, job_id, route_label, guard):
    """Require the generic same-repository guard for direct restricted routes."""
    del repository, relative, job_id, route_label
    return guard == BENCHMARK_TRUST_GUARD


def load_policy(path, repository):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"cannot read runner policy: {exc}") from exc
    if raw.get("schema_version") != 5:
        raise AuditError("runner policy schema_version must be 5")
    repositories = raw.get("repositories")
    if not isinstance(repositories, dict) or repository not in repositories:
        raise AuditError(f"repository is not governed: {repository}")
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise AuditError("runner policy profiles must be a non-empty object")
    validate_arc_attestations(raw)
    exceptions = raw.get("hosted_exceptions", {}).get(repository, {})
    if not isinstance(exceptions, dict):
        raise AuditError("repository hosted exceptions must be an object")
    return raw, exceptions


def validate_arc_attestations(policy):
    """Validate immutable ARC runtime evidence and exact restricted-job grants."""
    attestations = policy.get("arc_attestations")
    if not isinstance(attestations, dict):
        raise AuditError("runner policy ARC attestations must be an object")
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
        if not isinstance(name, str) or not SAFE_RUNNER_LABEL_RE.fullmatch(name):
            raise AuditError("ARC attestation names must be safe strings")
        if not isinstance(spec, dict) or set(spec) != fields:
            raise AuditError("ARC attestation fields are incomplete or unknown")
        label = spec["label"]
        repositories = spec["repositories"]
        if not isinstance(label, str) or not SAFE_RUNNER_LABEL_RE.fullmatch(label):
            raise AuditError("ARC attestation label must be a safe string")
        if label in labels:
            raise AuditError(f"duplicate ARC attestation label: {label}")
        labels.add(label)
        valid_repositories = True
        for item in repositories if isinstance(repositories, list) else ():
            if not isinstance(item, str) or item.count("/") != 1:
                valid_repositories = False
        if (
            not isinstance(spec["runner_profile"], str)
            or not SAFE_RUNNER_LABEL_RE.fullmatch(spec["runner_profile"])
            or not isinstance(spec["vm_size"], str)
            or not spec["vm_size"].startswith("Standard_")
            or not isinstance(spec["cpu_limit"], int)
            or spec["cpu_limit"] <= 0
            or not isinstance(spec["memory_limit_bytes"], int)
            or spec["memory_limit_bytes"] <= 0
            or not isinstance(spec["docker_socket"], bool)
            or not isinstance(spec["image"], str)
            or not IMAGE_DIGEST_RE.fullmatch(spec["image"])
            or not isinstance(repositories, list)
            or not repositories
            or not valid_repositories
            or len(repositories) != len(set(repositories))
        ):
            raise AuditError(f"ARC attestation is malformed: {name}")
    restricted = policy.get("restricted_routes")
    if not isinstance(restricted, dict):
        raise AuditError("restricted_routes must be an object")
    grant_fields = {"repository", "workflow", "job"}
    for label, grants in restricted.items():
        if label not in labels or not isinstance(grants, list) or not grants:
            raise AuditError("restricted route must name an attested label and grants")
        identities = set()
        for grant in grants:
            if not isinstance(grant, dict) or set(grant) != grant_fields:
                raise AuditError("restricted route grant fields are invalid")
            identity = (grant["repository"], grant["workflow"], grant["job"])
            if (
                not all(isinstance(item, str) and item for item in identity)
                or not grant["workflow"].startswith(".github/workflows/")
                or identity in identities
            ):
                raise AuditError("restricted route grant is malformed or duplicated")
            identities.add(identity)


def remote_dependency(value):
    if not isinstance(value, str):
        raise AuditError(f"uses must be a string, got {value!r}")
    if value.startswith(("./", "docker://")):
        return None
    if "@" not in value:
        raise AuditError(f"remote action has no revision: {value}")
    _, revision = value.rsplit("@", 1)
    if not SHA_RE.fullmatch(revision):
        raise AuditError(f"remote action is not commit-pinned: {value}")
    return value


def expected_self_hosted_labels(profile, profiles):
    labels = ["self-hosted", "Linux", "X64", CANONICAL_REPOSITORY_LABEL]
    if profile:
        if profile not in profiles:
            raise AuditError(f"unknown runner profile: {profile}")
        labels.extend(profiles[profile].get("labels", []))
    return labels


def docker_socket_value(profiles, profile):
    spec = profiles.get(profile)
    return spec.get("docker_socket") if isinstance(spec, dict) else None


def repository_routes(policy, repository):
    """Parse the repository's exact legacy or ARC scheduling routes."""
    profiles = policy.get("profiles", {})
    runner = policy.get("repositories", {}).get(repository, {}).get("runner", {})
    if not isinstance(runner, dict) or set(runner) - {"profiles", "arc_scale_sets"}:
        raise AuditError("repository runner policy has unknown fields")
    scale_sets = runner.get("arc_scale_sets")
    if scale_sets is not None:
        if "profiles" in runner:
            raise AuditError(
                "repository runner policy cannot combine ARC scale sets and legacy profiles",
            )
        if not isinstance(scale_sets, dict) or not scale_sets:
            raise AuditError("repository ARC scale sets must be a non-empty object")
        profiles_by_label = {}
        attestations = policy.get("arc_attestations", {})
        attestations_by_label = {}
        for name, spec in scale_sets.items():
            if not isinstance(name, str) or not re.fullmatch(
                r"[a-z0-9][a-z0-9.-]*",
                name,
            ):
                raise AuditError("repository ARC scale sets must use safe route names")
            if not isinstance(spec, dict) or set(spec) not in (
                {"label", "profile"},
                {"label", "attestation"},
            ):
                raise AuditError("ARC scale set must name one profile or attestation")
            label = spec.get("label")
            profile = spec.get("profile")
            if not isinstance(label, str) or not re.fullmatch(
                r"[a-z0-9][a-z0-9.-]*",
                label,
            ):
                raise AuditError("ARC scale set label must be a safe string")
            attestation_name = spec.get("attestation")
            if attestation_name is not None:
                attestation = attestations.get(attestation_name)
                if (
                    not isinstance(attestation, dict)
                    or attestation.get("label") != label
                    or repository not in attestation.get("repositories", [])
                ):
                    message = "ARC scale set attestation does not authorize repository"
                    raise AuditError(message)
                profile = policy["defaults"]["profile"]
                attestations_by_label[label] = attestation
            elif not isinstance(profile, str) or profile not in profiles:
                raise AuditError("ARC scale set profile must be defined")
            if label in profiles_by_label:
                raise AuditError(f"duplicate ARC scale set label: {label}")
            profiles_by_label[label] = profile
        expected = expected_arc_scale_sets(repository)
        if expected is not None and not arc_scale_sets_match_contract(
            repository,
            scale_sets,
        ):
            raise AuditError(f"{repository} ARC scale-set contract is invalid")
        validate_xcsh_candidate_grants(
            repository,
            scale_sets,
            policy.get("restricted_routes"),
        )
        if expected is None:
            leaked = set(profiles_by_label) & RESERVED_ARC_LABELS
            if leaked:
                message = "reserved ARC scale-set label escaped its cohort"
                raise AuditError(f"{message}: {sorted(leaked)}")
        restricted = policy.get("restricted_routes", {})
        grants_by_label = {}
        for label, grants in restricted.items():
            grants_by_label[label] = {grant_identity(grant) for grant in grants}
        return {
            "kind": "arc",
            "profiles_by_label": profiles_by_label,
            "attestations_by_label": attestations_by_label,
            "restricted_grants": grants_by_label,
        }

    allowed = runner.get("profiles", list(profiles))
    if (
        not isinstance(allowed, list)
        or not allowed
        or not all(isinstance(name, str) and name in profiles for name in allowed)
        or len(allowed) != len(set(allowed))
    ):
        raise AuditError("repository runner profiles must be unique known profiles")
    return {"kind": "legacy", "profiles": tuple(allowed)}


def grant_identity(grant):
    return grant["repository"], grant["workflow"], grant["job"]


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
    """Resolve only exact governed scalar or fork-safe compute expressions."""
    value = tuple(value) if isinstance(value, list) else value
    value = canonical_caller_label(value, repository)
    if value in {HOSTED_SOCKET_EXPR, HOSTED_BUILD_EXPR}:
        return "ubuntu-latest" if value == HOSTED_SOCKET_EXPR else "ubuntu-24.04"
    if value == RELEASE_CHAIN_LINKED_ISSUE_ROUTE_EXPRESSION:
        if repository in RELEASE_CHAIN_REPOSITORIES:
            return "ubuntu-latest"
        return DOCS_SOCKETLESS_ROUTE_LABELS.get(repository, "managed-socketless")
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


def profile_for_route(runs_on, profiles, routes, repository):
    """Resolve one security-equivalent profile for an exact scheduling route."""
    if routes["kind"] == "arc":
        if not isinstance(runs_on, str):
            return None
        label = canonical_route_label(runs_on, repository)
        return routes["profiles_by_label"].get(label)
    if not isinstance(runs_on, list) or len(runs_on) != 5:
        return None
    expected_prefix = ["self-hosted", "Linux", "X64"]
    repository_labels = {
        repository.split("/", 1)[1],
        CANONICAL_REPOSITORY_LABEL,
    }
    if runs_on[:3] != expected_prefix or runs_on[3] not in repository_labels:
        return None
    candidates = []
    for name in routes["profiles"]:
        spec = profiles[name]
        if spec.get("labels") == [runs_on[4]]:
            candidates.append((name, spec))
    if candidates:
        reference = candidates[0][1]
        if all(spec == reference for _, spec in candidates[1:]):
            return candidates[0][0]
    return None


def reusable_definition_profile(repository, relative, job_id, runs_on):
    """Resolve only the two governed reusable definitions' exact fallback expressions."""
    if repository != "f5-sales-demo/docs-control":
        return None
    expected = REUSABLE_DEFINITION_ROUTES.get((relative, job_id))
    if expected is None or runs_on != expected[1]:
        return None
    return expected[0]


def validate_reusable_runner_inputs(job, routes, profiles, default_profile, repository):
    """Validate runner-label inputs on governed reusable workflow calls."""
    uses = job.get("uses")
    target = uses.rsplit("@", 1)[0] if isinstance(uses, str) and "@" in uses else uses
    if target not in REUSABLE_RUNNER_WORKFLOWS:
        return
    inputs = job.get("with", {})
    if not isinstance(inputs, dict):
        raise AuditError("reusable workflow with inputs must be an object")
    names = ("socketless_runner_label", "container_build_runner_label")
    values = {name: inputs.get(name, "") for name in names}
    supplied = {name for name, value in values.items() if value not in (None, "")}
    if supplied and supplied != set(names):
        raise AuditError("ARC reusable runner labels must be supplied together")
    if not supplied:
        if routes["kind"] == "arc":
            raise AuditError("ARC reusable workflow call requires both runner labels")
        return
    if routes["kind"] != "arc":
        raise AuditError("legacy reusable workflow calls cannot override runner labels")
    conditional = set()
    for name, value in values.items():
        if value == CANONICAL_SUPER_LINTER_INPUTS[name]:
            conditional.add(name)
    if conditional:
        if conditional != set(names) or not target.endswith("/super-linter.yml"):
            message = "conditional ARC runner labels must be supplied together"
            raise AuditError(message)
        for name in names:
            values[name] = canonical_caller_label(values[name], repository)
    expected_profiles = {
        "socketless_runner_label": default_profile,
        "container_build_runner_label": "container-build",
    }
    for name, expected_profile in expected_profiles.items():
        value = values[name]
        safe_label = isinstance(value, str) and SAFE_RUNNER_LABEL_RE.fullmatch(value)
        if not safe_label:
            raise AuditError(f"{name} must be a safe scalar label")
        resolved = routes["profiles_by_label"].get(value)
        if resolved != expected_profile or expected_profile not in profiles:
            raise AuditError(f"{name} does not match its policy-approved profile")


def exception_for(exceptions, relative, job_id):
    workflow = exceptions.get(relative, {})
    if not isinstance(workflow, dict):
        raise AuditError(f"hosted exception workflow must be an object: {relative}")
    return workflow.get(job_id)


def trigger_names(workflow):
    value = workflow_on(workflow)
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    if isinstance(value, dict) and all(isinstance(item, str) for item in value):
        return set(value)
    raise AuditError("workflow trigger is malformed")


def dependency_names(job):
    needs = job.get("needs") if isinstance(job, dict) else None
    if isinstance(needs, str):
        return (needs,)
    if isinstance(needs, list) and all(isinstance(name, str) for name in needs):
        return tuple(needs)
    return ()


def transitive_dependencies(workflow, job_id):
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return set(), False

    reachable = set()
    active = {job_id}
    cycle = False

    def visit(name) -> None:
        nonlocal cycle
        if name in active:
            cycle = True
            return
        if name in reachable:
            return
        reachable.add(name)
        dependency_job = jobs.get(name)
        if not isinstance(dependency_job, dict):
            return
        active.add(name)
        for dependency in dependency_names(dependency_job):
            visit(dependency)
        active.remove(name)

    for dependency in dependency_names(jobs.get(job_id)):
        visit(dependency)
    return reachable, cycle


# pylint: disable-next=too-many-arguments,too-many-locals
def audit_docker_route(  # noqa: PLR0917
    workflow, relative, job_id, job, profiles, routes, repository, profile
):
    errors: list[str] = []
    if profile not in profiles or not profiles[profile].get("docker_socket"):
        return errors
    try:
        triggers = trigger_names(workflow)
    except AuditError as exc:
        return [f"Docker-capable job has a malformed trigger: {exc}"]
    allowed = {"pull_request", "push", "schedule", "workflow_call", "workflow_dispatch"}
    if not triggers or not triggers <= allowed:
        errors.append(
            "Docker-capable jobs require a protected push, same-repository PR, or manual dispatch",
        )
        return errors
    if triggers == {"workflow_dispatch"}:
        return errors
    tag_only = job.get("if") == TAG_ONLY_DOCKER_GUARD and "push" in triggers
    if not tag_only:
        pages_build = (
            relative,
            job_id,
        ) == (".github/workflows/github-pages-deploy.yml", "build")
        if pages_build:
            expected_guard = PAGES_DOCKER_GUARD
        elif "schedule" in triggers:
            expected_guard = SCHEDULED_DEFAULT_BRANCH_DOCKER_GUARD
        elif triggers == {"pull_request"}:
            expected_guard = PULL_REQUEST_GUARD
        elif "push" in triggers or triggers == {"workflow_call"}:
            expected_guard = DEFAULT_BRANCH_DOCKER_GUARD
        else:
            expected_guard = CALLABLE_DOCKER_GUARD
        if job.get("if") != expected_guard:
            errors.append(
                "Docker-capable PR job requires the complete same-repository guard",
            )
    dependencies, cycle = transitive_dependencies(workflow, job_id)
    if cycle:
        errors.append("Docker-capable job dependency graph must be acyclic")
    if "trust-gate" not in dependencies:
        errors.append("Docker-capable PR job requires the socketless trust-gate")
    trust_gate = workflow.get("jobs", {}).get("trust-gate")
    trust_runs_on = trust_gate.get("runs-on") if isinstance(trust_gate, dict) else None
    trust_profile = profile_for_route(trust_runs_on, profiles, routes, repository)
    if trust_profile is None:
        trust_context = repository, relative, "trust-gate", trust_runs_on
        trust_profile = reusable_definition_profile(*trust_context)
    if docker_socket_value(profiles, trust_profile) is not False:
        errors.append("Docker-capable PR job requires a socketless trust-gate job")
    return errors


def step_requires_docker(step):
    """Return whether an executable step needs the Docker socket, not comments."""
    if not isinstance(step, dict):
        return False
    uses = step.get("uses")
    docker_uses = ("docker://", "docker/", "super-linter/super-linter@")
    if isinstance(uses, str) and uses.startswith(docker_uses):
        return True
    run = step.get("run")
    if not isinstance(run, str):
        return False
    executable = "\n".join(line.split("#", 1)[0] for line in run.splitlines())
    return bool(re.search(r"(?<![\w-])docker(?:\s|$)", executable))


def step_has_privileged_package_install(step):
    """Reject self-hosted provisioning assumptions in executable shell content."""
    if not isinstance(step, dict) or not isinstance(step.get("run"), str):
        return False
    executable = "\n".join(line.split("#", 1)[0] for line in step["run"].splitlines())
    return bool(
        re.search(r"(?<![\w-])sudo(?:\s|$)", executable)
        or re.search(r"(?<![\w-])apt(?:-get)?\s+(?:update|install)(?:\s|$)", executable)
    )


# pylint: disable-next=too-many-arguments,too-many-locals
def audit_job(  # noqa: PLR0917
    repository,
    relative,
    job_id,
    job,
    profiles,
    routes,
    exceptions,
    workflow_context,
):
    default_profile, workflow = workflow_context
    errors = []
    if not isinstance(job, dict):
        return [f"{relative}/{job_id}: job must be an object"]
    if "uses" in job:
        try:
            remote_dependency(job["uses"])
            validate_reusable_runner_inputs(job, routes, profiles, default_profile, repository)  # fmt: skip
        except AuditError as exc:
            errors.append(f"{relative}/{job_id}: {exc}")
        if "runs-on" in job:
            errors.append(
                f"{relative}/{job_id}: reusable-workflow job cannot set runs-on",
            )
        return errors
    runs_on = job.get("runs-on")
    exception = exception_for(exceptions, relative, job_id)
    if exception is not None:
        allowed = exception.get("runs_on") if isinstance(exception, dict) else None
        resolved_runs_on = canonical_route_label(runs_on, repository)
        if allowed == "matrix":
            if not isinstance(runs_on, str) or "matrix." not in runs_on:
                errors.append(
                    f"{relative}/{job_id}: hosted exception requires matrix runs-on",
                )
        elif resolved_runs_on != allowed:
            errors.append(
                f"{relative}/{job_id}: hosted runs-on {runs_on!r} does not match {allowed!r}",
            )
        reason = exception.get("reason") if isinstance(exception, dict) else None
        if not isinstance(reason, str) or len(reason.strip()) < 12:
            errors.append(f"{relative}/{job_id}: hosted exception reason is incomplete")
    else:
        profile = default_profile
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
            message = "xcsh candidate job requires the exact manual route expression"
            errors.append(f"{relative}/{job_id}: {message}")
        if is_manual_route and dynamic_route_labels is None:
            message = "xcsh manual route requires its workflow_dispatch job context"
            errors.append(f"{relative}/{job_id}: {message}")
        resolved_profile = profile_for_route(runs_on, profiles, routes, repository)
        if dynamic_route_labels is not None:
            profiles_by_label = routes["profiles_by_label"]
            dynamic_profiles = set(map(profiles_by_label.get, dynamic_route_labels))
            if None not in dynamic_profiles and len(dynamic_profiles) == 1:
                resolved_profile = next(iter(dynamic_profiles))
        if resolved_profile is None:
            definition_context = repository, relative, job_id, runs_on
            resolved_profile = reusable_definition_profile(*definition_context)
        if resolved_profile is not None:
            profile = resolved_profile
        valid_route = resolved_profile is not None
        if not valid_route:
            errors.append(
                f"{relative}/{job_id}: runs-on must use the canonical repository route, got {runs_on!r}",
            )
        canonical_label = canonical_route_label(runs_on, repository)
        route_labels = dynamic_route_labels or frozenset({canonical_label})
        for route_label in route_labels:
            grants = routes.get("restricted_grants", {}).get(route_label)
            if grants is None:
                continue
            if identity not in grants:
                errors.append(
                    f"{relative}/{job_id}: restricted runner route is not allowlisted",
                )
            if runs_on == route_label and not benchmark_trust_guard_is_allowed(
                repository,
                relative,
                job_id,
                route_label,
                job.get("if"),
            ):
                errors.append(
                    f"{relative}/{job_id}: direct restricted route requires the exact same-repository benchmark guard",
                )
        steps = job.get("steps", [])
        requires_docker = any(map(step_requires_docker, steps))
        profile_has_socket = docker_socket_value(profiles, profile) is True
        if requires_docker and not profile_has_socket:
            errors.append(
                f"{relative}/{job_id}: Docker workload requires a Docker socket profile",
            )
        route_errors = audit_docker_route(
            workflow,
            relative,
            job_id,
            job,
            profiles,
            routes,
            repository,
            profile,
        )
        route_prefix = f"{relative}/{job_id}: "
        errors.extend(route_prefix + error for error in route_errors)
        if any(map(step_has_privileged_package_install, steps)):
            errors.append(
                f"{relative}/{job_id}: self-hosted jobs cannot use sudo or apt package installation",
            )
    for index, step in enumerate(job.get("steps", [])):
        if not isinstance(step, dict) or "uses" not in step:
            continue
        try:
            remote_dependency(step["uses"])
        except AuditError as exc:
            errors.append(f"{relative}/{job_id}/steps/{index}: {exc}")
    return errors


def audit_repository(root, repository, policy_path):
    root = Path(root)
    policy, exceptions = load_policy(policy_path, repository)
    profiles = policy["profiles"]
    routes = repository_routes(policy, repository)
    errors = []
    actual_exceptions = set()
    workflows = root / ".github/workflows"
    for path in sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml"))):
        relative = path.relative_to(root).as_posix()
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"{relative}: cannot parse workflow: {exc}")
            continue
        if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
            errors.append(f"{relative}: workflow must contain a jobs object")
            continue
        if workflow_on(document) is None:
            errors.append(f"{relative}: workflow trigger is missing")
        for job_id, job in document["jobs"].items():
            if exception_for(exceptions, relative, job_id) is not None:
                actual_exceptions.add((relative, job_id))
            errors.extend(
                audit_job(
                    repository,
                    relative,
                    job_id,
                    job,
                    profiles,
                    routes,
                    exceptions,
                    (policy["defaults"]["profile"], document),
                )
            )
    declared_exceptions = set()
    for workflow, jobs in exceptions.items():
        for job_id in jobs:
            declared_exceptions.add((workflow, job_id))
    for workflow, job_id in sorted(declared_exceptions - actual_exceptions):
        errors.append(f"unused hosted exception: {workflow}/{job_id}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--repository", required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".github/config/self-hosted-runner-policy.json"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        errors = audit_repository(args.root, args.repository, args.policy)
    except AuditError as exc:
        errors = [str(exc)]
    if args.json:
        print(json.dumps({"repository": args.repository, "errors": errors}, indent=2))
    else:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        if not errors:
            message = "validated workflow routing and immutable pins"
            print(f"{message} for {args.repository}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
