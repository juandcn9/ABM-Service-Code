"""TASK-30 (TEST-34, NFR-11): the AWS reference is valid, and each rule of the validator is enforced.

Each negative case breaks one property of a copy of the reference and expects the validator to name it.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_aws_reference import check  # type: ignore[import-not-found]

REFERENCE = json.loads(
    (ROOT / "deploy" / "aws" / "abm-reference.json").read_text(encoding="utf-8")
)


def mutated(edit) -> dict:
    template = copy.deepcopy(REFERENCE)
    edit(template)
    return template


def test_the_reference_template_is_valid():
    assert check(REFERENCE) == []


@pytest.mark.parametrize(
    "edit, expected",
    [
        (
            lambda t: t["Resources"]["DataVolume"]["Properties"].update(
                Encrypted=False
            ),
            "must be encrypted",
        ),
        (
            lambda t: t["Resources"]["AppInstance"]["Properties"][
                "BlockDeviceMappings"
            ][0]["Ebs"].update(Encrypted=False),
            "every instance volume must be encrypted",
        ),
        (
            lambda t: t["Resources"]["AppInstance"]["Properties"].update(
                AssociatePublicIpAddress=True
            ),
            "no public address",
        ),
        (
            lambda t: t["Resources"]["ServiceSecurityGroup"]["Properties"][
                "SecurityGroupIngress"
            ][0].update(CidrIp="0.0.0.0/0"),
            "from 0.0.0.0/0 is not allowed",
        ),
        (
            lambda t: t["Resources"]["ServiceSecurityGroup"]["Properties"][
                "SecurityGroupIngress"
            ][0].update(CidrIp="10.0.0.0/8"),
            "must come from a parameter",
        ),
        (
            lambda t: t["Resources"]["InstanceRole"]["Properties"]["Policies"][0][
                "PolicyDocument"
            ]["Statement"][0].update(Action="s3:*"),
            "wildcard IAM action",
        ),
        (
            lambda t: t["Resources"]["InstanceRole"]["Properties"]["Policies"][0][
                "PolicyDocument"
            ]["Statement"][0].update(Resource="*"),
            "wildcard IAM resource",
        ),
        (
            lambda t: t["Resources"].update(
                Database={"Type": "AWS::RDS::DBInstance", "Properties": {}}
            ),
            "outside the reference",
        ),
        (
            lambda t: t["Resources"].update(
                Group={"Type": "AWS::AutoScaling::AutoScalingGroup", "Properties": {}}
            ),
            "outside the reference",
        ),
        (
            lambda t: t["Resources"].update(
                Second={"Type": "AWS::EC2::Instance", "Properties": {}}
            ),
            "exactly one AWS::EC2::Instance",
        ),
        (
            lambda t: t["Resources"].pop("InstanceStatusAlarm"),
            "at least one basic alarm",
        ),
        (
            lambda t: t["Resources"]["InstanceStatusAlarm"]["Properties"].update(
                Dimensions=[]
            ),
            "bound to the single instance",
        ),
        (
            lambda t: t["Resources"]["AppLogGroup"]["Properties"].pop(
                "RetentionInDays"
            ),
            "must declare retention",
        ),
        (
            lambda t: t["Parameters"]["ConfigParameterPrefix"].update(
                Default="db-password-123"
            ),
            "secret-like default",
        ),
        (
            lambda t: t.update(
                Description=t["Description"].replace("backup", "data copies")
            ),
            "non-claim for 'backup'",
        ),
    ],
)
def test_each_rule_names_its_violation(edit, expected):
    failures = check(mutated(edit))
    assert any(expected in failure for failure in failures), failures
