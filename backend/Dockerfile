FROM python:3.11-slim

WORKDIR /app

# Install dependencies for all Lambda functions
COPY risk_map/requirements.txt risk_map/requirements.txt
COPY subscriptions/requirements.txt subscriptions/requirements.txt
COPY notifications/requirements.txt notifications/requirements.txt

RUN pip install --no-cache-dir \
    -r risk_map/requirements.txt \
    -r subscriptions/requirements.txt \
    -r notifications/requirements.txt \
    flask==3.0.2 \
    aws-lambda-powertools==2.34.2

COPY . .

EXPOSE 8000

# Local dev server wrapping the Lambda handlers as a Flask app
CMD ["python", "local_server.py"]
