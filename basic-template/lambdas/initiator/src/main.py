import json
import uuid
import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(format=LOG_FORMAT)


dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

def handler(event, context):
    # Determine which function to invoke
    function_type = event['pathParameters']['type']
    if function_type == 'research':
        lambda_function_name = os.environ['RESEARCH_AGENT_FUNCTION_NAME']             
    else:
        return {'statusCode': 400, 'body': 'Invalid function type'}

    # Remaining logic as previously defined...
    request_body = json.loads(event['body'])
    process_id = str(uuid.uuid4())
    process_table = dynamodb.Table(os.environ['PROCESS_TABLE'])
    process_table.put_item(Item={
        'processId': process_id,
        'status': 'PENDING',
        'input': request_body
    })
    logger.info(f'Process {process_id} created')
    logger.info(f'Long running function name: {lambda_function_name}')

    lambda_client.invoke(
        FunctionName=lambda_function_name,
        InvocationType='Event',
        Payload=json.dumps({
            'processId': process_id,
            'question': request_body.get('question', '')
        })
    )

    return {
        'statusCode': 200,
        'body': json.dumps({'processId': process_id})
    }