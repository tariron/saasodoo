#!/bin/bash

# Script to get Kubernetes Dashboard admin access token

set -e

echo "=================================================="
echo "Kubernetes Dashboard - Admin Access Token"
echo "=================================================="
echo ""

# Check if admin-user-token secret exists (persistent token)
if kubectl get secret admin-user-token -n kubernetes-dashboard &>/dev/null; then
    echo "Using persistent token from Secret..."
    echo ""
    TOKEN=$(kubectl get secret admin-user-token -n kubernetes-dashboard -o jsonpath='{.data.token}' | base64 -d)
else
    # Fall back to creating a token
    if ! kubectl get serviceaccount admin-user -n kubernetes-dashboard &>/dev/null; then
        echo "Error: admin-user ServiceAccount not found"
        echo ""
        echo "Please apply the admin user first:"
        echo "  kubectl apply -f 01-serviceaccount.yaml"
        echo "  kubectl apply -f 02-clusterrolebinding.yaml"
        echo "  kubectl apply -f 04-admin-token-secret.yaml"
        exit 1
    fi

    echo "Creating persistent token Secret..."
    kubectl apply -f 04-admin-token-secret.yaml
    sleep 2
    TOKEN=$(kubectl get secret admin-user-token -n kubernetes-dashboard -o jsonpath='{.data.token}' | base64 -d)
fi

echo "Access Token:"
echo ""
echo "$TOKEN"
echo ""
echo "=================================================="
echo "Dashboard URL: https://dashboard.62.171.153.219.nip.io"
echo "=================================================="
echo ""
echo "Copy the token above and paste it when logging into the dashboard."
echo ""
