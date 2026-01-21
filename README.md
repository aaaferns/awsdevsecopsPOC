# Build DevSecOps Pipeline in AWS

The project includes an Amazon CloudFormation template to help provision resources to build DevSecOps Pipeline in AWS

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

## Objective:
Thus, the objective here is to demonstrate how DevSecOps works in reality. The following series split into two parts (refer below) with very simple and clear instructions to provision a CI/CD pipeline adhering to DevSecOps principles in AWS. [Click Here](https://hackernoon.com/connect-to-ec2-remote-systems-from-the-ansible-control-machine-using-aws-ssm-parameter-store-jt2k342k), to go through the Step-by-Step Tutorial. 

## How Does it Work:
The tutorial has used open-source tools to build the DevSecOps pipeline to make the demo more achievable. The below diagram depicts the tools and native services used along with the security control gates applied in the process.

![alt text](https://hackernoon.com/images/gv93oOBCpSQa2kRIURhv0A8fVP33-gu14338u.jpeg)

![alt text](https://hackernoon.com/images/gv93oOBCpSQa2kRIURhv0A8fVP33-2o1l3378.png)

```

-- Master template deployment. -- FAILED. so used default launchfrom website.
cd /c/angelo/dwif/lab/AWSDevSecOpsPOC/CFNTemplate
aws cloudformation package --template-file  template.yml --s3-bucket dwif-lambda-project-artifacts --output-template-file output-template.yaml

-- deploy
aws cloudformation deploy --template-file C:\\angelo\\dwif\\lab\\AWSDevSecOpsPOC\\CFNTemplate\\output-template.yaml --stack-name devsecopspoc-infra-stack --capabilities CAPABILITY_NAMED_IAM

-- Deployment of lambda stack.
-- package 

aws cloudformation package --template-file template_cf.yml --s3-bucket dwif-lambda-project-artifacts --output-template-file output-template-cf.yaml
-- deploy
aws cloudformation deploy --template-file C:\\angelo\\dwif\\fy25\\AWSDevSecOpsTutorial\\output-template-cf.yaml --stack-name dwif-devsecops-lambda-stack --capabilities CAPABILITY_IAM


-- lab packaging
aws cloudformation package --template-file template_cf.yml --s3-bucket dwif-lambda-project-artifacts --output-template-file output-template-cf.yaml
-- deploy
output of this cmd is copied to CFNTemplate directory for use in codepipeline to deploy the template.
aws cloudformation deploy --template-file C:\\angelo\\dwif\\lab\\AWSDevSecOpsTutorial\\output-template-cf.yaml --stack-name dwif-devsecops-lambda-stack --capabilities CAPABILITY_IAM


-- add 2 params from json file into template_cf.yml  file.
-- change PreProdChangeSet in pipeline to point to template_cf.yml instead of Main-stack.yml
-- added resource: "*" in cloudformation role used from IAM.

-- added cloudformation full access to CloudFormationRole-DevSecOpsTutorial

-- added IAM full access policy  to 
CloudFormationRole-DevSecOpsTutorial role
-- added s3 full acess to the cloudformation-devsecopstutorial role.

-- added lambda full access to the same role.


-- Testing incorporation of aws cloudformation package and build instead of supplying output of cloudformation package to the build phase in pipeline.
User: arn:aws:sts::516595067404:assumed-role/CodePipelineRole-DevSecOpsTutorial/1741028217480 is not authorized to perform: cloudformation:DescribeStacks on resource: arn:aws:cloudformation:us-west-2:516595067404:stack/LambdaCodeBuildStack/* because no identity-based policy allows the cloudformation:DescribeStacks action (Service: AmazonCloudFormation; Status Code: 403; Error Code: AccessDenied; Request ID: 1fc9df0a-1122-491a-9f9f-cae96c14293f; Proxy: null)
-- Added cloudformationFullAccess to role. testing again.

-- corrected spelling for config-pre-prod.json file name.
corrected spelling of template file.
corrected yaml to yml extension.

Failed at codebuild resources.
This AWS::CloudFormation::Stack resource is in a ROLLBACK_IN_PROGRESS state.

Transform AWS::Serverless-2016-10-31 failed with: Invalid Serverless Application Specification document. Number of errors found: 2. Resource with id [AdvBotChatLambdaFunction] is invalid. 'CodeUri' is not a valid S3 Uri of the form 's3://bucket/key' with optional versionId query parameter. Resource with id [AdvBotLambdaFunction] is invalid. 'CodeUri' is not a valid S3 Uri of the form 's3://bucket/key' with optional versionId query parameter.. Rollback requested by user.


Parameters: [CodeBuildBucket, CodeBuildObjectKey] must have values (Service: AmazonCloudFormation; Status Code: 400; Error Code: ValidationError; Request ID: b70cd04d-7f08-4e55-9e3a-314f3da9eae9; Proxy: null)

-- after upgrade to 12.1.0 dependency-check.
[Container] 2025/03/04 23:07:42.960036 Running command gpg --verify dependency-check-*-release.zip.asc
gpg: assuming signed data in 'dependency-check-12.1.0-release.zip'
gpg: Signature made Sun Feb 16 14:26:47 2025 UTC
gpg:                using RSA key 259A55407DD6C00299E6607EFFDE55BE73A2D1ED
gpg: Can't check signature: No public key

-- removed dependency check SCA from build pipeline to test the lambda deployment.

-- added code build admin access to codepipeline role.

User: arn:aws:sts::516595067404:assumed-role/CodePipelineRole-DevSecOpsTutorial/1741198287026 is not authorized to perform: iam:PassRole on resource: arn:aws:iam::516595067404:role/code-build-lambda-cloudformationrole-9pXShapccN2M because no identity-based policy allows the iam:PassRole action (Service: AmazonCloudFormation; Status Code: 403; Error Code: AccessDenied; Request ID: 378ebe39-65a8-42b8-85e4-d6c50863993b; Proxy: null)

-- added IAM fullAccess to codepipelinerole.
-- added SNS fullaccess to the codepipeline role.
``

```

03/14/2025:
-----------
There was an error creating this change set
User: arn:aws:sts::516595067404:assumed-role/CloudFormationRole-devsecopspoc-infra-stack/AWSCloudFormation is not authorized to perform: cloudformation:CreateChangeSet on resource: arn:aws:cloudformation:us-west-2:aws:transform/Serverless-2016-10-31 because no identity-based policy allows the cloudformation:CreateChangeSet action
-- TODO: Add cloudformationfull access, s3 full access, iamfull access and lambda full access to the role in the template.

-- Added cloudformationfull access and s3 full access to the role.
CodebuildRole-devsecopspoc-infra-stack
-- TODO  do this in the template

-- Release changes on the Pipeline to test:
Failed at PreProdChangeSet.
There was an error creating this change set
Transform AWS::Serverless-2016-10-31 failed with: Invalid Serverless Application Specification document. Number of errors found: 2. Resource with id [AdvBotChatLambdaFunction] is invalid. 'CodeUri' is not a valid S3 Uri of the form 's3://bucket/key' with optional versionId query parameter. Resource with id [AdvBotLambdaFunction] is invalid. 'CodeUri' is not a valid S3 Uri of the form 's3://bucket/key' with optional versionId query parameter.

-- so it is expecting the aws cloudformation package cmd rather than original template to build lambda.
-- TODO incorporate the codebuild to get this out in a phase.
-- copy lambda-function build and lamda-function-deploy from aws-samples-code-build-lambda project in template.yaml.
   copy the codebuild project snippet in the template.yaml file to build all the infra namely: CFBuildspec.yaml is the codebuild file to do this.

as of 4:00pm all the above changes are in place.
TODO: Delete existing cloudformation stack. Redeply the infra stack. checkout the project from codecommit and put the lambda cf build file in it. add the lambda source from this project.
change the s3 folder name in CFBuildSpec.yml
Deploy the stack and see if it works. 
Compare codebuild project in new with the one that works if it does not work.

Test again the pipeline.


```

-- Deployed with changes.
Error at Preprod stage:
Requires capabilities : [CAPABILITY_AUTO_EXPAND] (Service: AmazonCloudFormation; Status Code: 400; Error Code: InsufficientCapabilitiesException; Request ID: bffd020a-110f-4371-964e-5b46118eee13; Proxy: null)