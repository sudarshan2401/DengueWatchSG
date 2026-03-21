#!/bin/bash
set -e

# Clean up old builds
rm -rf build
mkdir -p build/ingestion

# ==========================================
# Install Dependencies for AWS Linux
# ==========================================
echo "📦 Installing dependencies from requirements.txt..."
pip install \
    --platform manylinux2014_x86_64 \
    --target=build/ingestion \
    --implementation cp \
    --python-version 3.14 \
    --only-binary=:all: \
    --upgrade \
    psycopg2-binary==2.9.11 > /dev/null

# ==========================================
# Package and Deploy Ingestion Lambda
# ==========================================
echo "📦 Packaging Ingestion Lambda..."
cp ingestion/lambda_function.py build/ingestion/

cd build/ingestion
python -c "import shutil; shutil.make_archive('../ingestion', 'zip', '.')"
cd ../../

echo "🚀 Deploying RiskMapIngestionFunction to AWS..."
aws lambda update-function-code \
    --function-name RiskMapIngestionFunction \
    --zip-file fileb://build/ingestion.zip \
    --region ap-southeast-1 > /dev/null
echo "✅ Deployment Complete!"

# ==========================================
# Clean Up
# ==========================================
echo "🧹 Cleaning up temporary build files..."
rm -rf build/ingestion
echo "✅ Done"