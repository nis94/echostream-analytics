# EchoStream Analytics v2.0

![Version](https://img.shields.io/badge/version-2.0-blue)
![AWS](https://img.shields.io/badge/AWS-Serverless-orange)
![Python](https://img.shields.io/badge/Python-3.11-blueviolet)

[cite_start]EchoStream Analytics is a complete, cloud-native, and serverless platform for ingesting, processing, and analyzing text-based data in near real-time. [cite: 1] [cite_start]This project ingests live data from social media (Reddit), performs AI-powered sentiment analysis and generative AI summarization, and displays the results on a secure, multi-tenant web dashboard. [cite: 2]

[cite_start]The entire architecture is designed to be "Serverless-First, Cost-Obsessed," operating comfortably under a **$25/month budget** by aggressively leveraging AWS Free Tiers and pay-per-use services. [cite: 3, 4]

## Key Features (v2.0)

* **Live Data Ingestion**: A producer Lambda automatically polls live data from Reddit for multiple tenants and topics.
* **High-Throughput Pipeline**: Uses **Amazon SQS** as a durable, scalable buffer to decouple ingestion from processing.
* **AI-Powered Enrichment**:
    * Performs real-time sentiment analysis on every comment using **AWS Comprehend**.
    * [cite_start]An alternate, self-hosted **NLTK** model is available via a Lambda Layer for cost control. [cite: 8]
* **Generative AI Summaries**: A scheduled Lambda uses **Amazon Bedrock** (Anthropic Claude 3 Sonnet) to generate daily, human-readable summaries of sentiment and key themes for each tenant.
* [cite_start]**Proactive Spike Alerts**: A scheduled Lambda monitors for sudden negative sentiment shifts and sends email alerts via **Amazon SES**. [cite: 143, 144]
* [cite_start]**True Multi-Tenancy**: Features a full user authentication and security model using **Amazon Cognito**, ensuring complete data isolation between tenants. [cite: 69]
* **Dual-Storage Strategy**:
    * [cite_start]**Amazon DynamoDB** for the low-latency, real-time dashboard data. [cite: 40]
    * [cite_start]**Amazon S3 Data Lake** for long-term raw data archival. [cite: 42]
* [cite_start]**Ad-Hoc Analysis**: The S3 data lake is cataloged by **AWS Glue** and is queryable using standard SQL with **Amazon Athena**. [cite: 45]
* [cite_start]**Fully Automated**: The entire infrastructure is defined as code (**AWS SAM**) and deployed via a **CI/CD pipeline in GitHub Actions**. [cite: 11]

## Architecture Diagram (v2.0)

```mermaid
graph TD
    subgraph "External & Automation"
        A[Reddit API]
        B[GitHub Actions CI/CD]
    end

    subgraph "AWS Cloud Infrastructure"
        C[Producer Lambda] -- Scheduled by EventBridge --> C;
        C -- Polls --> A;
        C -- Writes to --> D[SQS Queue];
        
        D -- Triggers --> E[Processor Lambda];
        E -- Uses --> F[AWS Comprehend];
        E -- Writes Raw Data --> G[S3 Data Lake];
        E -- Writes Enriched Data --> H[DynamoDB Data Table];
        
        I[Summarizer Lambda] -- Scheduled by EventBridge --> I;
        I -- Reads from --> H;
        I -- Calls --> J[Amazon Bedrock];
        J -- Returns Summary --> I;
        I -- Writes Summary to --> K[DynamoDB Tenants Table];
        
        L[Alerting Lambda] -- Scheduled by EventBridge --> L;
        L -- Reads from --> H;
        L -- Sends Alert via --> M[Amazon SES];
        
        subgraph "User-Facing Application"
            N[User] --> O[CloudFront];
            O -- Loads --> P[S3 Frontend Bucket];
            P -- Calls --> Q{API Gateway};
            Q -- Authenticates with --> R[Amazon Cognito];
            Q -- Triggers --> S[Query/Summary Lambdas];
            S -- Reads from --> H;
            S -- Reads from --> K;
        end
    end


Of course. Here are the `Setup & Deployment` and `Cleanup` sections formatted in Markdown for your `README.md` file.

-----

## Setup & Deployment

This guide will walk you through deploying the EchoStream Analytics v2.0 platform from scratch.

### Prerequisites

Before you begin, ensure you have the following:

  * An AWS Account with billing configured.
  * [AWS CLI](https://aws.amazon.com/cli/) installed and configured on your local machine.
  * [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) installed.
  * [Git](https://git-scm.com/downloads) installed.
  * A Reddit account with a "script" type application created to get API credentials.

### Installation & Deployment Steps

1.  **Clone the Repository**

    ```bash
    git clone <your-repository-url>
    cd echostream-analytics
    ```

2.  **Configure Local Credentials**
    Create a file named `.env` in the root of the project. This file will hold your Reddit API credentials and is ignored by Git.

    Paste the following into the `.env` file and replace the placeholder values:

    ```
    # Local environment variables for setup script
    export REDDIT_CLIENT_ID="YOUR_CLIENT_ID"
    export REDDIT_CLIENT_SECRET="YOUR_CLIENT_SECRET"
    export REDDIT_USER_AGENT="EchoStreamClient/1.0 by your_username"
    export REDDIT_USERNAME="your_reddit_username"
    export REDDIT_PASSWORD="your_reddit_password"
    ```

3.  **Deploy the Infrastructure**
    This project uses a CI/CD pipeline with GitHub Actions for automated deployments.

      * Create a new GitHub repository and push this project's code to it.
      * In your GitHub repository's settings, go to **Secrets and variables \> Actions** and create two repository secrets:
          * `AWS_ACCESS_KEY_ID`: Your IAM user's access key.
          * `AWS_SECRET_ACCESS_KEY`: Your IAM user's secret key.
      * Pushing a commit to the `main` branch will automatically trigger the GitHub Actions workflow, which will deploy the entire AWS stack using the `template.yaml` file.

4.  **Run Post-Deployment Setup**
    After the CloudFormation stack has been successfully deployed, you need to run the setup script to configure the application.

    First, make the script executable:

    ```bash
    chmod +x setup_stack.sh
    ```

    Then, run the script:

    ```bash
    ./setup_stack.sh
    ```

    This script will automatically:

      * Fetch the necessary outputs from your new CloudFormation stack.
      * Update the AWS Secret with your Reddit credentials from the `.env` file.
      * Create the 5 tenant configurations in the `TenantsTable`.
      * Create the `RickSanchez` test user in Cognito.
      * Trigger the producer Lambda to begin ingesting data.

5.  **Access the Frontend**

      * Navigate to the **CloudFormation** console in your AWS account.
      * Select the `echostream-prod` stack and go to the **Outputs** tab.
      * The URL for your live dashboard will be the value for the `HttpApiUrl` output. *Correction: The CloudFront URL is the one for the frontend. I should add this output to the template.* A better way is to get it from the CloudFront console.
      * Navigate to the **CloudFront** console. Find your new distribution and copy its **Domain name** (e.g., `d123456abcdef.cloudfront.net`). Paste this URL into your browser to access the login page.

-----

## Cleanup

To avoid ongoing costs, you can completely remove all AWS resources created by this project by running the automated cleanup script. This script will empty the S3 buckets and then delete the entire CloudFormation stack.

From the root of the project directory, run:

```bash
./cleanup_stack.sh
```