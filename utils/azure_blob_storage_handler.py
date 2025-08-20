from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, ContentSettings
from utils.config import CONTAINER_NAME, AZURE_STORAGE_CONNECTION_STRING
from datetime import datetime
import os

connect_str = AZURE_STORAGE_CONNECTION_STRING
container_name = CONTAINER_NAME

blob_service_client = BlobServiceClient.from_connection_string(connect_str)
container_client = blob_service_client.get_container_client(container_name)

def upload_pdf_to_blob(file_path, blob_name):
    """
    Upload PDF to Azure Blob Storage with proper headers for inline display
    """
    with open(file_path, "rb") as data:
        blob_client = container_client.get_blob_client(blob_name)
        
        # Set content settings for PDF inline display
        content_settings = ContentSettings(
            content_type="application/pdf",
            content_disposition="inline"  # This makes PDFs display in browser instead of downloading
        )
        
        blob_client.upload_blob(
            data, 
            overwrite=True,
            content_settings=content_settings
        )
        
        # Generate the public URL
        url = blob_client.url
        
    return url

def update_existing_pdf_headers():
    """
    Utility function to update existing PDFs in blob storage with correct headers
    Call this once to fix existing PDFs
    """
    try:
        blobs = container_client.list_blobs()
        updated_count = 0
        
        for blob in blobs:
            if blob.name.endswith('.pdf'):
                blob_client = container_client.get_blob_client(blob.name)
                
                # Get existing blob properties
                properties = blob_client.get_blob_properties()
                
                # Update content settings
                content_settings = ContentSettings(
                    content_type="application/pdf",
                    content_disposition="inline"
                )
                
                # Set the blob HTTP headers
                blob_client.set_http_headers(content_settings=content_settings)
                updated_count += 1
                print(f"✅ Updated headers for: {blob.name}")
        
        print(f"🎉 Updated {updated_count} PDF files with inline display headers")
        return updated_count
        
    except Exception as e:
        print(f"❌ Error updating PDF headers: {e}")
        return 0

if __name__ == "__main__":
    # Example usage - update existing PDFs
    print("🔧 Updating existing PDF headers for inline display...")
    count = update_existing_pdf_headers()
    print(f"✅ Process complete. Updated {count} files.")