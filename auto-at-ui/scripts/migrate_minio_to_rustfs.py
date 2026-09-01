"""Read-only-by-default legacy MinIO to RustFS migration utility.

This is an operator tool. It never deletes legacy objects and copy mode requires
an explicit confirmation string after a dry-run inventory has been reviewed.
"""

import argparse
import hashlib

import boto3
from botocore.config import Config


def inventory(client, bucket: str) -> list[dict[str, object]]:
    paginator = client.get_paginator("list_objects_v2")
    return [item for page in paginator.paginate(Bucket=bucket) for item in page.get("Contents", [])]


def migrate(source, destination, source_bucket: str, destination_bucket: str) -> dict[str, int]:
    copied = bytes_copied = 0
    for item in inventory(source, source_bucket):
        key, expected_size = item["Key"], item["Size"]
        body = source.get_object(Bucket=source_bucket, Key=key)["Body"].read()
        checksum = hashlib.sha256(body).hexdigest()
        destination.put_object(
            Bucket=destination_bucket, Key=key, Body=body, Metadata={"sha256": checksum}
        )
        head = destination.head_object(Bucket=destination_bucket, Key=key)
        if (
            head.get("ContentLength") != expected_size
            or head.get("Metadata", {}).get("sha256") != checksum
        ):
            raise RuntimeError("reconciliation failed")
        copied += 1
        bytes_copied += len(body)
    return {"objects": copied, "bytes": bytes_copied}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-endpoint", required=True)
    parser.add_argument("--source-bucket", required=True)
    parser.add_argument("--destination-endpoint", required=True)
    parser.add_argument("--destination-bucket", required=True)
    parser.add_argument("--access-key", required=True)
    parser.add_argument("--secret-key", required=True)
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--confirm-copy", default="")
    args = parser.parse_args()
    client_args = {
        "aws_access_key_id": args.access_key,
        "aws_secret_access_key": args.secret_key,
        "config": Config(s3={"addressing_style": "path"}),
    }
    source = boto3.client("s3", endpoint_url=args.source_endpoint, **client_args)
    destination = boto3.client("s3", endpoint_url=args.destination_endpoint, **client_args)
    items = inventory(source, args.source_bucket)
    print(
        {
            "dry_run": not args.copy,
            "objects": len(items),
            "bytes": sum(item["Size"] for item in items),
        }
    )
    if args.copy:
        if args.confirm_copy != "COPY_LEGACY_MINIO":
            raise SystemExit("copy requires --confirm-copy COPY_LEGACY_MINIO")
        print(migrate(source, destination, args.source_bucket, args.destination_bucket))


if __name__ == "__main__":
    main()
