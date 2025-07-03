from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from utils.config import CONTAINER_NAME, AZURE_STORAGE_CONNECTION_STRING
from datetime import datetime
import os

connect_str = AZURE_STORAGE_CONNECTION_STRING
container_name = CONTAINER_NAME

blob_service_client = BlobServiceClient.from_connection_string(connect_str)
container_client = blob_service_client.get_container_client(container_name)

def upload_pdf_to_blob(file_path, blob_name):
    with open(file_path, "rb") as data:
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(data, overwrite=True)
        # Generate a URL (assuming container is public or use SAS token)
        url = blob_client.url
    return url

if __name__ == "__main__":
    pdf_path = "data/briefings/briefing_2025-07-03.pdf"
    pdf_url = upload_pdf_to_blob(pdf_path, "briefing_2025-07-03.pdf")
    print("Uploaded PDF URL:", pdf_url)

