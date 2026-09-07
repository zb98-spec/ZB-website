#!/usr/bin/env bash
# One-time setup for GitHub Actions -> Cloud Run deployment.
# Run this once, locally, after `gcloud auth login` and `gcloud config set project <PROJECT_ID>`.
#
# Usage:
#   PROJECT_ID=my-project REGION=us-central1 GITHUB_REPO=my-user/my-repo \
#     ./scripts/setup_gcp_ci.sh
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your GCP project id}"
: "${REGION:=us-central1}"
: "${GITHUB_REPO:?Set GITHUB_REPO to owner/repo, e.g. zb98-spec/ZB-website}"

SERVICE_ACCOUNT="zb-hub-deployer"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
POOL="github-pool"
PROVIDER="github-provider"
REPOSITORY="zb-hub"

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

echo ""
echo "Done. Add these as GitHub Actions repository secrets:"
echo "  GCP_PROJECT_ID     = ${PROJECT_ID}"
echo "  GCP_REGION         = ${REGION}"
echo "  GCP_SA_EMAIL       = ${SA_EMAIL}"
echo "  GCP_WIF_PROVIDER   = ${POOL_ID}/providers/${PROVIDER}"
echo ""
echo "You'll also need these Secret Manager secrets (create with"
echo "  echo -n VALUE | gcloud secrets create NAME --data-file=-):"
echo "  secret-key, database-url, google-client-id, google-client-secret,"
echo "  apple-client-id, apple-team-id, apple-key-id, apple-private-key"
echo ""
echo "And these as GitHub Actions repository secrets (used to run migrations"
echo "against Neon directly from the workflow):"
echo "  SECRET_KEY, DATABASE_URL"
