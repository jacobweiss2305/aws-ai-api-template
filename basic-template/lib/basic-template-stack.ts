import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigatewayv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigatewayv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import { HttpMethod } from 'aws-cdk-lib/aws-apigatewayv2';
import * as dotenv from 'dotenv';

dotenv.config();

export class BasicTemplateStack extends cdk.Stack {
    constructor(scope: Construct, id: string, props?: cdk.StackProps) {
        super(scope, id, props);

        const requiredEnvVars = [
            'OPENAI_API_KEY',
            'MODEL',
            'ZENDESK_USERNAME',
            'ZENDESK_PW',
        ];

        for (const envVar of requiredEnvVars) {
            if (typeof process.env[envVar] !== 'string') {
                throw new Error(`${envVar} environment variable is not set`);
            }
        }

        const processStatusTable = new dynamodb.Table(this, "tutorialAgentProcessStatus", {
            partitionKey: { name: "processId", type: dynamodb.AttributeType.STRING },
            billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        });

        const httpApi = new apigatewayv2.HttpApi(this, "tutorialAgentHttpApi", {
            corsPreflight: {
                allowHeaders: ['Content-Type'],
                allowMethods: [apigatewayv2.CorsHttpMethod.POST, apigatewayv2.CorsHttpMethod.GET],
                allowOrigins: ['*'],
            },
        });

        const zendeskProcessLambda = new lambda.DockerImageFunction(this, "tutorialZendeskAgent", {
            code: lambda.DockerImageCode.fromImageAsset("./lambdas/zendesk"),
            memorySize: 1024,
            timeout: cdk.Duration.seconds(30),
            architecture: lambda.Architecture.ARM_64,
            environment: {
                OPENAI_API_KEY: process.env.OPENAI_API_KEY as string,
                MODEL: process.env.MODEL as string,
                ZENDESK_USERNAME: process.env.ZENDESK_USERNAME as string,
                ZENDESK_PW: process.env.ZENDESK_PW as string,
                PROCESS_TABLE: processStatusTable.tableName,
            },
        });

        const financialAgentLambda = new lambda.DockerImageFunction(this, "tutorialFinancialAgent", {
            code: lambda.DockerImageCode.fromImageAsset("./lambdas/financial_analyst"),
            memorySize: 1024,
            timeout: cdk.Duration.seconds(90),
            architecture: lambda.Architecture.ARM_64,
            environment: {
                OPENAI_API_KEY: process.env.OPENAI_API_KEY as string,
                MODEL: process.env.MODEL as string,
                PROCESS_TABLE: processStatusTable.tableName,
            },
        });        

        const initiatorLambda = new lambda.DockerImageFunction(this, "tutorialAgentInitiatorFunction", {
            code: lambda.DockerImageCode.fromImageAsset("./lambdas/initiator"),
            memorySize: 1024,
            timeout: cdk.Duration.seconds(30),
            architecture: lambda.Architecture.ARM_64,
            environment: {
                PROCESS_TABLE: processStatusTable.tableName,
                RESEARCH_AGENT_FUNCTION_NAME: financialAgentLambda.functionName,
            },
        });

        httpApi.addRoutes({
            path: "/initiate/{type}",
            methods: [apigatewayv2.HttpMethod.POST],
            integration: new apigatewayv2Integrations.HttpLambdaIntegration("InitiatorIntegration", initiatorLambda),
        });
        

        const statusCheckLambda = new lambda.DockerImageFunction(this, "tutorialAgentStatusCheckFunction", {
            code: lambda.DockerImageCode.fromImageAsset("./lambdas/poller"),
            memorySize: 1024,
            timeout: cdk.Duration.seconds(30),
            architecture: lambda.Architecture.ARM_64,
            environment: {
                PROCESS_TABLE: processStatusTable.tableName
            },
        });

        const lambdaInvokePolicyStatement = new iam.PolicyStatement({
            actions: ['lambda:InvokeFunction'],
            resources: [financialAgentLambda.functionArn],
            effect: iam.Effect.ALLOW,
        });


        initiatorLambda.role?.attachInlinePolicy(new iam.Policy(this, 'InvokeLambdaPolicy', {
            statements: [lambdaInvokePolicyStatement],
        }));

        processStatusTable.grantReadWriteData(initiatorLambda);
        processStatusTable.grantReadWriteData(zendeskProcessLambda);
        processStatusTable.grantReadWriteData(financialAgentLambda);
        processStatusTable.grantReadData(statusCheckLambda);
        
        financialAgentLambda.grantInvoke(initiatorLambda);

        const statusCheckIntegration = new apigatewayv2Integrations.HttpLambdaIntegration("StatusCheckIntegration", statusCheckLambda);

        httpApi.addRoutes({
            path: "/status/{processId}",
            methods: [apigatewayv2.HttpMethod.GET],
            integration: statusCheckIntegration,
        });

        const zendeskIntegration = new apigatewayv2Integrations.HttpLambdaIntegration("zendeskIntegration", zendeskProcessLambda);
        const financialIntegration = new apigatewayv2Integrations.HttpLambdaIntegration("financialAgentIntegration", financialAgentLambda);

        httpApi.addRoutes({
            path: "/zendesk",
            methods: [HttpMethod.POST],
            integration: zendeskIntegration,
        });

        httpApi.addRoutes({
            path: "/research",
            methods: [HttpMethod.POST],
            integration: financialIntegration,
        });

        new cdk.CfnOutput(this, "ProcessStatusTableName", {
            value: processStatusTable.tableName,
        });

        new cdk.CfnOutput(this, "HttpAPIUrl", {
            value: httpApi.url!,
        });
    }
}