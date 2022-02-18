from typing import Dict, Optional

import io
import json
from loguru import logger
import datetime

from google.cloud import storage
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
from google.protobuf import duration_pb2


def create_task(cfg, payload, task_name, delay):
    """Create a task with a payload, and a delay in s
    
    """
    
    duration = duration_pb2.Duration()

    duration.FromSeconds(1800)
    
    # Construct the request body.
    task = {
        "dispatch_deadline": duration,
        "http_request": {  # Specify the type of request.
            "http_method": tasks_v2.HttpMethod.POST,
            "url": cfg['url'],  # The full url path that the task will be sent to.
            'oidc_token': {
               'service_account_email': cfg['service_account']
            },
        }
    }
    
    if delay is not None:
        # Convert "seconds from now" into an rfc3339 datetime string.
        d = datetime.datetime.utcnow() + datetime.timedelta(seconds=delay)

        # Create Timestamp protobuf.
        timestamp = timestamp_pb2.Timestamp()
        timestamp.FromDatetime(d)

        # Add the timestamp to the tasks.
        task["schedule_time"] = timestamp
    
    if isinstance(payload, dict):
        # Convert dict to JSON string
        payload = json.dumps(payload)
        # specify http content-type to application/json
        task["http_request"]["headers"] = {"Content-type": "application/json"}

    # The API expects a payload of type bytes.
    converted_payload = payload.encode()
    
    task["name"] = task_name

    # Add the payload to the request.
    task["http_request"]["body"] = converted_payload

    """ No lead time.
    if in_seconds is not None:
        # Convert "seconds from now" into an rfc3339 datetime string.
        d = datetime.datetime.utcnow() + datetime.timedelta(seconds=in_seconds)

        # Create Timestamp protobuf.
        timestamp = timestamp_pb2.Timestamp()
        timestamp.FromDatetime(d)

        # Add the timestamp to the tasks.
        task["schedule_time"] = timestamp
    """
    
    return task

def deploy_task(cfg, task):
    
    # Create a client.
    client = tasks_v2.CloudTasksClient()
    
    task["name"] = client.task_path(cfg['project'], cfg['location'], cfg['queue'], task["name"])

    # Construct the fully qualified queue name.
    parent = client.queue_path(
        cfg['project'], 
        cfg['location'], 
        cfg['queue'],
    )
    
    # Use the client to build and send the task.
    response = client.create_task(request={"parent": parent, "task": task})

    logger.info("Created task {}".format(response.name))
    
    return 1

def download_blob(url: str) -> io.BytesIO:
    """Download a blob as bytes
    Args:
        url (str): the url to download
    Returns:
        io.BytesIO: the content as bytes
    """
    storage_client = storage.Client()
    
    bucket_id = url.split('/')[0]
    file_path = '/'.join(url.split('/')[1:])
    
    bucket = storage_client.bucket(bucket_id)
    blob = bucket.blob(file_path)
    
    f = io.BytesIO(blob.download_as_bytes())
    return f
    
def download_blob_to_filename(url: str, local_path: str) -> int:
    """Download a blob as bytes
    Args:
        url (str): the url to download
    Returns:
        io.BytesIO: the content as bytes
    """
    storage_client = storage.Client()
    
    bucket_id = url.split('/')[0]
    file_path = '/'.join(url.split('/')[1:])
    
    bucket = storage_client.bucket(bucket_id)
    blob = bucket.blob(file_path)
    
    blob.download_to_filename(local_path)
    return 1


def upload_blob(source_directory: str, target_directory: str):
    """Function to save file to a bucket.
    Args:
        target_directory (str): Destination file path.
        source_directory (str): Source file path
    Returns:
        None: Returns nothing.
    Examples:
        >>> target_directory = 'target/path/to/file/.pkl'
        >>> source_directory = 'source/path/to/file/.pkl'
        >>> save_file_to_bucket(target_directory)
    """

    client = storage.Client()
    
    bucket_id = target_directory.split('/')[0]
    file_path = '/'.join(target_directory.split('/')[1:])

    bucket = client.get_bucket(bucket_id)

    # get blob
    blob = bucket.blob(file_path)

    # upload data
    blob.upload_from_filename(source_directory)

    return target_directory

def download_cloud_json(bucket_name: str, filename: str, **kwargs) -> Dict:
    """
    Function to load the json data for the WorldFloods bucket using the filename
    corresponding to the image file name. The filename corresponds to the full
    path following the bucket name through intermediate directories to the final
    json file name.
    Args:
      bucket_name (str): the name of the Google Cloud Storage (GCP) bucket.
      filename (str): the full path following the bucket_name to the json file.
    Returns:
      The unpacked json data formatted to a dictionary.
    """
    # initialize client
    client = storage.Client(**kwargs)
    # get bucket
    bucket = client.get_bucket(bucket_name)
    # get blob
    blob = bucket.blob(filename)
    # check if it exists
    # TODO: wrap this within a context
    return json.loads(blob.download_as_string(client=None))

def cloud_file_exists(full_path: str, **kwargs) -> bool:
    """
    Function to check if the file in the bucket exist utilizing Google Cloud Storage
    (GCP) blobs.
    Args:
      bucket_name (str): a string corresponding to the name of the GCP bucket.
      filename_full_path (str): a string containing the full path from bucket to file.
    Returns:
      A boolean value corresponding to the existence of the file in the bucket.
    """
    
    bucket_name = full_path.split('/')[0]
    remaining_path = '/'.join(full_path.split('/')[1:])
    
    # initialize client
    client = storage.Client(**kwargs)
    # get bucket
    bucket = client.get_bucket(bucket_name)
    # get blob
    blob = bucket.blob(remaining_path)
    # check if it exists
    return blob.exists()