# Notification Service

This service handles the delivery of dengue risk alerts. It is a robust, serverless, and event-driven pipeline designed to process machine learning predictions, match them against user subscriptions, and dispatch targeted emails without hitting API rate limits or losing data.

## Architecture Overview

The system uses an SQS-buffered architecture to decouple the fast process of identifying affected users from the slower, rate-limited process of sending emails.

1. **Amazon S3:** Receives the `predictions.json` file from the SageMaker Batch Transform job.
2. **Dispatcher Lambda (Producer):** Triggered by S3. Identifies high-risk areas, queries the subscriber database, and pushes users to SQS in batches of 10.
3. **Amazon SQS (Buffer):** A Standard Queue that holds the email requests, ensuring fault tolerance and preventing downstream throttling.
4. **Worker Lambda (Consumer):** Triggered by SQS. Picks up batches of 10, dispatches emails via SES, and reports partial batch failures to prevent duplicate alerting.
5. **Amazon SES:** Dispatches the final HTML email alerts to users.

## 📂 Folder Structure

```text
notification/
├── dispatcher/
│   ├── main.py                # S3 -> SQS logic
│   └── requirements.txt
├── worker/
│   ├── main.py                # SQS -> SES logic
│   ├── templates.py           # HTML email templates
│   └── requirements.txt
└── README.md
```

## 🛠️ Setup & Deployment

Follow these steps to set up your local environment and deploy the Notification Service to AWS.

### 1. Install AWS CLI

For the most up-to-date installation instructions, refer to the official AWS documentation:

👉 **[Installing or updating to the latest version of the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)**

Verify installation by running: `aws --version`

### 2. AWS SSO Authentication

We use AWS IAM Identity Center (SSO) for secure access.

1.  **Initialize the login:**
    ```bash
    aws configure sso
    ```
2.  **Enter the following when prompted:**
    - **SSO session name:** `local-dev` (or any name)
    - **SSO start URL:** `https://d-9667a7613f.awsapps.com/start`
    - **SSO region:** `ap-southeast-1`
    - **Registration Scopes:** (Leave as default/Enter)
3.  **Browser Login:** Your browser will open. Sign in with your credentials and click **Allow**.
4.  **Terminal Setup:** Return to the terminal. Select the AWS Account and the **Role** assigned to you.
5.  **Final Config:**
    - **CLI default client region:** (Leave as default/Enter)
    - **CLI default output format:** (Leave as default/Enter)
    - **CLI profile name:** `default` (or your preferred name)

> **Note:** If your session expires in the future, just run `aws sso login`.

### 3. Deploying to AWS

The deployment is handled by a custom bash script.

**Run the deployment:**

```bash
cd notification
./deploy.sh
```
