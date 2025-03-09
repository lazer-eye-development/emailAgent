### Email Classification and Processing System

![emailAgent-github](https://github.com/user-attachments/assets/ac3f20a3-594c-4237-94ce-825429fa5159)

An intelligent system that processes incoming emails, extracts their content, and uses AWS Bedrock with Claude to classify them based on their content and required action.

### Architecture Overview
This system consists of three main components:

### 1. Email Retriever
Connects to Gmail using OAuth, identifies unread messages, extracts their content, and uploads them to an AWS S3 bucket.

### 2. Email Classifier
Retrieves email content from S3 and uses Claude via AWS Bedrock to classify each email into one of four categories:

STANDARD_FAQ: Answerable by standard FAQ
REQUIRES_RAG: Requires response using RAG for complex questions
CRM_ADDITION: Sender needs to be added to CRM
NEEDS_INFO: More information needed from sender

### 3. Storage Layer
AWS S3 serves as the storage layer between components, enabling a decoupled architecture.

### System Flow

Gmail API -> Email Retriever -> S3 -> Email Classifier -> Classification Results

### Key Technologies

AWS Bedrock: Used to access Claude LLM for natural language classification
AWS S3: Object storage for email content between processing steps
Google Gmail API: For accessing and processing emails
Python: Primary implementation language

### Setup Instructions
### Prerequisites

AWS Account with Bedrock access
Google Cloud Project with Gmail API enabled
Python 3.8+

### Environment Setup

Clone this repository
Install dependencies:

pip install -r requirements.txt

Copy .env.example to .env and fill in your configuration values
Set up Google OAuth credentials:

Create a project in Google Cloud Console
Enable the Gmail API
Create OAuth client ID credentials
Download the credentials JSON file and save as credentials.json
Run the application once to complete the OAuth flow and generate token.json



### Running the Application
### Email Retrieval
python email_retriever.py

### Email Classification
python classifier.py

### Security Considerations

Credentials: All API keys and secrets are loaded from environment variables or secure storage.
Token Handling: OAuth refresh tokens are stored securely and never committed to the repository.
Access Control: Minimal IAM permissions are used for AWS resources.

### Future Improvements

Add response generation based on classification
Implement automated routing of emails based on classification
Add a dashboard for monitoring system performance
Expand classification categories based on business needs





