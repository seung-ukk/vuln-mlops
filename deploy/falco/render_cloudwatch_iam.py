"""Render the two reviewed IAM documents; this script makes no AWS calls."""

import argparse
import json
from pathlib import Path


CLUSTER = "vuln-mlops-personal-lab"
REGION = "ap-northeast-2"
GROUP = f"/vuln-mlops/{CLUSTER}/falco"


def documents(account_id: str) -> tuple[dict, dict]:
    if len(account_id) != 12 or not account_id.isdecimal():
        raise ValueError("account_id must be a 12-digit AWS account ID")
    cluster_arn = f"arn:aws:eks:{REGION}:{account_id}:cluster/{CLUSTER}"
    stream_arn = f"arn:aws:logs:{REGION}:{account_id}:log-group:{GROUP}:log-stream:falco-*"
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "pods.eks.amazonaws.com"},
            "Action": ["sts:AssumeRole", "sts:TagSession"],
            "Condition": {"StringEquals": {
                "aws:RequestTag/eks-cluster-arn": cluster_arn,
                "aws:RequestTag/kubernetes-namespace": "falco-observe",
                "aws:RequestTag/kubernetes-service-account": "falco-cloudwatch",
            }},
        }],
    }
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": stream_arn,
        }],
    }
    return trust, policy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account_id")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    trust, policy = documents(args.account_id)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, value in (("trust.json", trust), ("policy.json", policy)):
        (args.output_dir / filename).write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
