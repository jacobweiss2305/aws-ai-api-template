import logging
import json
import os
import requests
import re
from uuid import uuid4

from phi.llm.openai import OpenAILike
from phi.assistant import Assistant

import boto3

def strip_html(content):
    """
    Remove HTML tags from the given content string.

    Args:
    content (str): A string containing HTML content.

    Returns:
    str: The content string with all HTML tags removed.
    """
    clean = re.compile('<.*?>')
    return re.sub(clean, '', content)

def dedupe_articles(articles):
    """
    Remove duplicate articles based on their 'name'.
    :param articles: List of dictionaries representing articles.
    :return: A list of dictionaries with duplicates removed.
    """
    seen = set()
    deduped_articles = []
    for article in articles:
        if article['name'] not in seen:
            deduped_articles.append(article)
            seen.add(article['name'])
    return deduped_articles

def search_zendesk(search_string: str):
    zd_username = os.getenv("ZENDESK_USERNAME")
    zd_password = os.getenv("ZENDESK_PW")
    company_name = os.getenv("COMPANY_NAME")
    auth = (zd_username, zd_password)
    url = f"https://{company_name}.zendesk.com/api/v2/help_center/articles/search.json?query={search_string}"
    response = requests.get(url, auth=auth).json()
    deduped_articles = dedupe_articles(response['results'])
    articles = [strip_html(i["body"]) for i in deduped_articles]
    return json.dumps(articles)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
dynamodb = boto3.resource("dynamodb")

def handler(event, context):
    request_body = json.loads(event['body'])
    process_id = str(uuid4())
    logger.info(f"Received event: {event}")
    question = request_body.get('question', '')
    process_table = dynamodb.Table(os.environ["PROCESS_TABLE"])

    try:
        customer_support = Assistant(
            name="Zendesk Search Assistant",
            llm=OpenAILike(model="gpt-3.5-turbo-0125", api_key=os.getenv("OPENAI_API_KEY")),
            tools=[search_zendesk],
            tool_call_limit=2,
            description="You are a customer support agent. Use keywords to search for relevant articles on Zendesk.",
            instructions=[
                "Given a question, search zendesk based on keywords.",
                "Once you have enough information, provide the user with the answer.",
            ],
        )
        res = customer_support.run(question, stream=False)
        
        process_table.put_item(Item={
            'processId': process_id,
            'status': 'COMPLETED',
            'input': question,
            'result': res
        })
        
        return {
            "statusCode": 200,
            "body": json.dumps({"processId": process_id, "message": "Process completed successfully", "result": res}),
            "headers": {"Content-Type": "application/json"},
        }
    except Exception as e:
        # Update the process status to 'FAILED' in DynamoDB if an error occurs
        process_table.update_item(
            Key={"processId": process_id},
            UpdateExpression="SET #status = :status, #error = :error",
            ExpressionAttributeNames={"#status": "status", "#error": "error"},
            ExpressionAttributeValues={":status": "FAILED", ":error": str(e)},
        )
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "An error occurred during processing"}),
            "headers": {"Content-Type": "application/json"},
        }