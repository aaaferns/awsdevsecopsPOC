import json
import os
import base64
import time
from datetime import datetime
import boto3
import botocore
import math

def lambda_handler(event, context):

    print(f'event: {json.dumps(event)}')

    # Get the current intent so it can be evaluated right up-front
    current_intent = event['sessionState']['intent']['name']

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #----------------------------------- check to see if the invocation is to warm the bot via automation ------------------------------------#

    if current_intent == "warmBot":
        warmBot_payload =  {
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": current_intent, 
                    "state": "Fulfilled"
                }
            },
            "messages": [
                {
                    "contentType": "PlainText",
                    "content": f"Bot is cooking"
                }
            ]
        }

        return warmBot_payload
        
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #-------------------------------------------------------- Call OpenAI  -------------------------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def makeAIcall(lex_input, userDetailPayload, lambda_client, current_intent, sessionId):
        qs = get_queries()
        inputParams = {
            "current_intent": current_intent,
            "query": lex_input,
            "index": "bogus",
            "userDetailPayload": userDetailPayload,
            "channel": "Text",
            "sessionId": sessionId
        }
        
        qs.update(inputParams)
        print(f'qs: {qs} and the current input is {lex_input}')

        # call the Lambda function that calls Azure OpenAI
        lambdaResponse = lambda_client.invoke(
            FunctionName='arn:aws:lambda:us-east-1:730335323965:function:dwif-demo-adv-openai-FY25-v1',
            InvocationType='RequestResponse',
            Payload=json.dumps(qs)
        )
    
        # Retrieve the Azure OpenAI result
        response_paylaod = json.loads(lambdaResponse['Payload'].read().decode('utf-8'))
        
        # this is the boolean that indicates data was found or not...  "True" = good; "False" = bad
        try:
            good_response = response_paylaod["good_response"]
        except:
            good_response = ""
            print(f'good_response ERROR: boolean not returnd from dwif-demo-adv-openai-FY25-v1')

            ####  TO DO ####
            #### Add logic to return an error message to the user and stop executing
            ####  TO DO ####

         # this is just the answer from the LLM
        try:
            answer = response_paylaod["response_text"]
        except:
            answer = ""
            print(f'response_paylaod ERROR:  {response_paylaod}')
        
        # these are the follow-on-questions that the LLM provided based on the context and current question
        try:
            foqs = response_paylaod["foqs"]
        except:
            foqs = ""
            
        print(f'foqs from payload: {foqs}')
        
        # store the follow-on-questions in session attributes so they can be retrieved if needed
        session_attributes['foqs'] = json.dumps(foqs)

        return answer, good_response
    
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #------------------------------------------ Generate a Sentiment Table -------------------------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def getSentiment(interpretations):

        sentiment          = ''
        nluConfidence      = ''
        sentimentRating    = ''
    
        for key in interpretations:
            if key["intent"]["name"] == current_intent:
                sentiment           = key['sentimentResponse']['sentiment']
                try:
                    nluConfidence   = key['nluConfidence']
                except:
                    nluConfidence   = 'no defined'
                nluConfNeurtal      = key['sentimentResponse']['sentimentScore']['neutral']
                nluConfNeutralPcnt  = round((nluConfNeurtal/1)*100)
                nluConfMixed        = key['sentimentResponse']['sentimentScore']['mixed']
                nluConfMixedPcnt    = round((nluConfMixed/1)*100)
                nluPositive         = key['sentimentResponse']['sentimentScore']['positive']
                nluConfPositivePcnt = round((nluPositive/1)*100)
                nluNegative         = key['sentimentResponse']['sentimentScore']['negative']
                nluConfNegativePcnt = round((nluNegative/1)*100)
                
        nluSentimentTotal  = nluConfNeurtal + nluConfMixed + nluPositive + nluNegative
    
        generalSentimentStatement = ''
        i = 1
        if sentiment == 'NEGATIVE':
            sentimentRating  = nluConfNegativePcnt
            sentimentRanking = f'<img src="/images/bootstrap/emoji-frown-fill.svg" title="{sentiment}" /> {sentimentRating}% <i>{sentiment.lower()}</i>'
            generalSentimentStatement = "I'm verry sorry you're having a bad experience.  &nbsp;Let's try and fix that. &nbsp;"
        elif sentiment == 'NEUTRAL':
            generalSentimentStatement = "Ok. &nbsp;Let's get it. &nbsp;"
            sentimentRating  = nluConfNeutralPcnt
            sentimentRanking = f'<img src="/images/bootstrap/emoji-neutral-fill.svg" title="{sentiment}" /> {sentimentRating}% <i>{sentiment.lower()}</i>'
        elif sentiment == 'MIXED':
            generalSentimentStatement = "Let's get you what you need! &nbsp;"
            sentimentRating  = nluConfMixedPcnt
            sentimentRanking = f'<img src="/images/bootstrap/emoji-neutral-fill.svg" title="{sentiment}" /> {sentimentRating}% <i>{sentiment.lower()}</i>'
        elif sentiment == 'POSITIVE':
            generalSentimentStatement = "You sound like you're getting what you need.  &nbsp;Let's keep that going! &nbsp;"
            sentimentRating  = nluConfPositivePcnt
            sentimentRanking = f'<img src="/images/bootstrap/emoji-smile-fill.svg" title="{sentiment}" /> {sentimentRating}% <i>{sentiment.lower()}</i>'
    
        if verbose == "True":
            print(f'({current_intent}) sentiment: {sentiment} | nluConfidence: {nluConfidence} | nluConfNeurtal: {nluConfNeurtal}({nluConfNeutralPcnt}%) | nluConfMixed: {nluConfMixed}({nluConfMixedPcnt}%) | nluPositive: {nluPositive}({nluConfPositivePcnt}%) | nluNegative: {nluNegative}({nluConfNegativePcnt}%) | nluSentimentTotal: {nluSentimentTotal})')

        return generalSentimentStatement, sentiment, sentimentRating, sentimentRanking
    
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #--------------------------------------- Record feedback, sentiment, etc.,.. in ServiceNow  ----------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def recordResults(userDetailPayload, lambda_client, table, method, instance, itsm_account, itsm_account_pwd, supporting_payload, requestType):
        
        userid    = userDetailPayload['userIdSlot']
        #channel   = userDetailPayload['channel']
        #input     = userDetailPayload['input']
        
        input_params = {
            "instance":             instance,
            "account":              itsm_account,
            "pwd":                  itsm_account_pwd,
            "apimethod":            method,
            "endpoint":             f"/api/now/table/{table}?sysparm_fields=number", 
            "supporting_payload": supporting_payload
        }    
        
        # Call the child function that creates the incident
        labmdaResponse = lambda_client.invoke(
            FunctionName='arn:aws:lambda:us-east-1:730335323965:function:dwif-demo-adv-sn-crud-FY25-v1',
            InvocationType=f'{requestType}',
            Payload=json.dumps(input_params)
        )
        if requestType == "RequestResponse":
            responsePayload       = json.load(labmdaResponse['Payload'])
            if verbose == "True":
                print(f'responsePayload: {responsePayload}')
            
            returnRecNo           = responsePayload['result']['number']
            return returnRecNo
        
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #--------------------------------------- Produce Follow-on-Questions from the AI Response ------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def generate_foqs():
        # retrieve follow-on-questions from session attributes
        foqs = json.loads(session_attributes.get('foqs', '[]'))

        # Create a list to hold the new JSON objects
        foq_buttons = []
        
        if foqs:
            # Iterate through each item and build separate strings
            for question in foqs:
                foq_buttons.append({
                    "text": question[:50],
                    "value": question[:50]
                })
                
            foq_message = f"Follow-on-Questions are based on your current dialog and are intended to be relevant within this topic.\n\n\nSelect one of the questions provided below or ask your new question.\n\n\nPlease use the 'Feedback' button to let us know how we're doing."
            
        else:
            # construct a special message when no FOQ's have been generated.
            foq_message = f"Follow-on-questions were not generated for you.\n\n\nAsk a question to try again.\n\n\nYou can use 'Feedback' to report an issue, provide general information or even suggest an enhancement to the solution."
                
        # add an additional hard coded button
        foq_buttons.append({
            "text": "Provide Feedback",
            "value": "Feedback"
        })
        
        return foq_message, foq_buttons

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #------------------------------------------ Clear the "queries" array from attributes ----------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def clear_queries():
        # retrieve follow-on-questions from session attributes
        session_attributes['queries'] = None
        
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #------------------------------------------ Retrieve the "queries" array from attributes -------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def get_queries():
        # build the q1-q6 json string
        query_json = {f"q{i+1}": "" for i in range(6)}

        # Retrieve follow-on-questions from session attributes
        queries_str = session_attributes.get('queries', '[]')
        
        # Check if queries_str is not None and is a valid JSON string
        if queries_str is not None:
            try:
                queries = json.loads(queries_str)
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError: {e}")
                queries = []
        else:
            queries = []
            
        for i, question in enumerate(queries):
            query_json[f"q{i+1}"] = question

        return query_json
        
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #----------------------------------------------- Retrieve logged in users ITSM details ---------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def getUserSituation(userDetailPayload, lambda_client, instance):
        
        # determine if it's morning or afternoon and create a greeting
        
        print(f'getUserSituation: made it')
        
        #    call function that summarizes the users situation
        #    # of incidents
        #    # of requests
        #    # of outages
        #    # of assets
        #    # of approvals requests
        
        userid    = userDetailPayload['userIdSlot']
        firstname = userDetailPayload['given_nameSlot']
        # instance  = "scienceapplicationsintlcorpsaicdemo9.service-now.com"

        # input_params = {
        #     "userid":               userid,
        #     "instance":             instance,
        #     "account":              "aws.saic",
        #     "pwd":                  "M1P1amazonintONE1!"
        # }    
        #conn.request('GET', f'/api/x_saic4_aws_integr/lextableintegration/getUserSituation?userid={userid}', body=json.dumps(payload), headers=headers)

        input_params = {
            "instance":             f"{instance}",
            "account":              f"{itsm_account}",
            "pwd":                  f"{itsm_account_pwd}",
            "apimethod":            "GET",
            "endpoint":             f"/api/x_saic4_aws_integr/lextableintegration/getUserSituation?userid={userid}",
            "supporting_payload": {
                "short_description": "",
                "long_description":  "",
                "category":          "",
                "subcategory":       "",
                "assignment_group":  ""
            }
        }    
        
        # Call the child function that creates the incident
        labmdaResponse = lambda_client.invoke(
            FunctionName='arn:aws:lambda:us-east-1:730335323965:function:dwif-demo-adv-sn-crud-FY25-v1',
            InvocationType='RequestResponse',
            Payload=json.dumps(input_params)
        )

        #decodedlabmdaResponse = json.loads(labmdaResponse.read().decode())

        queryResults       = json.load(labmdaResponse['Payload'])
        print(f'queryResults: {queryResults}')
        returnITSM         = queryResults['result']
        countOfITSMrecords = len(returnITSM)
        print(f'countOfITSMrecords: {countOfITSMrecords}')
        #print(f'queryResults: {type(queryResults)} - {queryResults}')
        print(f'returnUserSituation: {returnITSM}')

        myResult = ""
        
        #################################################
        ## build output for bot
        #myResult = "<table width='600px;' cellpadding='3' cellspacing='2'><th>Number</th><th></th><th>Requested</th><th>Updated</th><th>Status</th>"
        for i in range(countOfITSMrecords):
            incidentCount    = returnITSM[i]['incidentCount']
            approvalCount    = returnITSM[i]['approvalCount']
            requestCount     = returnITSM[i]['requestCount']
#            href            = f"https://{instance}{linkQuery}{sysID}"
            assetCount       = returnITSM[i]['assetCount']
            outageCount      = returnITSM[i]['outageCount']
            announcements    = returnITSM[i]['announcements']
            userLocationName = returnITSM[i]['userLocationName']

        ##################
        # Announcements
        countOfAnnouncement = len(announcements) 
        returnAnnouncements = f'<br/>**General Announcements**<br/>'
        for i in range(countOfAnnouncement):
            itemNumber = announcements[i]['itemNumber']
            title      = announcements[i]['title']
            summary    = announcements[i]['summary']
            print(f'title: {title}')
            returnAnnouncements += f'{str(itemNumber)} - {title} <img src="/images/bootstrap/info-circle-fill.svg" title="{summary}" /><br/>'
            
        ##################
        # Outages
        if int(outageCount) == 1:
            outageStatement = f'<div style="border-style: solid; border-color:red; padding: 5px 5px 5px 5px;"><img src="/images/bootstrap/exclamation-triangle-fill.svg" /> Your location, **{userLocationName}**, is reporting an outage to a product or service that may be impacting your productivity.&nbsp; To check the status of these outages, please type or say, **"My Outages"**.</div><br/>'
        elif int(outageCount) > 0:
            outageStatement = f'<div style="border-style: solid; border-color:red; padding: 5px 5px 5px 5px;"><img src="/images/bootstrap/exclamation-triangle-fill.svg" /> Your location, **{userLocationName}**, is reporting **{outageCount}** outages to products or services that may be impacting your productivity.&nbsp; To check the status of these outages, please type or say, **"My Outages"**.</div><br/>'
        else:
            outageStatement = f''

        ##################
        # Requests
        if int(requestCount) == 1:
            requestStatement = f'You have **1** active request, '
        elif int(requestCount) > 0:
            requestStatement = f'You have **{requestCount}** active requests, '
        else:
            requestStatement = f"You don't have any active requests, "

        ##################
        # Assets
        if int(assetCount) == 1:
            assetStatement = f'you have **1** asset asigned to you, '
        elif int(assetCount) > 0:
            assetStatement = f'you have **{assetCount}** assets assigned to you, '
        else:
            assetStatement = f"you don't have any assets assigned to you, "

        ##################
        # Approvals
        if int(approvalCount) == 1:
            approvalStatement = f'**one (1)** request requiring your approval, '
        elif int(approvalCount) > 0:
            approvalStatement = f'**{approvalCount}** requests awaiting your approval, '
        else:
            approvalStatement = f'no requests awaiting your approval, '

        ##################
        # Incidents
        if int(incidentCount) == 1:
            incidentStatement = f' and you have **1** open incident.<br/>'
        elif int(incidentCount) > 0:
            incidentStatement = f' and you have **{incidentCount}** open incidents.<br/>'
        else:
            incidentStatement = f' and no active incidents.<br/>'

        ##################
        # Final Message
        finalMessage = f'<br/>You can check any one of these individually by just asking: **My Incidents** | **My Assets** | **My Requests** | **My Approvals** | **My Outages** | **Show me everything**'
            
        myResult += f'<br/>{outageStatement}{requestStatement}{assetStatement}{approvalStatement}{incidentStatement}{returnAnnouncements}{finalMessage}'
        
        #myResult += '</table>'
        print(f'myResult : {myResult}')
        return myResult

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #------------------------------------------------- Retrieve Misc ITSM details ------------------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def makeITSMQuery(userDetailPayload, queryDepth, queryTable, queryFilter, lambda_client, instance): 
        print(f'makeITSMQuery: made it')
        # queryDepth  : summary|individual
        # queryTable  : incident|sc_req_item|outage|approval|assets
        # queryFilter : part of a number

        if queryTable == 'x_saic4_aws_integr_open_ai_transactions':
            userid = userDetailPayload['sessionId']
        else:
            userid = userDetailPayload['userIdSlot']
        limit      = 10
        # instance   = "scienceapplicationsintlcorpsaicdemo9.service-now.com"
        table      = queryTable
        linkQuery  = f"/{table}.do?sys_id="

        input_params = {
            "instance":             f"{instance}",
            "account":              f"{itsm_account}",
            "pwd":                  f"{itsm_account_pwd}",
            "apimethod":            "GET",
            "endpoint":             f"/api/x_saic4_aws_integr/lextableintegration/getUserRecords?table={queryTable}&limit={limit}&userid={userid}",
            "supporting_payload": {
                "short_description": "",
                "long_description":  "",
                "category":          "",
                "subcategory":       "",
                "assignment_group":  ""
            }
        }    
        
        # Call the child function that creates the incident
        labmdaResponse = lambda_client.invoke(
            FunctionName='arn:aws:lambda:us-east-1:730335323965:function:dwif-demo-adv-sn-crud-FY25-v1',
            InvocationType='RequestResponse',
            Payload=json.dumps(input_params)
        )
        print(f'lambda call returned... {labmdaResponse}')
        print(f'table: {table}')

        # Read the output from the second lambda function
        queryResults       = json.load(labmdaResponse['Payload'])
        returnITSM         = queryResults['result']
        countOfITSMrecords = len(returnITSM) 
        print(f'countOfITSMrecords: {countOfITSMrecords}')
        #print(f'queryResults: {type(queryResults)} - {queryResults}')
        print(f'returnITSM: {returnITSM}')

        returnITSMresult = ""
        
        #################################################
        ## INCIDENTS
        if table == 'incident':
            returnITSMresult = "<table width='600px;' cellpadding='3' cellspacing='2'><th>Number</th><th></th><th>Requested</th><th>Updated</th><th>Status</th>"
            for i in range(countOfITSMrecords):
                shortDesc = returnITSM[i]['short_desc']
                sysID     = returnITSM[i]['sysID']
                href      = f"https://{instance}{linkQuery}{sysID}"
                number    = returnITSM[i]['number']
                status    = returnITSM[i]['status']
                requested = returnITSM[i]['requested_on']
                updated   = returnITSM[i]['updated_on']
                
                if requested == updated:
                    updated = "<span style='color:red'>**Never**</span>"
                
                returnITSMresult += f"<tr><td align='center'><a target='itsm' href='{href}'>{number}</a></td><td align='center'><img src='/images/bootstrap/info-circle-fill.svg' title='{shortDesc}' /></td><td align='center'>{requested}</td><td align='center'>{updated}</td><td align='center'>{status}</td></tr>"
            
            returnITSMresult += '</table>'
            print(f'returnITSM INCIDENT result: {returnITSMresult}')
        #################################################
        ## Requests
        elif table == 'sc_req_item':
            returnITSMresult = "<table width='600px;' cellpadding='3' cellspacing='2'><th>Number</th><th></th><th>Requested</th><th>Stage</th><th>Status</th>"
            for i in range(countOfITSMrecords):
                cat_item  = returnITSM[i]['cat_item']
                sysID     = returnITSM[i]['sysID']
                href      = f"https://{instance}{linkQuery}{sysID}"
                request   = returnITSM[i]['request']
                number    = returnITSM[i]['number']
                status    = returnITSM[i]['status']
                stage     = returnITSM[i]['stage']
                requested = returnITSM[i]['requested_on']

                returnITSMresult += f"<tr><td align='center'><a target='itsm' href='{href}'>{number}</a></td><td align='center'><img src='/images/bootstrap/info-circle-fill.svg' title='{cat_item}' /></td><td align='center'>{requested}</td><td align='center'>{stage}</td><td align='center'>{status}</td></tr>"
            
            returnITSMresult += '</table>'
            print(f'returnITSM REQUESTS result: {returnITSMresult}')
        #################################################
        ## Assets
        elif table == 'alm_asset':
            returnITSMresult = "<table width='600px;' cellpadding='3' cellspacing='2'><th>Asset Tag</th><th></th><th>State</th><th>Warranty Exp</th>"
            for i in range(countOfITSMrecords):
                asset_tag     = returnITSM[i]['asset_tag']
                sysID         = returnITSM[i]['sysID']
                href          = f"https://{instance}{linkQuery}{sysID}"
                serial_number = returnITSM[i]['serial_number']
                warranty_expiration = returnITSM[i]['warranty_expiration']
                install_status      = returnITSM[i]['install_status']

                returnITSMresult += f"<tr><td align='center'><a target='itsm' href='{href}'>{asset_tag}</a></td><td align='center'><img src='/images/bootstrap/info-circle-fill.svg' title='{serial_number}' /></td><td align='center'>{install_status}</td><td align='center'>{warranty_expiration}</td></tr>"
            
            returnITSMresult += '</table>'
            print(f'returnITSMresult: {returnITSMresult}')
        #################################################
        ## Outages
        elif table == 'cmdb_ci_outage':
            returnITSMresult = "<table width='600px;' cellpadding='3' cellspacing='2'><th>Number</th><th></th><th>Type</th><th>Started</th>"
            for i in range(countOfITSMrecords):
                number            = returnITSM[i]['number']
                sysID             = returnITSM[i]['sysID']
                href              = f"https://{instance}{linkQuery}{sysID}"
                begin             = returnITSM[i]['begin']
                cmdb_ci           = returnITSM[i]['cmdb_ci']
                type              = returnITSM[i]['type']
                location          = returnITSM[i]['location']
                user_location     = returnITSM[i]['user_location']
                short_description = returnITSM[i]['short_description']

                returnITSMresult += f"<tr><td align='center'><a target='itsm' href='{href}'>{number}</a></td><td align='center'><img src='/images/bootstrap/info-circle-fill.svg' title='{cmdb_ci} is currently down at your location,  {location}.  The description is: {short_description}.  No Return to Service time has been estimated.' /></td><td align='center'>{type}</td><td align='center'>{begin}</td></tr>"
            
            returnITSMresult += '</table>'
            print(f'returnITSM OUTAGES result: {returnITSMresult}')
        #################################################
        ## AI Interactions
        elif table == 'x_saic4_aws_integr_open_ai_transactions':
            returnITSMresult = f"<table style='border-collapse: collapse; border: 1px; padding: 10px; width=600px;'><th width='200px'>Query</th><th>Response</th>"
            row = "odd"
            cellStyle = "style='padding-left: 4px; padding-right: 4px; vertical-align: top;'"
            for i in range(countOfITSMrecords):
                sysID             = returnITSM[i]['sysID']
                href              = f"https://{instance}{linkQuery}{sysID}"
                query             = returnITSM[i]['query']     # [:20]
                response          = returnITSM[i]['response']
                if row == "odd":
                    rowStyle = "style='background-color: #b3dbe4;'"
                    row = "even"
                else:
                    rowStyle = "style='background-color: #bae7f2;'"
                    row = "odd"
                    
                returnITSMresult += f"<tr {rowStyle}><td {cellStyle} align='center'><a target='itsm' href='{href}'> {query}</a></td><td style='border-collapse: collapse; border: 1px; '>{response}</td></tr>"
            
            returnITSMresult += '</table>'

        #################################################
        ## Approvals
        return returnITSMresult

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #----------------------------------------------------- Create Incident in ServiceNow  ----------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def recordResults(userDetailPayload, lambda_client, table, method, instance, itsm_account, itsm_account_pwd, supporting_payload, requestType):
        
        input_params = {
            "instance":             instance,
            "account":              itsm_account,
            "pwd":                  itsm_account_pwd,
            "apimethod":            method,
            "endpoint":             f"/api/now/table/{table}?sysparm_fields=number", 
            "supporting_payload": supporting_payload
        }    
        
        # Call the child function that creates the incident
        labmdaResponse = lambda_client.invoke(
            FunctionName='arn:aws:lambda:us-east-1:730335323965:function:dwif-demo-adv-sn-crud-FY25-v1',
            InvocationType=f'{requestType}',
            Payload=json.dumps(input_params)
        )
        if requestType == "RequestResponse":
            responsePayload       = json.load(labmdaResponse['Payload'])
            if verbose == "True":
                print(f'({current_intent}) responsePayload: {responsePayload}')
            
            returnRecNo           = responsePayload['result']['number']
            return returnRecNo
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # END FUNCTION DEFINITION ### END FUNCTION DEFINITION ### END FUNCTION DEFINITION ### END FUNCTION DEFINITION ### END FUNCTION DEFINITION #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    #------------------------------ ENVRIONMENT VARIABLES ------------------------------------------------------------------------------------#
    
    # Set debugging
    verbose = "True"

    # capture environment variable that support ITSM integration CRUD functions
    instance                = os.environ['ITSM_INSTANCE']
    itsm_account            = os.environ['ITSM_ACCOUNT']
    itsm_account_pwd        = os.environ['ITSM_ACCOUNT_PWD']

    # define thresholds for the called function
    lambdaCfg = botocore.config.Config(
        retries = {'max_attempts': 0},
        read_timeout = 1840,
        connect_timeout = 1600
    )

    lex_client = boto3.client(
        'lexv2-runtime',
        region_name='us-west-2'
    )

    # Create the boto3 object that allows the interaction with other Lambda functions
    lambda_client_obj = boto3.client('lambda', config=lambdaCfg)

    quitIcon    = '<img src="https://media.giphy.com/media/2XflxzGoMXkpe9bvyk8/giphy.gif"/>'
    helpImage   = '<br/><img title="Directions for starting a live chat with an agent" class="vertical-align: bottom;" src="/images/chat_help_info_1.png" height="300" /><br/>'
    kendra_icon = '<img title="AWS Kendra cognitive search of the IT FAQ" class="vertical-align: bottom;" src="/images/kendra_icon.png" height="40" />'
    lambda_icon = '<img title="AWS Lambda" class="vertical-align: bottom;" src="/images/lambda_icon.png" height="15" />&nbsp;'

    inputMode          = event['inputMode']
    if verbose == "True":
        print(f'inputMode: {inputMode}')

    slots              = event['sessionState']['intent']['slots']
    invocationSource   = event['invocationSource']

    sessionId = event['sessionId']

    # capture details about the bot used
    botName      = event['bot']['name']
    botVersion   = event['bot']['version']
    botAliasID   = event['bot']['aliasId']
    botAliasName = event['bot']['aliasName']
    
    botInfo = f'Lex BOT details | Name: {botName} | Version: {botVersion} | Alias ID: {botAliasID} | Alias Name: {botAliasName}'
    if verbose == "True":
        print(f'sessionId: {sessionId}')

    #session_attributes = event['sessionState']['sessionAttributes']
    session_attributes = event['sessionState'].get('sessionAttributes', {})
    
    print(f'session_attributes: json.dumps({session_attributes})')

    lex_input          = event['inputTranscript']
    if verbose == "True":
        print(f'lex_input: {lex_input}')
    
    interpretations    = event['interpretations']
    
    #---------------------------------------------------- Decode JTW -------------------------------------------------------------

    userJWT         = event['sessionState']['sessionAttributes']['idtokenjwt']

    if verbose == "True":
        print(f'({current_intent}) userJWT: {userJWT}')
    
    jwtheader, jwtpayload, jwtsignature = userJWT.split('.')

    missing_header_padding = len(jwtheader) % 4
    if missing_header_padding:
        jwtheader += '='* (4 - missing_header_padding)
            
    missing_payload_padding = len(jwtpayload) % 4
    if missing_payload_padding:
        jwtpayload += '='* (4 - missing_payload_padding)

    decoded_header_bytes = base64.b64decode(str(jwtheader)) 
    decoded_header = decoded_header_bytes.decode('utf-8')
    if verbose == "True":
        print(f'({current_intent}) decoded_header: {decoded_header}')

    decoded_payload_bytes = base64.b64decode(str(jwtpayload)) 
    decoded_payload = decoded_payload_bytes.decode('utf-8')
    if verbose == "True":
        print(f'({current_intent}) decoded_payload: {decoded_payload}')
    
    decoded_payload_dic = json.loads(decoded_payload)

    #-----------------------------------------------------------------------------------------------------------------------------
    #------------------------------------------------ Harvest decoded JTW --------------------------------------------------------
    # userIdSlot       = decoded_payload_dic['identities'][0]['userId']
    # providerName     = decoded_payload_dic['identities'][0]['providerName']
    # providerType     = decoded_payload_dic['identities'][0]['providerType']
    # issuer           = decoded_payload_dic['identities'][0]['issuer']
    # emailSlot        = decoded_payload_dic['email']
    # family_nameSlot  = decoded_payload_dic['family_name']
    # given_nameSlot   = decoded_payload_dic['given_name']
    # phone_numberSlot = decoded_payload_dic['phone_number'] # in +1xxxxxxxxxx format
    # picture          = decoded_payload_dic['picture']      # url to users image, avatar, other
    # exp              = decoded_payload_dic['exp']          # this will be a string and must be converted to Int

    # updated to support Cognito only vs. SAMML
    userIdSlot       = decoded_payload_dic['cognito:username']
    providerName     = decoded_payload_dic['iss']
    providerType     = "AWS Cognito"
    issuer           = "AWS Cognito"
    emailSlot        = decoded_payload_dic['email']
    family_nameSlot  = decoded_payload_dic['family_name']
    given_nameSlot   = decoded_payload_dic['given_name']
    phone_numberSlot = decoded_payload_dic['phone_number'] # in +1xxxxxxxxxx format
    exp              = decoded_payload_dic['exp']          # this will be a string and must be converted to Int

    #-----------------------------------------------------------------------------------------------------------------------------

    formatted_phone = format(int(phone_numberSlot[:-1]), ",").replace(",","-")+ phone_numberSlot[-1]
    if verbose == "True":
        print(f'formatted_phone: {formatted_phone}')

    current_time    = int(time.time())  # this will be float and need to be converted to int
    if verbose == "True":
        print(f'current_time: {current_time}')
    
    if verbose == "True":
        print(f'({current_intent}) exp ({exp})({type(exp)})({datetime.fromtimestamp(exp)}) < current_time ({current_time})({type(current_time)})({datetime.fromtimestamp(current_time)})')
    
    # if the JWT token expiration has been met, return a response indicating such
    print(f'exp: {exp} = current_time: {current_time}')
    if int(exp) < current_time:
        print(f'({current_intent}) EXPIRED: ({exp})({type(exp)})({datetime.fromtimestamp(exp)}) < current_time ({current_time})({type(current_time)})({datetime.fromtimestamp(current_time)})')
        response = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'PlainText',
                    'content': 'Your access has expired.  Please log out and restart your session.'
                }
            ]
        }
        return response
    
    # except:
    #     userIdSlot       = ''
    #     providerName     = ''
    #     providerType     = ''
    #     issuer           = ''
    #     emailSlot        = ''
    #     family_nameSlot  = ''
    #     given_nameSlot   = ''
    #     phone_numberSlot = ''
    #     exp              = ''
    #     iam      = f'JTW is missing or critical data is missing from your authorization record in Cognito.  Please contact support to rectify this issue.'

    sessionId = event['sessionId']

    userDetailPayload = {
        'userIdSlot':       emailSlot,
        'providerName':     providerName,
        'providerType':     providerType,
        'issuer':           issuer,
        'emailSlot':        emailSlot,
        'family_nameSlot':  family_nameSlot,
        'given_nameSlot':   given_nameSlot,
        'phone_numberSlot': phone_numberSlot,
        'exp':              exp,
        'sessionId':        sessionId
    }
    if verbose == "True":
        print(f'({current_intent}) userDetailPayload: {userDetailPayload}')

    # set custom session attributes that can be used by Connect Flow when "connect to a live agent" option is invoked
    session_attributes['connect_phone_number'] = phone_numberSlot
    session_attributes['connect_given_name']   = given_nameSlot
    session_attributes['connect_family_name']  = family_nameSlot
    session_attributes['connect_userId']       = userIdSlot

    #-----------------------------------------------------------------------------------------------------------------------------
    #-------------------------------------- Get the users current sentiment ------------------------------------------------------
    generalSentimentStatement, sentiment, sentimentRating, sentimentRanking = getSentiment(interpretations)
    
    iam      = f'Hi {given_nameSlot} {family_nameSlot}.&nbsp; {generalSentimentStatement} I have your email as {emailSlot} and phone as {formatted_phone}.&nbsp; If any of this information is incorrect, just type or say **"Update my profile"**.  <img src="/images/bootstrap/info-circle-fill.svg" title="You have been authenticated using {providerType} from the {providerName} provider issued by {issuer}." />'
    if verbose == "True":
        print(f'iam: {iam}')

    if verbose == "True":
        print(f'sentimentRating: {sentimentRating}')
        print(f'sentimentRanking: {sentimentRanking}')
        print(f'sentiment: {sentiment}')
    
    if current_intent != "Gather_feedback":
        # check to see how bad the sentiment is and if too bad, return information that inlcudes how to initiate a session with a live agent
        if (sentiment == 'NEGATIVE') and (int(sentimentRating) > 85):
            
            inputPayload = {
                "user":              emailSlot,
                "channel":           'text',
                "lex_input":         lex_input,
                "intent":            current_intent,
                "sentiment_rating":  sentimentRating,
                "sentiment":         sentiment
            }
    
            # record the poor sentiment
            recordResults(userDetailPayload, lambda_client_obj, 'x_saic4_dwif_ai_kn_pilot_sentiment', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'Event')

            # invoke the "Help" Intent
            helpResponse = {
                'sessionState': {
                    'dialogAction': {
                        'type': 'Close'
                    },
                    'sessionAttributes': session_attributes,
                    'intent': {
                        'name': current_intent,
                        'state': 'Fulfilled',
                        'slots': slots
                    },
                },
                'messages': [
                    {
                        'contentType': 'CustomPayload',
                        'content': f'{generalSentimentStatement}\nIf you would like to connect with a live agent follow the instruction shown below.\n\n\nI will still be here to assist you in any way I can once you are done.\n{helpImage}For a **"Live Agent"**, click the menu and select **"Start Live Chat"**.\n\n{sentimentRanking}'
                     }
                ]
            }
            
            return helpResponse

    #-----------------------------------------------------------------------------------------------------------------------------

    #------------------------------ END ENVRIONMENT VARIABLES --------------------------------------------------------------------------------#

    if current_intent == "Show_follow-on-questions":
        ###########################################################################################################################################
        ### Show the follow-on-questions
        ###########################################################################################################################################
        
        foq_message, foq_buttons = generate_foqs()
        foq_response = {
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": current_intent,
                    "state": "Fulfilled",
                    "slots": slots
                },
                'sessionAttributes': session_attributes
            },
            "messages": [
                {
                    "contentType": "ImageResponseCard",
                    "imageResponseCard": {
                        "title": f"Follow-on-Questions are based on your current dialog.",
                        "subtitle": foq_message,
                        "buttons": foq_buttons
                    }
                }
            ]
        }

        print(f'foq_response: {json.dumps(foq_response)}')
        return foq_response
        
    elif current_intent == "FallbackIntent":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #--------------------------------------------------------------- FALLBACKINTENT ----------------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        # Make the OpenAI call
        AIOutput_answer, good_response = makeAIcall(lex_input, userDetailPayload, lambda_client_obj, current_intent, sessionId)
        
        if good_response == "False":
            # if you don't get a good answer back you probably need to move to a new topic. This keeps the bad question from getting
            # included in the RAG
            email_blurb = ""
        else:
            email_blurb = "Check your email for the full respones along with a cost summary of this activity."
        
        # add most recent question to the custom attributes to be included in the RAG
        new_items = json.loads(session_attributes.get('queries', '[]'))
        new_items.append(lex_input)
        session_attributes['queries'] = json.dumps(new_items)

        queries = json.loads(session_attributes['queries'])

        # check for the number of previous quesitons.  If it exceeds 5, let's let them know this is the last time before the topic
        # is required to be changed.
        
        number_of_items = len(queries)
        print(f'number_of_items: {number_of_items}')
        
        #button_value = 'soopa sooot'
        # the following won't work because inline javascript is not secure per CSP :/
        #button_string = f'<button class="pill-button" onclick="submitUtterance(\'{button_value}\')">{button_value}</button>'
        #button_string = f'<button class="pill-button" data-value="{button_value}">{button_value}</button>'

        if good_response == "False":
            clear_queries()
            new_topic_message = f'\n\n**Starting a new topic**: We\'ve covered a lot! What else would you like to know?  Just ask.'
            payload =  {
                "sessionState": {
                    "dialogAction": {
                        "type": "Close"
                    },
                    "intent": {
                        "name": "FallbackIntent",
                        "state": "Fulfilled",
                        "slots": slots
                    },
                    "sessionAttributes": session_attributes
                },
                "messages": [
                    {
                        "contentType": "CustomPayload",
                        "content": f'{AIOutput_answer}<hr>{email_blurb}\n\n{new_topic_message}\n\n{sentimentRanking}'
                    }
                ]
            }
        elif number_of_items > 5:
            clear_queries()
            new_topic_message = f'\n\n**Starting a new topic**: We\'ve covered a lot! What else would you like to know?  Just ask.'
            payload =  {
                "sessionState": {
                    "dialogAction": {
                        "type": "Close"
                    },
                    "intent": {
                        "name": "FallbackIntent",
                        "state": "Fulfilled",
                        "slots": slots
                    },
                    "sessionAttributes": session_attributes
                },
                "messages": [
                    {
                        "contentType": "CustomPayload",
                        "content": f'{AIOutput_answer}<hr>{email_blurb}\n\n{new_topic_message}\n\n{sentimentRanking}'
                    }
                ]
            }
        else:
            new_topic_message = ""
            payload =  {
                "sessionState": {
                    "dialogAction": {
                        "type": "Close"
                    },
                    "intent": {
                        "name": "FallbackIntent",
                        "state": "Fulfilled",
                        "slots": slots
                    },
                    "sessionAttributes": session_attributes
                },
                "messages": [
                    {
                        "contentType": "CustomPayload",
                        #"content": f'Topic ({number_of_items}) here is your answer...\n\n Did this answer your question?<div id="button-container">{button_string}</div>{new_topic_message}'
                        "content": f"{AIOutput_answer}<hr>An email has been sent with the full respones along with a cost summary of this activity.\n\n**Answer your question?**\n\nPlease use the **Thumbs Up** or **Thumbs Down** icons before continuing so we can track how we're doing.{new_topic_message}\n\n{sentimentRanking}"
                    }
                ]
            }
            # new_topic_message = ""
            # payload =  {
            #     "sessionState": {
            #         "dialogAction": {
            #             "type": "ElicitSlot",
            #             "slotToElicit": "answered"
            #         },
            #         "intent": {
            #             "name": "Did_I_answer_your_question",
            #             "state": "InProgress",
            #             "slots": slots
            #         },
            #         "sessionAttributes": session_attributes
            #     },
            #     "messages": [
            #         {
            #             "contentType": "CustomPayload",
            #             #"content": f'Topic ({number_of_items}) here is your answer...\n\n Did this answer your question?<div id="button-container">{button_string}</div>{new_topic_message}'
            #             "content": f'{AIOutput_answer}<hr>Check your email for the full respones along with a cost summary of this activity.\n\n**Answer your question?**\n\nPlease answer **Yes** or **No** before continuing.{new_topic_message}\n\n{sentimentRanking}'
            #         }
            #     ]
            # }

        print(f'payload: {payload}')
        
        return payload
    
    elif current_intent == "Did_I_answer_your_question":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #---------------- validation that the response provided to the user actually answered the question asked. --------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        # in the future use a privately deploy NLP or GTP to evalute input to determin real topic/intent

        yes_variations = ["it did", "it did!", "yes", "yes sir!", "sure", "of course", "sure did", "yep, it sure did", "yep sure did", "yep it sure did","it sure did", "yep", "yep it did","yep, it did","yeah", "yes sir", "yes it did","yes, it did","oh yeah", "yes!", "yes, thank you", "yes thank you"]
        no_variations  = ["it didn't", "it did not", "no", "no, it didn't","nope", "no sir", "no it did not", "no it didn't", "not really", "sort of","not a chance"]
    
        if lex_input.lower() in yes_variations:
            normalized_input = "Yes"
        elif lex_input.lower() in no_variations:
            normalized_input = "No"
        else:
            normalized_input = "Unknown"
            
        print(f'normalized_input: {normalized_input}')
        
        slots['answered'] = {
            "value": {
                "interpretedValue": normalized_input
            }
        }
        
        # if the answer is ultimately "no", retrieve FOQ's from session attributes "queries" array and use those to build the buttons.
        
        if normalized_input == "Yes": 

            payload =  {
                "sessionState": {
                    "dialogAction": {
                        "type": "Close"
                    },
                    "intent": {
                        "name": "Did_I_answer_your_question",
                        "state": "Fulfilled",
                        "slots": slots
                    },
                    "sessionAttributes": session_attributes
                },
                "messages": [
                    {
                        "contentType": "CustomPayload",
                        "content": f"Great! If you have more questions within this topic, please just ask, or if you'd like I can generate **follow-on-topics** for you, just ask!\n\n{sentimentRanking}"
                    }
                ]
            }
        elif normalized_input == "No":
            # if the answer is ultimately "no", retrieve FOQ's from session attributes "foqs" array and use those to build the buttons.
            foq_message, foq_buttons = generate_foqs()
            
            payload = {
                "sessionState": {
                    "dialogAction": {
                        "type": "Close"
                    },
                    "intent": {
                        "name": "Show_follow-on-questions",
                        "state": "Fulfilled",
                        "slots": slots
                    },
                    'sessionAttributes': session_attributes
                },
                "messages": [
                    {
                        "contentType": "ImageResponseCard",
                        "imageResponseCard": {
                            "title": f"I'm sorry.  You can ask another question, or choose one below.  Just click one",
                            "subtitle": foq_message, 
                            "buttons": foq_buttons
                        }
                    }
                ]
            }
        else:
            # if the answer is ultimately "unknown", reprompt for a "yes" or "no" response.
            payload =  {
                "sessionState": {
                    "dialogAction": {
                        "type": "ElicitSlot",
                        "slotToElicit": "answered"
                    },
                    "intent": {
                        "name": "Did_I_answer_your_question",
                        "state": "InProgress",
                        "slots": slots
                    },
                    "sessionAttributes": session_attributes
                },
                "messages": [
                    {
                        "contentType": "CustomPayload",
                        "content": f"I'm sorry but I can't determine if I answered your question or not.  \n\nCan you please give me a **Yes** or a **No**?\n\n{sentimentRanking}" 
                    }
                ]
            }
            
        print(f'payload: {payload}')
        
        return payload

    elif current_intent == "pilot_instructions":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #----------------------------------------- Produce instructions to the pilot participants ------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        pilot_payload =  {
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": current_intent, 
                    "state": "Fulfilled"
                },
                "sessionAttributes": session_attributes
            },
            "messages": [
                {
                    "contentType": "CustomPayload",
                    "content": f"Welcome to the ITO AI Enabled Service Desk pilot!  Ask me a question to get started"
                }
            ]
        }
        print(f'pilot_payload: {pilot_payload}')
        return pilot_payload

    elif current_intent == "Gather_feedback":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #--------------------------------------------- Get feedback from the pilot participants --------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        inputPayload = {
            "user":     emailSlot,
            "channel":  'text',
            "feedback": lex_input
        }

        recNo = recordResults(userDetailPayload, lambda_client_obj, 'x_saic4_dwif_ai_kn_pilot_feedback', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'RequestResponse')
        feedback_payload =  {
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": current_intent, 
                    "state": "Fulfilled"
                }, 
                "sessionAttributes": session_attributes
            },
            "messages": [
                {
                    "contentType": "CustomPayload",
                    "content": f"Thank you for your feedback!\n\n**{recNo}** was recorded and will be evaluated for action.\n\nNow, let's get more answers.  Just ask a question or have me generate ones for you by typing '**foq**'."
                }
            ]
        }
        print(f'feedback_payload: {feedback_payload}')
        return feedback_payload

    elif current_intent == "WhoAmI":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #------------------------------------------------ Return User details from ITSM/other ----------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        mySummary = getUserSituation(userDetailPayload, lambda_client_obj, instance)
        userResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f'{lambda_icon}{iam}{mySummary}<br/><br/>{sentimentRanking}'
                }
            ]
        }
        return userResponse

    elif current_intent == "TicketStatus":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #----------------------------------------------- Return status of incidents from ITSM ----------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        incidentPayload = makeITSMQuery(userDetailPayload, "summary", "incident", "queryFilter", lambda_client_obj, instance)

        ticketResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f"{lambda_icon} Sure!&nbsp; {generalSentimentStatement} Here's your latest Incidents:<br/>{incidentPayload}<br/>If you have more that are not shown, pleae visit the Service Portal or ask to **check an Incident** which will prompt for a specifc Incident.<br/><br/>{sentimentRanking}"
                }
            ]
        }
        return ticketResponse

    elif current_intent == "TicketCreate":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #---------------------------------------------------- Create an incidents in ITSM --------------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        ShortDescription  = slots['ShortDescription']['value']['interpretedValue']
        AdditionalDetails = slots['AdditionalDetails']['value']['interpretedValue']

        inputPayload = {
            "impact":               "2",
            "urgency":              "2",
            "caller_id":            emailSlot,
            "short_description":    ShortDescription,
            "description":          AdditionalDetails,
            "work_notes":           f'Incident created from AWS LEX via AWS Lambda.  {botInfo}',
            "assignment_group":     "Service Desk",
            "sys_class_name":       "incident",
            "contact_type":         "AWS Lex",
            "category":             "Enterprise Customer Service",
            "subcategory":          "AI-Chatbot"
        }

        # create the incident
        IncidentNumber = recordResults(userDetailPayload, lambda_client_obj, 'incident', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'RequestResponse')

        print(f'({current_intent}) IncidentNumber: {IncidentNumber}')

        contentBack = f"I've created Incident **{IncidentNumber}** regarding your issue."
        print(f'({current_intent}) contentBack {contentBack}')

        ticketCreatePayload = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f"{contentBack}"
                }
            ]
        }
        return ticketCreatePayload


    elif current_intent == "RequestStatus":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #----------------------------------------------- Return status of Requests from ITSM -----------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        requestPayload = makeITSMQuery(userDetailPayload, "summary", "sc_req_item", "queryFilter", lambda_client_obj, instance)

        requestResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f"{lambda_icon} Sure!&nbsp; {generalSentimentStatement} Here's your latest Requests:<br/>{requestPayload}<br/>If you have more that are not shown, pleae visit the Service Portal or ask to **check a Request** which will prompt for a specifc Request.<br/><br/>{sentimentRanking}"
                }
            ]
        }
        return requestResponse

    elif current_intent == "MyAssets":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #------------------------------------------------- Return status of Assets from ITSM -----------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        requestPayload = makeITSMQuery(userDetailPayload, "summary", "alm_asset", "queryFilter", lambda_client_obj, instance)

        assetResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f"{lambda_icon} Sure!&nbsp; {generalSentimentStatement}  Here are your assigned assets:<br/>{requestPayload}<br/>If you have more that are not shown, pleae visit the Service Portal or ask to **check an Asset** which will prompt for a specifc Asset.<br/><br/>{sentimentRanking}"
                }
            ]
        }
        return assetResponse

    elif current_intent == "MyOutages":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #----------------------------------------------- Return relevant Outages from ITSM -------------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        outagePayload = makeITSMQuery(userDetailPayload, "summary", "cmdb_ci_outage", "queryFilter", lambda_client_obj, instance)

        outageResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f"{lambda_icon} Sure!&nbsp; {generalSentimentStatement}  Here are outages at **your location** that may be impacting service for you:<br/>{outagePayload}<br/>If you have more that are not shown, pleae visit the Service Portal or ask to **check an Outage** which will prompt for a specifc Outage.<br/><br/>{sentimentRanking}"
                }
            ]
        }
        return outageResponse

    elif current_intent == "myAI":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #---------------------------------------------- Return previous AI requests from ITSM ----------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        aiInteractionPayload = makeITSMQuery(userDetailPayload, "summary", "x_saic4_aws_integr_open_ai_transactions", "queryFilter", lambda_client_obj, instance)

        aiResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f"{lambda_icon} Sure!&nbsp; {generalSentimentStatement}  Here are your last 10 Open AI interactions:<br/>{aiInteractionPayload}<br/>If you have more that are not shown, pleae visit the Service Portal or ask to **get an AI interaction** which will prompt for a specifc Interaction.<br/><br/>{sentimentRanking}"
                }
            ]
        }
        return aiResponse
        
    elif current_intent == "Help":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #----------------------------------------------------- Show user how to get help ---------------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        helpResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f'For a **"Live Agent"**, click the menu and select **"Start Live Chat"**.\n\nI will still be here to assist you in any way I can once you are done.\n\n{helpImage}\n\n{sentimentRanking}'
                }
            ]
        }
        
        return helpResponse
        
    elif current_intent == "New_topic":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #----------------------------------------------------- Change topics for genai -----------------------------------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        
        # remove FOQ's and previous questions.
        clear_queries()
        
        NewTopicResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'CustomPayload',
                    'content': f'{lambda_icon} Sure!  What would you like to learn now?\n\n{sentimentRanking}'
                }
            ]
        }
        
        return NewTopicResponse
    
    elif current_intent == "Thumbs_up":

        inputPayload = {
            "user":      emailSlot,
            "channel":   'text',
            "queries":   get_queries(),
            "sessionid": sessionId,
            "thumb_orientation": "up"
        }
        
        # record the the thumbs down intent
        recordResults(userDetailPayload, lambda_client_obj, 'x_saic4_dwif_ai_kn_pilot_not_helpful_feedback', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'Event')

        thumbsUpResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'sessionAttributes': session_attributes,
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled',
                    'slots': slots
                },
            },
            'messages': [
                {
                    'contentType': 'PlainText',
                    'content': f'Got it!  Thanks! If you have another question, just ask.'
                }
            ]
        }
        
        return thumbsUpResponse
    elif current_intent == "Thumbs_down":

        inputPayload = {
            "user":      emailSlot,
            "channel":   'text',
            "queries":   get_queries(),
            "sessionid": sessionId,
            "thumb_orientation": "down"
        }
        
        # record the the thumbs down intent
        recordResults(userDetailPayload, lambda_client_obj, 'x_saic4_dwif_ai_kn_pilot_not_helpful_feedback', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'Event')
        
        foq_message, foq_buttons = generate_foqs()

        # thumbsUpResponse = {
        #     'sessionState': {
        #         'dialogAction': {
        #             'type': 'Close'
        #         },
        #         'sessionAttributes': session_attributes,
        #         'intent': {
        #             'name': current_intent,
        #             'state': 'Fulfilled',
        #             'slots': slots
        #         },
        #     },
        #     'messages': [
        #         {
        #             'contentType': 'PlainText',
        #             'content': f"Captured!"
        #          }
        #     ]
        # }
        thumbsUpResponse = {
            "sessionState": {
                "dialogAction": {
                    "type": "Close"
                },
                "intent": {
                    "name": "Show_follow-on-questions",
                    "state": "Fulfilled",
                    "slots": slots
                },
                'sessionAttributes': session_attributes
            },
            "messages": [
                {
                    "contentType": "ImageResponseCard",
                    "imageResponseCard": {
                        "title": f"You can ask another question, or choose one below.  Just click one",
                        "subtitle": foq_message, 
                        "buttons": foq_buttons
                    }
                }
            ]
        }
        
        return thumbsUpResponse
