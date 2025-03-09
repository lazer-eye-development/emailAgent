"""
Email Classifier - Classifies emails using AWS Bedrock and Claude

This module retrieves email content from S3 and uses Claude via AWS Bedrock
to classify each email into predefined categories for appropriate handling.
"""

import boto3
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("classifier.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EmailClassifier:
    """Classifies emails using AWS Bedrock and Claude."""
    
    def __init__(self):
        """Initialize the EmailClassifier with required clients and configuration."""
        # Validate environment variables
        required_vars = ["BWB_PROFILE_NAME", "BWB_REGION_NAME", "BWB_ENDPOINT_URL", "S3_BUCKET_NAME"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        self.s3_bucket = os.environ.get("S3_BUCKET_NAME")
        self.bedrock_model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-v2:1")
        
        try:
            # Initialize S3 client
            self.s3_client = boto3.client('s3')
            
            # Initialize Bedrock client
            session = boto3.Session(
                profile_name=os.environ.get("BWB_PROFILE_NAME")
            )
            self.bedrock_client = session.client(
                service_name='bedrock-runtime',
                region_name=os.environ.get("BWB_REGION_NAME"),
                endpoint_url=os.environ.get("BWB_ENDPOINT_URL")
            )
            
            logger.info(f"Initialized EmailClassifier with bucket: {self.s3_bucket}, model: {self.bedrock_model_id}")
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            raise
    
    def list_email_files(self, prefix="emails/"):
        """List email files in the S3 bucket.
        
        Args:
            prefix (str): The prefix to filter objects by
            
        Returns:
            list: List of object keys matching the prefix
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix=prefix
            )
            
            if 'Contents' in response:
                return [item["Key"] for item in response["Contents"]]
            
            return []
        except Exception as e:
            logger.error(f"Error listing files from S3 bucket: {e}")
            return []
    
    def read_email_file(self, file_key):
        """Read content of a file from S3 bucket.
        
        Args:
            file_key (str): The S3 object key
            
        Returns:
            dict: Parsed email content or None if error
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.s3_bucket, 
                Key=file_key
            )
            
            content = response['Body'].read().decode('utf-8')
            
            try:
                # Parse as JSON
                return json.loads(content)
            except json.JSONDecodeError:
                # Handle plain text content (for backward compatibility)
                lines = content.split("\n")
                email_data = {}
                
                # Try to parse plain text format
                for line in lines[:3]:
                    if line.startswith("Subject: "):
                        email_data["subject"] = line.replace("Subject: ", "")
                    elif line.startswith("Sender: "):
                        email_data["sender"] = line.replace("Sender: ", "")
                    elif line.startswith("Date Received: "):
                        email_data["dateReceived"] = line.replace("Date Received: ", "")
                
                # Everything else is the body
                email_data["body"] = "\n".join(lines[3:]).strip()
                
                return email_data
        except Exception as e:
            logger.error(f"Error reading file from S3 bucket: {e}")
            return None
    
    def save_classification_result(self, email_key, email_data, classification):
        """Save classification result to S3.
        
        Args:
            email_key (str): Original email S3 key
            email_data (dict): Email content data
            classification (str): Classification result
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create result object
            result = {
                "originalEmail": email_key,
                "emailData": email_data,
                "classification": classification,
                "classifiedAt": datetime.now().isoformat()
            }
            
            # Generate results key
            filename = os.path.basename(email_key)
            results_key = f"results/{filename}"
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=results_key,
                Body=json.dumps(result, indent=2).encode('utf-8')
            )
            
            logger.info(f"Saved classification result to {self.s3_bucket}/{results_key}")
            return True
        except Exception as e:
            logger.error(f"Error saving classification result: {e}")
            return False
    
    def classify_email(self, email_data):
        """Classify the email using Claude model via AWS Bedrock.
        
        Args:
            email_data (dict): Email content data
            
        Returns:
            str: Classification result or None if error
        """
        # Construct email content from data
        if isinstance(email_data, dict):
            subject = email_data.get("subject", "No Subject")
            sender = email_data.get("sender", "Unknown Sender")
            body = email_data.get("body", "")
            
            email_content = f"Subject: {subject}\nFrom: {sender}\n\n{body}"
        else:
            email_content = str(email_data)
        
        # Create prompt for classification
        prompt = f"""
Human: I need you to classify the following email into one of these categories:
1. STANDARD_FAQ: Answerable by standard FAQ, no complex information needed
2. REQUIRES_RAG: Requires response by LLM using RAG for more complex questions
3. CRM_ADDITION: Sender needs to be added to CRM, appears to be a new contact or lead
4. NEEDS_INFO: More information needed from sender before we can properly respond

Please respond with ONLY the category name (e.g., "STANDARD_FAQ"). Here's the email:

{email_content}
