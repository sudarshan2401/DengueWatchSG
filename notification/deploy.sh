#!/bin/bash
set -e

# Clean up old builds
rm -rf build
mkdir -p build/dispatcher build/worker

# ==========================================
# Package and Deploy DISPATCHER Lambda
# ==========================================
echo "📦 Packaging Dispatcher..."
cp dispatcher/lambda_function.py build/dispatcher/
cp -r shared build/dispatcher/

cd build/dispatcher
python -c "import shutil; shutil.make_archive('../dispatcher', 'zip', '.')"
cd ../../

echo "🚀 Deploying Dispatcher to AWS..."
aws lambda update-function-code \
    --function-name NotificationDispatcher \
    --zip-file fileb://build/dispatcher.zip \
    --region ap-southeast-1 > /dev/null
echo "✅ Deployment Complete!"

# ==========================================
# Package and Deploy WORKER Lambda
# ==========================================
echo "📦 Packaging Worker..."
cp worker/lambda_function.py build/worker/
cp worker/templates.py build/worker/
cp -r shared build/worker/

cd build/worker
python -c "import shutil; shutil.make_archive('../worker', 'zip', '.')"
cd ../../

echo "🚀 Deploying Worker to AWS..."
aws lambda update-function-code \
    --function-name NotificationWorker \
    --zip-file fileb://build/worker.zip \
    --region ap-southeast-1 > /dev/null
echo "✅ Deployment Complete!"

# ==========================================
# Clean Up
# ==========================================
echo "🧹 Cleaning up temporary build files..."
rm -rf build/dispatcher build/worker
echo "✅ Done"