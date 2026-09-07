#!/usr/bin/env bash
# One-time setup for GitHub Actions -> Cloud Run deployment.
# Run this once, locally, after `gcloud auth login` and `gcloud config set project <PROJECT_ID>`.
#
# Usage:
#   PROJECT_ID=my-project REGION=us-central1 GITHUB_REPO=my-user/my-repo \
#     ./scripts/setup_gcp_ci.sh
#
# You'll be prompted for your Neon DATABASE_URL if it isn't already set in
# the environment. Everything else is created automatically and is safe to
# re-run (existing resources are skipped or updated, not duplicated).
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your GCP project id}"
: "${REGION:=us-central1}"
: "${GITHUB_REPO:?Set GITHUB_REPO to owner/repo, e.g. zb98-spec/ZB-website}"

SERVICE_ACCOUNT="zb-hub-deployer"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
POOL="github-pool"
PROVIDER="github-provider"
REPOSITORY="zb-hub"

create_or_update_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- --project "$PROJECT_ID" >/dev/null
    echo "    updated existing secret: $name"
  else
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- --project "$PROJECT_ID" >/dev/null
    echo "    created secret: $name"
  fi
}

# deploy.yml's `--set-secrets` references a fixed list of Secret Manager
# secrets (Google/Apple OAuth, email, Gemini) - Cloud Run refuses to deploy
# if ANY of them don't exist, even for features you haven't set up yet. So
# every optional secret gets an empty placeholder up front (an empty value
# keeps that feature disabled, same as if the env var were never set) and
# is left alone on re-runs, so this never overwrites a real value you add
# later with `gcloud secrets versions add <name> --data-file=-`.
create_secret_if_missing() {
  local name="$1"
  if gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "    already exists, leaving as-is: $name"
  else
    printf '' | gcloud secrets create "$name" --data-file=- --project "$PROJECT_ID" >/dev/null
    echo "    created empty placeholder: $name"
  fi
}

echo "==> Enabling required APIs"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  --project "$PROJECT_ID"

echo "==> Creating Artifact Registry repository ($REPOSITORY)"
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION" \
  --project "$PROJECT_ID" \
  || echo "    (already exists, skipping)"

echo "==> Creating deploy service account ($SA_EMAIL)"
gcloud iam service-accounts create "$SERVICE_ACCOUNT" \
  --display-name="ZB Hub CI/CD deployer" \
  --project "$PROJECT_ID" \
  || echo "    (already exists, skipping)"

echo "==> Granting roles to the deploy service account"
for ROLE in roles/run.admin roles/artifactregistry.writer roles/secretmanager.secretAccessor roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" \
    --condition=None \
    --quiet
done

echo "==> Creating Workload Identity Pool + Provider (no long-lived keys)"
gcloud iam workload-identity-pools create "$POOL" \
  --location="global" \
  --display-name="GitHub Actions pool" \
  --project "$PROJECT_ID" \
  || echo "    (already exists, skipping)"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --location="global" \
  --workload-identity-pool="$POOL" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --project "$PROJECT_ID" \
  || echo "    (already exists, skipping)"

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}"

echo "==> Allowing this GitHub repo to impersonate the deploy service account"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_REPO}" \
  --project "$PROJECT_ID"

echo "==> Creating app secrets in Secret Manager"
SECRET_KEY_VALUE="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || openssl rand -hex 32)}"
create_or_update_secret secret-key "$SECRET_KEY_VALUE"

if [ -z "${DATABASE_URL:-}" ]; then
  read -rsp "Neon DATABASE_URL (input hidden, e.g. postgresql://...): " DATABASE_URL
  echo
fi
create_or_update_secret database-url "$DATABASE_URL"

echo "==> Creating empty placeholders for not-yet-configured optional features"
echo "    (Google/Apple OAuth, email for password reset, Gemini chat bot)"
for NAME in google-client-id google-client-secret apple-client-id apple-team-id \
            apple-key-id apple-private-key mail-server mail-username \
            mail-password gemini-api-key; do
  create_secret_if_missing "$NAME"
done
echo "    Fill any of these in later with:"
echo "      printf '%s' 'the-real-value' | gcloud secrets versions add <name> --data-file=-"
echo "    That feature turns on automatically on the next deploy - no code"
echo "    or workflow changes needed."

echo ""
echo "==================================================================="
echo "Done. Add these as GitHub repo secrets"
echo "(Settings -> Secrets and variables -> Actions -> New repository secret):"
echo ""
echo "  GCP_PROJECT_ID   = ${PROJECT_ID}"
echo "  GCP_REGION       = ${REGION}"
echo "  GCP_SA_EMAIL     = ${SA_EMAIL}"
echo "  GCP_WIF_PROVIDER = ${POOL_ID}/providers/${PROVIDER}"
echo "  SECRET_KEY       = ${SECRET_KEY_VALUE}"
echo "  DATABASE_URL     = (the same Neon connection string you just entered)"
echo ""
echo "Once those 6 secrets are in GitHub, every push to main that passes"
echo "tests deploys automatically."
echo "==================================================================="
