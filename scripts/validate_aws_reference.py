"""TASK-30 static validation of the AWS CloudFormation reference (TEST-34, NFR-11; DEC-0006).

Usage (repository root):  python scripts/validate_aws_reference.py [TEMPLATE]

Validation only: no AWS account is used. Checks the JSON syntax, the allowed resource types, the
single-instance boundary, the private boundary, encryption of the persistent volume, restricted
ingress, least-privilege IAM, centralized logs, a basic alarm, parameters with no secret defaults,
and the explicit non-claims in the description. Standard library only. Exit 0 means every check passed.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "deploy" / "aws" / "abm-reference.json"

ALLOWED_TYPES = {
    "AWS::EC2::Instance",
    "AWS::EC2::Volume",
    "AWS::EC2::VolumeAttachment",
    "AWS::EC2::SecurityGroup",
    "AWS::IAM::Role",
    "AWS::IAM::InstanceProfile",
    "AWS::Logs::LogGroup",
    "AWS::CloudWatch::Alarm",
}
REQUIRED_NON_CLAIMS = {"backup", "disaster", "production"}  # not claimed
SECRET_LIKE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key)"
)
OPEN_CIDRS = {"0.0.0.0/0", "::/0"}


def statements(policy: Any) -> list[dict[str, Any]]:
    return policy.get("Statement", []) if isinstance(policy, dict) else []


def check(template: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    resources = template.get("Resources")
    if not isinstance(resources, dict) or not resources:
        return ["the template has no Resources"]

    types = {name: res.get("Type") for name, res in resources.items()}
    for name, kind in types.items():
        if kind not in ALLOWED_TYPES:
            failures.append(
                f"{name}: resource type {kind} is outside the reference (no database, scaling, load balancing, or backup service)"
            )

    instances = [n for n, k in types.items() if k == "AWS::EC2::Instance"]
    if len(instances) != 1:
        failures.append(
            f"exactly one AWS::EC2::Instance is required (single-instance boundary); found {len(instances)}"
        )

    for name, res in resources.items():
        props = res.get("Properties", {})
        if res.get("Type") == "AWS::EC2::Volume" and props.get("Encrypted") is not True:
            failures.append(f"{name}: the persistent volume must be encrypted")
        if res.get("Type") == "AWS::EC2::Instance":
            if (
                props.get("AssociatePublicIpAddress") is True
                or "NetworkInterfaces" in props
            ):
                failures.append(
                    f"{name}: the instance must stay in a private boundary (no public address)"
                )
            for mapping in props.get("BlockDeviceMappings", []):
                if mapping.get("Ebs", {}).get("Encrypted") is not True:
                    failures.append(f"{name}: every instance volume must be encrypted")
        if res.get("Type") == "AWS::EC2::SecurityGroup":
            for rule in props.get("SecurityGroupIngress", []):
                cidr = rule.get("CidrIp")
                if isinstance(cidr, str) and cidr in OPEN_CIDRS:
                    failures.append(f"{name}: ingress from {cidr} is not allowed")
                if not isinstance(cidr, dict) or "Ref" not in cidr:
                    failures.append(
                        f"{name}: ingress CIDR must come from a parameter, not a literal"
                    )
        if res.get("Type") == "AWS::IAM::Role":
            for policy in props.get("Policies", []):
                for statement in statements(policy.get("PolicyDocument", {})):
                    actions = statement.get("Action", [])
                    actions = [actions] if isinstance(actions, str) else actions
                    if any(a == "*" or str(a).endswith(":*") for a in actions):
                        failures.append(
                            f"{name}: wildcard IAM action is not least privilege"
                        )
                    if statement.get("Resource") == "*":
                        failures.append(
                            f"{name}: wildcard IAM resource is not least privilege"
                        )
        if res.get("Type") == "AWS::Logs::LogGroup" and "RetentionInDays" not in props:
            failures.append(f"{name}: the log group must declare retention")

    alarms = [n for n, k in types.items() if k == "AWS::CloudWatch::Alarm"]
    if not alarms:
        failures.append("at least one basic alarm is required")
    elif instances:
        bound = [
            a
            for a in alarms
            if any(
                d.get("Value") == {"Ref": instances[0]}
                for d in resources[a].get("Properties", {}).get("Dimensions", [])
            )
        ]
        if not bound:
            failures.append("a basic alarm must be bound to the single instance")

    for name, param in template.get("Parameters", {}).items():
        default = param.get("Default")
        if isinstance(default, str) and SECRET_LIKE.search(name + " " + default):
            failures.append(
                f"parameter {name}: secret-like default values are not allowed (use a secret reference)"
            )

    description = str(template.get("Description", "")).lower()
    for word in sorted(REQUIRED_NON_CLAIMS):
        if word not in description:
            failures.append(f"the description must state the non-claim for '{word}'")
    if "not claimed" not in description and "not claim" not in description:
        failures.append("the description must say what is not claimed")

    return failures


def main(argv: list[str]) -> int:
    path = pathlib.Path(argv[0]) if argv else DEFAULT
    try:
        template = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"AWS REFERENCE INVALID: cannot parse {path.name}: {type(exc).__name__}")
        return 1
    failures = check(template)
    if failures:
        print("AWS REFERENCE INVALID:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        f"AWS REFERENCE VALID: {path.name} ({len(template['Resources'])} resources; validation only)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
