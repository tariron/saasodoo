#!/bin/bash

# Script to get Kubernetes Dashboard admin access token

set -e

echo "=================================================="
echo "Kubernetes Dashboard - Admin Access Token"
echo "=================================================="
echo ""

# Check if admin-user exists
if ! kubectl get serviceaccount admin-user -n kubernetes-dashboard &>/dev/null; then
    echo "❌ Error: admin-user ServiceAccount not found"
    echo ""
    echo "Please apply the admin user first:"
    echo "  kubectl apply -f 01-serviceaccount.yaml"
    echo "  kubectl apply -f 02-clusterrolebinding.yaml"
    exit 1
fi

# Generate token
echo "Generating access token..."
echo ""

TOKEN=$(kubectl -n kubernetes-dashboard create token admin-user --duration=87600h)

echo "✅ Access Token:"
echo ""
echo "$TOKEN"
echo ""
echo "=================================================="
echo "Dashboard URL: http://dashboard.62.171.153.219.nip.io"
echo "=================================================="
echo ""
echo "Copy the token above and paste it when logging into the dashboard."
echo ""
