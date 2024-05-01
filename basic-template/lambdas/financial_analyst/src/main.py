import logging
import json
import os
from uuid import uuid4

from phi.assistant.team import Assistant
from phi.tools.yfinance import YFinanceTools
from phi.tools.newspaper_toolkit import NewspaperToolkit

import boto3

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
dynamodb = boto3.resource("dynamodb")

def handler(event, context):
    process_id = event["processId"]
    question = event["question"]
    question = f"Process ID: {str(process_id)}\n{str(question)}"
    # Update the process status to 'PROCESSING' in DynamoDB
    process_table = dynamodb.Table(os.environ["PROCESS_TABLE"])
    process_table.update_item(
        Key={"processId": process_id},
        UpdateExpression="SET #status = :status",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":status": "PROCESSING"},
    )

    try:
        stock_analyst = Assistant(
            name="Stock Analyst",
            role="Get current stock price, analyst recommendations, income statements, stock fundamentals, and news for a company.",
            tools=[
                YFinanceTools(
                    stock_price=True,
                    stock_fundamentals=True,
                    income_statements=True,
                    key_financial_ratios=True,
                    analyst_recommendations=True,
                    company_news=True,
                    technical_indicators=True,
                    company_profile=True,
                ),
                NewspaperToolkit(),
            ],
            description="You are an stock analyst tasked with producing factual reports on companies.",
            instructions=[
                "Answer the users question based on the tools available to you.",
                "Gather the current stock price, analyst recommendations, income statements, stock fundamentals, and news for the company in question."
                "Be objective and create a detailed report for the user that either confirms or denies their statement.",
            ],
        )

        res = stock_analyst.run(question, stream=False)

        process_table.update_item(
            Key={"processId": process_id},
            UpdateExpression="SET #status = :status, #result = :result",
            ExpressionAttributeNames={"#status": "status", "#result": "result"},
            ExpressionAttributeValues={
                ":status": "COMPLETED",
                ":result": json.dumps(res),
            },
        )
        
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