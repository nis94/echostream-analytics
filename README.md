# EchoStream Analytics v3.0

![Version](https://img.shields.io/badge/version-3.0-blue)
![AWS](https://img.shields.io/badge/AWS-Serverless-orange)
![Python](https://img.shields.io/badge/Python-3.11-blueviolet)
![IaC](https://img.shields.io/badge/IaC-AWS_SAM-yellow)

EchoStream Analytics is a proactive, indispensable intelligence assistant. This fully serverless platform ingests live social media data from Reddit, performs AI-powered sentiment analysis, generates generative AI summaries with Amazon Bedrock, and delivers automated insights and alerts. The system is designed with a secure, multi-tenant architecture and is deployed and managed via a fully automated CI/CD pipeline, all while adhering to a strict sub-$25/month operational budget.

## Key Features

* **Live Data Ingestion**: An automated Lambda producer polls live comments from Reddit for multiple, tenant-configurable topics.
* **Scalable Pipeline**: Uses **Amazon SQS** as a durable, asynchronous buffer to decouple data ingestion from processing.
* **AI-Powered Enrichment**:
    * Performs real-time sentiment analysis on every comment using **AWS Comprehend**.
    * Includes a self-hosted **NLTK** model (via Lambda Layer) as a cost-control alternative.
* **Generative AI Summaries**: A scheduled Lambda uses **Amazon Bedrock** (Anthropic Claude 3 Sonnet) to generate daily, human-readable summaries of key themes and overall sentiment for each tenant.
* **Proactive Spike Alerts**: A scheduled Lambda monitors for sudden negative sentiment shifts and sends email alerts via **Amazon SES**.
* **True Multi-Tenancy**: A full user management and security model using **Amazon Cognito**. Features include self-service user sign-up, automated tenant creation, and secure, token-based data isolation.
* **Full Automation (IaC & CI/CD)**: The entire infrastructure is defined as code (**AWS SAM**) and deployed via a **GitHub Actions** pipeline, which includes automated frontend configuration and upload.

## Architecture Diagram

```mermaid
graph TD
    subgraph "Automation & External"
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
        I -- Sends Digest via --> M[Amazon SES];

        subgraph "Self-Service User Management"
            R[Amazon Cognito] -- on sign-up --> T[PostConfirmation Lambda];
            T -- Creates Tenant --> K;
            T -- Updates User Attribute --> R;
        end
        
        subgraph "User-Facing Application"
            N[User] --> O[CloudFront];
            O -- Loads --> P[S3 Frontend Bucket];
            P -- Calls --> Q{API Gateway};
            Q -- Authenticates with --> R;
            Q -- Triggers --> S[Query/Summary/Watchlist Lambdas];
            S -- Reads/Writes --> H;
            S -- Reads/Writes --> K;
        end
    end