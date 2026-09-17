#!/usr/bin/env sh
set -eu

compose_file=infra/docker-compose.yml
services='db mailpit storage api web'
s3_region=${S3_REGION:-us-east-1}

storage_container=$(docker compose -f "$compose_file" ps -q storage)
if [ -z "$storage_container" ]; then
  echo 'missing container for storage' >&2
  exit 1
fi

storage_env() {
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$storage_container" |
    sed -n "s/^$1=//p" |
    sed -n '1p'
}

storage_access_key=$(storage_env AWS_ACCESS_KEY_ID)
storage_secret_key=$(storage_env AWS_SECRET_ACCESS_KEY)
storage_bucket=$(storage_env S3_BUCKET)
storage_address=$(docker compose -f "$compose_file" port storage 8333)

if [ -z "$storage_access_key" ] || [ -z "$storage_secret_key" ] || [ -z "$storage_bucket" ] || [ -z "$storage_address" ]; then
  echo 'storage container is missing an effective S3 credential, bucket, or published endpoint' >&2
  exit 1
fi

if [ -n "${S3_ACCESS_KEY+x}" ] || [ -n "${S3_SECRET_KEY+x}" ]; then
  if [ -z "${S3_ACCESS_KEY:-}" ] || [ -z "${S3_SECRET_KEY:-}" ]; then
    echo 'S3_ACCESS_KEY and S3_SECRET_KEY overrides must be supplied together' >&2
    exit 1
  fi
  s3_access_key=$S3_ACCESS_KEY
  s3_secret_key=$S3_SECRET_KEY
else
  s3_access_key=$storage_access_key
  s3_secret_key=$storage_secret_key
fi

s3_bucket=${S3_BUCKET:-$storage_bucket}
s3_endpoint=${S3_ENDPOINT_URL:-http://$storage_address}

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/easydentist-compose-health.XXXXXX")
canary_key=".compose-health-canary-$$"
canary_url="$s3_endpoint/$s3_bucket/$canary_key"
canary_created=false

cleanup() {
  if [ "$canary_created" = true ]; then
    signed_curl --request DELETE "$canary_url" --output /dev/null >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp_dir"
}

signed_curl() {
  curl --fail --silent --show-error \
    --aws-sigv4 "aws:amz:${s3_region}:s3" \
    --user "${s3_access_key}:${s3_secret_key}" \
    "$@"
}

signed_status_curl() {
  curl --silent --show-error \
    --aws-sigv4 "aws:amz:${s3_region}:s3" \
    --user "${s3_access_key}:${s3_secret_key}" \
    "$@"
}

trap cleanup EXIT HUP INT TERM

expect_health_json() {
  endpoint_name=$1
  endpoint_url=$2
  expected_json=$3
  response_body="$tmp_dir/${endpoint_name}.json"
  response_headers="$tmp_dir/${endpoint_name}.headers"
  response_status=$(curl --silent --show-error --output "$response_body" \
    --dump-header "$response_headers" --write-out '%{http_code}' \
    --header 'Accept: application/json' --max-redirs 0 "$endpoint_url" || true)

  if [ "$response_status" != 200 ] || ! grep -qi '^content-type: application/json' "$response_headers" || ! printf '%s' "$expected_json" | cmp -s - "$response_body"; then
    echo "$endpoint_name endpoint did not return the expected HTTP 200 JSON contract" >&2
    exit 1
  fi
}

for service in $services; do
  container_id=$(docker compose -f "$compose_file" ps -q "$service")
  if [ -z "$container_id" ]; then
    echo "missing container for $service" >&2
    exit 1
  fi

  health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
  if [ "$health" != healthy ]; then
    echo "$service is $health" >&2
    exit 1
  fi

  echo "$service: healthy"
done

expect_health_json 'api' 'http://127.0.0.1:8000/api/v1/health' '{"service":"api","status":"ok"}'
echo 'api endpoint: healthy'

expect_health_json 'web' 'http://127.0.0.1:3000/health' '{"service":"web","status":"ok"}'
echo 'web endpoint: healthy'

expect_health_json 'web-proxy' 'http://127.0.0.1:3000/api/v1/health' '{"service":"api","status":"ok"}'
echo 'web proxy endpoint: healthy'

if ! curl --help all | grep -q -- '--aws-sigv4'; then
  echo 'curl with AWS Signature v4 support is required for the S3 verification' >&2
  exit 1
fi

# A ready S3 gateway rejects an unsigned ListBuckets request with the canonical
# S3 error. This is intentionally stricter than merely accepting any failure.
unauthenticated_status=$(curl --silent --output "$tmp_dir/unauthenticated.xml" \
  --write-out '%{http_code}' "$s3_endpoint/" || true)
if [ "$unauthenticated_status" != 403 ] || ! grep -q '<Code>AccessDenied</Code>' "$tmp_dir/unauthenticated.xml"; then
  echo 'S3 endpoint did not return the expected unauthenticated AccessDenied response' >&2
  exit 1
fi
echo 's3 endpoint: ready'

# PUT Bucket is idempotent for the local owner: SeaweedFS returns 200 for a
# create/reuse, while other S3 implementations can return 409 for an existing
# bucket. The signed object round-trip below proves that the bucket is usable.
bucket_status=$(signed_status_curl --request PUT "$s3_endpoint/$s3_bucket" \
  --output "$tmp_dir/bucket.xml" --write-out '%{http_code}' || true)
case "$bucket_status" in
  200 | 409) ;;
  *)
    echo "could not create or reuse local S3 bucket (HTTP $bucket_status)" >&2
    exit 1
    ;;
esac
echo 's3 bucket: ready'

printf 'EasyDentist Compose S3 canary\n' > "$tmp_dir/canary-upload"
signed_curl --upload-file "$tmp_dir/canary-upload" "$canary_url" --output /dev/null
canary_created=true
signed_curl "$canary_url" --output "$tmp_dir/canary-download"
cmp "$tmp_dir/canary-upload" "$tmp_dir/canary-download"
echo 's3 signed object round-trip: healthy'

anonymous_status=$(curl --silent --output "$tmp_dir/anonymous.xml" \
  --write-out '%{http_code}' "$canary_url" || true)
if [ "$anonymous_status" != 403 ] || ! grep -q '<Code>AccessDenied</Code>' "$tmp_dir/anonymous.xml"; then
  echo 'anonymous access unexpectedly read the local S3 canary object' >&2
  exit 1
fi
echo 's3 anonymous read: denied'

signed_curl --request DELETE "$canary_url" --output /dev/null
canary_created=false
echo 's3 canary cleanup: complete'
