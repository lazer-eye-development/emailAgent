"""
Email Retriever - Gets emails from Gmail and uploads to S3
"""

import os
import base64
import logging
import boto3
import json
from datetime import datetime
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("email_retriever.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


class EmailRetriever:
    """Handles retrieving emails from Gmail and storing in S3"""
    
    def __init__(self):
        # Get bucket from env or use default as fallback
        self.s3_bucket = os.environ.get('S3_BUCKET_NAME')
        
        if not self.s3_bucket:
            logger.error("No S3 bucket specified in environment variables!")
            raise ValueError("S3_BUCKET_NAME environment variable not set")
            
        # Init the S3 client
        try:
            self.s3_client = boto3.client('s3')
            logger.info(f"Using S3 bucket: {self.s3_bucket}")
        except Exception as e:
            logger.error(f"Couldn't initialize S3: {e}")
            raise
    
    def upload_to_s3(self, content, object_name):
        """Upload email content to S3
        
        Args:
            content: Text content to upload
            object_name: S3 object key name
        """
        try:
            # Direct upload to S3 without temp files
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=object_name,
                Body=content.encode('utf-8')
            )
            logger.info(f"Uploaded to {object_name}")
            return True
        except Exception as e:
            # Log the error but don't crash
            logger.error(f"S3 upload failed: {e}")
            return False
    
    def _get_gmail_service(self):
        """Get authenticated Gmail service
        
        Returns the Gmail API service or raises exception if auth fails
        """
        creds = None
        
        # Try to load existing token
        if os.path.exists('token.json'):
            try:
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            except Exception as e:
                logger.warning(f"Couldn't load token.json: {e}")
        
        # If token doesn't exist or is invalid
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    # Try to refresh token
                    creds.refresh(Request())
                except:
                    # If refresh fails, we'll need to authenticate again
                    logger.warning("Token refresh failed, need to re-authenticate")
                    creds = None
            
            # Fresh authentication needed
            if not creds:
                if not os.path.exists('credentials.json'):
                    logger.error("Missing credentials.json - can't authenticate!")
                    raise FileNotFoundError("credentials.json file not found")
                    
                # Run the OAuth flow
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                    logger.info("Authentication successful")
                except Exception as e:
                    logger.error(f"OAuth flow failed: {e}")
                    raise
            
            # Save creds for next time
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                logger.info("Saved new token.json")
        
        # Build and return the Gmail service
        try:
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            logger.error(f"Failed to build Gmail service: {e}")
            raise
    
    def _extract_email_parts(self, msg):
        """Extract and parse email parts from Gmail API response
        
        Handles different formats Gmail might return
        """
        # First get the headers
        headers = msg.get('payload', {}).get('headers', [])
        
        # Default values in case we can't find headers
        subject = "No Subject"
        sender = "Unknown Sender"
        date_received = "Unknown Date"
        
        # Extract header values
        for header in headers:
            name = header['name'].lower()
            if name == 'subject':
                subject = header['value']
            elif name == 'from':
                sender = header['value']
            elif name == 'date':
                date_received = header['value']
        
        # Now extract the body - this is tricky as emails can be complex
        body = ""
        
        # Extract based on message structure
        if 'parts' in msg['payload']:
            # Multipart email - find the text parts
            for part in msg['payload']['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                    decoded = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    body += decoded
        elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
            # Simple email with just one part
            body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')
        else:
            # Not sure what format this is - log it
            logger.warning(f"Couldn't extract body from email with structure: {msg['payload'].keys()}")
        
        # Create email object
        return {
            "subject": subject,
            "sender": sender,
            "dateReceived": date_received,
            "body": body,
        }
    
    def process_emails(self):
        """Main method to fetch and process emails"""
        try:
            service = self._get_gmail_service()
            
            # Query for unread emails in primary category
            # TODO: Maybe expand this to include other categories?
            results = service.users().messages().list(
                userId='me', 
                q='category:primary is:unread'
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                logger.info('No new emails to process')
                return
            
            logger.info(f"Found {len(messages)} emails to process")
            
            for message in messages:
                msg_id = message['id']
                
                # Get the full message
                full_msg = service.users().messages().get(
                    userId='me', 
                    id=msg_id, 
                    format='full'
                ).execute()
                
                # Extract email content
                try:
                    email_data = self._extract_email_parts(full_msg)
                    email_data['messageId'] = msg_id
                    email_data['processed'] = datetime.now().isoformat()
                    
                    # Create unique filename with timestamp
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    object_name = f"emails/{msg_id}_{timestamp}.json"
                    
                    # Upload as JSON
                    success = self.upload_to_s3(
                        json.dumps(email_data, indent=2), 
                        object_name
                    )
                    
                    if success:
                        # Only mark as read if we processed it successfully
                        service.users().messages().modify(
                            userId='me', 
                            id=msg_id, 
                            body={'removeLabelIds': ['UNREAD']}
                        ).execute()
                        logger.info(f"Processed and marked as read: {msg_id}")
                    else:
                        logger.warning(f"Upload failed for {msg_id}, not marking as read")
                        
                except Exception as e:
                    logger.error(f"Error processing message {msg_id}: {e}")
                    # Continue with next message
                    continue
                
        except Exception as e:
            logger.error(f"Error in process_emails: {e}")
            raise


# Just a simple function to run the process
def main():
    """Run the email processing"""
    # For simpler stacktraces during development:
    # import pdb; pdb.set_trace()
    try:
        retriever = EmailRetriever()
        retriever.process_emails()
        logger.info("Email retrieval completed successfully")
    except Exception as e:
        logger.critical(f"Email retrieval failed: {e}")
        return 1
    return 0


if __name__ == '__main__':
    exit(main())
