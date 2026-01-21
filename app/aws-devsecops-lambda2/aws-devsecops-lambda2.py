import os
import json
import boto3
import botocore
import random

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
            "query": f'{lex_input}?',
            "index": "bogus",
            "userDetailPayload": userDetailPayload,
            "channel": "Voice",
            "sessionId": sessionId
        }
        
        qs.update(inputParams)
        print(f'({current_intent}) qs: {qs} and the current input is {lex_input}')

        # call the Lambda function that calls Azure OpenAI
        lambdaResponse = lambda_client.invoke(
            FunctionName='arn:aws:lambda:us-east-1:730335323965:function:dwif-demo-adv-openai-FY25-v1',
            InvocationType='RequestResponse',
            Payload=json.dumps(qs)
        )
    
        # Retrieve the Azure OpenAI result
        response_paylaod = json.loads(lambdaResponse['Payload'].read().decode('utf-8'))
        print(f'({current_intent}) response_paylaod: {response_paylaod}')
        # this is the boolean that indicates data was found or not...  "True" = good; "False" = bad
        try:
            good_response = response_paylaod["good_response"]
        except:
            good_response = ""
            print(f'({current_intent}) good_response ERROR: boolean not returnd from dwif-lab-adv-openai-FY25-v1')
 
         # this is just the answer from the LLM
        try:
            answer = response_paylaod["response_text"]
        except:
            answer = ""
            print(f'({current_intent}) response_paylaod ERROR:  {response_paylaod}')
        
        # # these are the follow-on-questions that the LLM provided based on the context and current question
        # try:
        #     foqs = response_paylaod["foqs"]
        # except:
        #     foqs = ""
            
        # print(f'({current_intent}) foqs from payload: {foqs}')
        
        # # store the follow-on-questions in session attributes so they can be retrieved if needed
        # session_attributes['foqs'] = json.dumps(foqs)

        return answer, good_response
    
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #-------------------------------------------------------- Call OLD OpenAI  -------------------------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def makeAIcall_OLD(q1, q2, q3, query, userDetailPayload, type_of_questionSlots, current_intent, sessionId):
        
        qs = get_queries()

        # format the query for input
        input_params = {
            "current_intent": current_intent,
            "q1": q1,
            "q2": q2,
            "q3": q3,
            "query": query,
            "index": type_of_questionSlots,
            "userDetailPayload": userDetailPayload,
            "channel": "Voice",
            "sessionId": sessionId
        }    

        # define thresholds for the called function
        lambdaCfg = botocore.config.Config(
            retries = {'max_attempts': 0},
            read_timeout = 1840,
            connect_timeout = 1600
        )
    
        # Create the boto3 object that allows the interaction with other Lambda functions
        lambda_client_obj = boto3.client('lambda', config=lambdaCfg)

        ####################################################
        # call the Lambda function that calls Azure OpenAI
        ####################################################
        lambdaResponse = lambda_client_obj.invoke(
            FunctionName='arn:aws:lambda:us-east-1:730335323965:function:dwiflab_azure_corp_ai',
            InvocationType='RequestResponse',
            Payload=json.dumps(input_params)
        )
    
        ####################################################
        # Retrieve the Azure OpenAI result
        ####################################################

        response_paylaod = json.loads(lambdaResponse['Payload'].read().decode('utf-8'))

        ####################################################
        # Return the result to Lex
        ####################################################
        return response_paylaod

    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #------------------------------------------ Generate a Sentiment Table -------------------------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def getSentiment(interpretations):

        sentiment          = ''
        nluConfidence      = ''
        sentimentRating    = ''

        for key in interpretations:
            if key["intent"]["name"] == current_intent:
                try:
                    nluConfidence       = key['nluConfidence']
                except:
                    nluConfidence       = 'not defined'

                try:
                    sentiment           = key['sentimentResponse']['sentiment']
                except:
                    sentiment           = 'not defined'

                if sentiment == 'not defined':
                    nluConfNeurtal      = 'nluConfNeurtal Not defined'
                    nluConfNeutralPcnt  = 0
                    nluConfMixed        ='nluConfMixed Not defined'
                    nluConfMixedPcnt    = 0
                    nluPositive         = 'nluPositive Not defined'
                    nluConfPositivePcnt = 0
                    nluNegative         = 'nluNegative Not defined'
                    nluConfNegativePcnt = 0
                else:
                    nluConfNeurtal      = key['sentimentResponse']['sentimentScore']['neutral']
                    nluConfNeutralPcnt  = round((nluConfNeurtal/1)*100)
                    nluConfMixed        = key['sentimentResponse']['sentimentScore']['mixed']
                    nluConfMixedPcnt    = round((nluConfMixed/1)*100)
                    nluPositive         = key['sentimentResponse']['sentimentScore']['positive']
                    nluConfPositivePcnt = round((nluPositive/1)*100)
                    nluNegative         = key['sentimentResponse']['sentimentScore']['negative']
                    nluConfNegativePcnt = round((nluNegative/1)*100)

                
        nluSentimentTotal  = nluConfNeurtal + nluConfMixed + nluPositive + nluNegative

        # an array of responses for detected "Negative" setiment.  Add new phrases to the end starting with a comma (needs to be JSON formatted)
        negative_sentiment_responses = [
            "Sounds stressful. Let's try to make things better.",
            "Tough topic. I'm here to assist you.",
            "You're not alone.",
            "I understand.",
            "Let's work through this together.",
            "I'm sorry you're going through this. Let's work on resolving it.",
            "Thanks for sharing.",
            "That sounds really hard. I'm here to make things right.",
            "I'm sorry if you're having issues. I'm here to help.",
            "My apologies if your productivity is getting impacted today. I'm here to assist you."
        ]
    
        # an array of responses for detected "Neutral" setiment.  Add new phrases to the end starting with a comma (needs to be JSON formatted)
        neutral_sentiment_responses = [
            "Ok.",
            "Got it.",
            "Let's see.",
            "Alright."
        ]
    
        # an array of responses for detected "Mixed" setiment.  Add new phrases to the end starting with a comma (needs to be JSON formatted)
        mixed_sentiment_responses = [
            "Let's get you what you need!"
        ]

        # an array of responses for detected "Positive" setiment.  Add new phrases to the end starting with a comma (needs to be JSON formatted)
        positive_sentiment_responses = [
            "Let's keep it going!"
        ]

        generalSentimentStatement = ''
        i = 1
        if sentiment == 'NEGATIVE':
            sentimentRating  = nluConfNegativePcnt
            generalSentimentStatement = random.choice(negative_sentiment_responses)
            #sentimentRanking = f'<img src="/images/bootstrap/emoji-frown-fill.svg" title="{sentiment}" /> {sentimentRating}% <i>{sentiment.lower()}</i>'
        elif sentiment == 'NEUTRAL':
            generalSentimentStatement = random.choice(neutral_sentiment_responses)
            sentimentRating  = nluConfNeutralPcnt
            #sentimentRanking = f'<img src="/images/bootstrap/emoji-neutral-fill.svg" title="{sentiment}" /> {sentimentRating}% <i>{sentiment.lower()}</i>'
        elif sentiment == 'MIXED':
            generalSentimentStatement = random.choice(mixed_sentiment_responses)
            sentimentRating  = nluConfMixedPcnt
            #sentimentRanking = f'<img src="/images/bootstrap/emoji-neutral-fill.svg" title="{sentiment}" /> {sentimentRating}% <i>{sentiment.lower()}</i>'
        elif sentiment == 'POSITIVE':
            generalSentimentStatement = random.choice(positive_sentiment_responses)
            sentimentRating  = nluConfPositivePcnt
            #sentimentRanking = f'<img src="/images/bootstrap/emoji-smile-fill.svg" title="{sentiment}" /> {sentimentRating}% <i>{sentiment.lower()}</i>'
    
        if verbose == "True":
            print(f'({current_intent}) sentiment: {sentiment} | nluConfidence: {nluConfidence} | nluConfNeurtal: {nluConfNeurtal}({nluConfNeutralPcnt}%) | nluConfMixed: {nluConfMixed}({nluConfMixedPcnt}%) | nluPositive: {nluPositive}({nluConfPositivePcnt}%) | nluNegative: {nluNegative}({nluConfNegativePcnt}%) | nluSentimentTotal: {nluSentimentTotal})')

        if verbose == 'True':
            print(f'({current_intent}) : ***************************************************************************************************************')
            print(f'({current_intent}) : ******************* Print Execution Variables *****************************************************************')
            print(f'({current_intent}) : ***************************************************************************************************************')
            print(f'({current_intent}) : json event:         {json.dumps(event)}')
            print(f'({current_intent}) : session_attributes: {session_attributes}')
            print(f'({current_intent}) : inputMode:          {inputMode}')
            print(f'({current_intent}) : current_intent:     {current_intent}')
            print(f'({current_intent}) : slots:              {json.dumps(slots)}')
            print(f'({current_intent}) : sentiment:          {sentiment} | nluConfidence: {nluConfidence} | nluConfNeurtal: {nluConfNeurtal}({nluConfNeutralPcnt}%) | nluConfMixed: {nluConfMixed}({nluConfMixedPcnt}%) | nluPositive: {nluPositive}({nluConfPositivePcnt}%) | nluNegative: {nluNegative}({nluConfNegativePcnt}%) | nluSentimentTotal: {nluSentimentTotal})')
            print(f'({current_intent}) : ***************************************************************************************************************')

        return generalSentimentStatement, sentiment, sentimentRating #, sentimentRanking
    
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #--------------------------------------- Record feedback, sentiment, etc.,.. in ServiceNow  ----------------------------------------------#
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
                print(f"({current_intent}) JSONDecodeError: {e}")
                queries = []
        else:
            queries = []
            
        for i, question in enumerate(queries):
            query_json[f"q{i+1}"] = question

        return query_json
    
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    #--------------------------------------- Determine if a topic changes has been requested -------------------------------------------------#
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    def contains_new_topic_variation(lex_input):
        for variation in new_topic_variations:
            if variation in lex_input:
                return True
        return False     
        
    #-----------------------------------------------------------------------------------------------------------------------------------------#
    # END FUNCTION DEFINITION ### END FUNCTION DEFINITION ### END FUNCTION DEFINITION ### END FUNCTION DEFINITION ### END FUNCTION DEFINITION #
    #-----------------------------------------------------------------------------------------------------------------------------------------#

    #-----------------------------------------------------------------------------------------------------------------------------
    #------------------------------ BEGIN ENVRIONMENT VARIABLES ------------------------------------------------------------------
    #-----------------------------------------------------------------------------------------------------------------------------
    
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

    # get value that indicates "Text" or "Voice"
    inputMode        = event['inputMode']

    if verbose == "True":
        print(f'({current_intent}) inputMode: {inputMode}')

    slots              = event['sessionState']['intent']['slots']
    invocationSource   = event['invocationSource']

    sessionId    = event['sessionId']

    # capture details about the bot used
    botName      = event['bot']['name']
    botVersion   = event['bot']['version']
    botAliasID   = event['bot']['aliasId']
    botAliasName = event['bot']['aliasName']
    
    botInfo = f'Lex BOT details | Name: {botName} | Version: {botVersion} | Alias ID: {botAliasID} | Alias Name: {botAliasName}'

    if verbose == "True":
        print(f'({current_intent}) sessionId: {sessionId}')
    
    session_attributes = event['sessionState']['sessionAttributes']
    
    print(f'({current_intent}) session_attributes: json.dumps({session_attributes})')

    lex_input           = event['inputTranscript']
    if verbose == "True":
        print(f'({current_intent}) lex_input: {lex_input}')
    
    interpretations     = event['interpretations']
    
    # {'PhoneNumber': '8 4 3 , 3 6 4 , 5 7 2 9', 'LastName': 'Sabados', 'FirstName': 'Joseph', 'EmailAddress': 'joseph.b.sabados@saic.com'}
    # PhoneNumber is formated this way so Lex will not interpret it when read back to the user as a single integer but rather speaks each individual numbers
    sessionPhoneNumber  = session_attributes['PhoneNumber']

    # Remove spaces and commas
    cleanedSessionNumber= sessionPhoneNumber.replace(" ", "").replace(",", "")

    # Format the number with hyphens
    connectPhoneNumber  = cleanedSessionNumber[:3] + "-" + cleanedSessionNumber[3:6] + "-" + cleanedSessionNumber[6:]

    connectFirstName    = session_attributes['FirstName']
    connectEmailaddress = session_attributes['EmailAddress']

    userDetailPayload = {
        'userIdSlot':       connectEmailaddress,
        'providerName':     '',
        'providerType':     '',
        'issuer':           '',
        'emailSlot':        connectEmailaddress,
        'family_nameSlot':  '',
        'given_nameSlot':   connectFirstName,
        'phone_numberSlot': connectPhoneNumber,
        'exp':              '',
        'sessionId':        sessionId
    }

    if verbose == "True":
        print(f'({current_intent}) userDetailPayload: {userDetailPayload}')

    #-----------------------------------------------------------------------------------------------------------------------------
    #------------------------------ END ENVRIONMENT VARIABLES --------------------------------------------------------------------
    #-----------------------------------------------------------------------------------------------------------------------------

    #-------------------------------------- Get the users current sentiment ------------------------------------------------------
    generalSentimentStatement, sentiment, sentimentRating = getSentiment(interpretations)

    # check for bad sentiment and redirect to an agent right here.
    
    # if decent sentiment, check intents

    if current_intent != "Gather_feedback":

        # check to see how bad the sentiment is and if too bad, automatically transfer the caller to an agent with the appropriate response
        
        ## IMPORTANT ##
        
        # The next line will allow you to dial-up or dial-down the level at which the auto-transfer will occur.  If you want it to transfer easier, down the default value
        # of 85 to something less but greater than 0.  To make the transfer harder, dial up the default value from 85 to a number < 100 but > the default 85.
        #
        # For example:
        #      
        #       if you want all and any negative detection to auto-route, change the sentimentRating to 1
        #
        #       if you want to make it nearly impossible to auto-route, change the sentimentRating to 99
        
        ## 
        if (sentiment == 'NEGATIVE') and (int(sentimentRating) > 85):
            
            inputPayload = {
                "user":              connectEmailaddress,
                "channel":           'Voice',
                "lex_input":         lex_input,
                "intent":            current_intent,
                "sentiment_rating":  sentimentRating,
                "sentiment":         sentiment
            }
    
            # record the poor sentiment
            recordResults(userDetailPayload, lambda_client_obj, 'x_saic4_dwif_ai_kn_pilot_sentiment', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'Event')

            Agent = {
                'shape': 'Scalar',
                'value': {
                    'originalValue': None,
                    'resolvedValues': None,
                    'interpretedValue': 'Yes'
                }
            }
            
            slots['Agent'] = Agent
    
            transferResponse = {
                'sessionState': {
                    'dialogAction': {
                        'type': 'Close'
                    },
                    'intent': {
                        'confirmationState': 'None',
                        'name': "AgentIntent",
                        'state': 'Fulfilled',
                        'slots': slots
                    }
                },
                'messages': [
                    {
                        'contentType': 'PlainText',
                        'content': f"{generalSentimentStatement}"
                    }
                ]
            }

            return transferResponse

    #------------------------- Before the check for intents, see if there's a request to start a new topic -------------------------

    # the following array is a list of sub-strings that, if found in the lex input, will trigger a change in topic regardless of current intent.  This is because the 
    # logic for asking questions is a loop that will not allow you to break out unless you answer "No" to a question...
    
    new_topic_variations = ["quit", "stop", "home", "change topic", "new topic", "something else", "move on", "another subject", "change subject", "another topic"]
    
    if contains_new_topic_variation(lex_input):
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
                    'contentType': 'PlainText',
                    'content': f'Sure!  All set!'
                 }
            ]
        }
        
        return NewTopicResponse

    #------------------------- Before the check for intents, see if there's has failed to enter anything -------------------------

    # When the bot 
    # logic for asking questions is a loop that will not allow you to break out unless you answer "No" to a question...
    user_input = lex_input.strip()
    
    if not user_input and current_intent == "FallbackIntent":
        varied_responses = ["Are you still there?", "I'm waiting for a question.", "Still waiting.", "Ask me a question or give me a command."]
        
        print(f'({current_intent}) lex_input is empty so remind the user to provide some input')
        response = {
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
                    'content': random.choice(varied_responses)
                 }
            ]
        }
        
        return response

    #-----------------------------------------------------------------------------------------------------------------------------
    #------------------------------ BEGIN Specific Intent Processing  ------------------------------------------------------------
    #-----------------------------------------------------------------------------------------------------------------------------

    if current_intent == 'TicketCreate':
        #--------------------------------------------------------------------------------------------#
        #------------- TicketCreate Intent ----------------------------------------------------------#
        #--------------------------------------------------------------------------------------------#

        ShortDescription  = slots['ShortDescription']['value']['interpretedValue']
        AdditionalDetails = slots['AdditionalDetails']['value']['interpretedValue']

        inputPayload = {
            "impact":               "2",
            "urgency":              "2",
            "caller_id":            connectEmailaddress,
            "short_description":    ShortDescription,
            "description":          AdditionalDetails,
            "work_notes":           f'Incident created from AWS Connect via AWS Lambda.  {botInfo}',
            "assignment_group":     "Service Desk",
            "sys_class_name":       "incident",
            "contact_type":         "AWS Lex",
            "category":             "Enterprise Customer Service",
            "subcategory":          "AI-Chatbot"
        }
        
        IncidentNumber = recordResults(userDetailPayload, lambda_client_obj, 'incident', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'RequestResponse')

        print(f'({current_intent}) IncidentNumber: {IncidentNumber}')

        contentBack = f"I've created Incident {IncidentNumber} regarding your issue."
        print(f'({current_intent}) contentBack {contentBack}')

        # Build the JSON response array to Lex
        incidentResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'intent': {
                    'name': current_intent,
                    'state': 'Fulfilled'
                }
            },
            'messages': [
                {
                    'contentType': 'PlainText',
                    'content': contentBack
                }
            ]
        }

        return incidentResponse

    elif current_intent == "Gather_feedback":
        #--------------------------------------------------------------------------------------------#
        #------------- Get feedback from the pilot participants -------------------------------------#
        #--------------------------------------------------------------------------------------------#
        inputPayload = {
            "user":     connectEmailaddress,
            "channel":  'Voice',
            "feedback": lex_input
        }

        recNo = recordResults(userDetailPayload, lambda_client_obj, 'x_saic4_dwif_ai_kn_pilot_feedback', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'Event')
        
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
                    "contentType": "PlainText",
                    "content": f"Thank you for your feedback! It will be evaluated by our team for action.  Now, let's get more answers."
                }
            ]
        }

        return feedback_payload

    elif current_intent == "FallbackIntent":
        #--------------------------------------------------------------------------------------------#
        #-------------------------------- Fallbackintent Intent -------------------------------------#
        #--------------------------------------------------------------------------------------------#
 
        # lex_input at this point will be the question asked by the user...
        print(f'({current_intent}) : lex_input: {lex_input}')

        ai_question = {
            'shape': 'Scalar',
            'value': {
                'originalValue': None,
                'resolvedValues': None,
                'interpretedValue': lex_input
            }
        }

        answerQuestionYesNo = None

        slots['ai_question']         = ai_question
        slots['answerQuestionYesNo'] = answerQuestionYesNo
        print(f'({current_intent}) slots: {slots}')
    
        fallbackResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'ElicitSlot',
                    'slotToElicit': 'answerQuestionYesNo'
                },
                'intent': {
                    'confirmationState': 'None',
                    'name': "I_have_a_question",
                    'state': 'InProgress',
                    'slots': slots
                },
                'sessionAttributes': session_attributes
            },
            'messages': [
                {
                    'contentType': 'PlainText',
                    'content': f"{generalSentimentStatement} You want to know, {lex_input.replace('?','')}, right?  Yes or No."
                }
            ]
        }

        return fallbackResponse

    elif current_intent == "AI_FallbackIntent":
        #--------------------------------------------------------------------------------------------#
        #-------------------------------- AI_FallbackIntent Intent -------------------------------------#
        #--------------------------------------------------------------------------------------------#
 
        # lex_input at this point will be the question asked by the user...
        print(f'({current_intent}) : lex_input: {lex_input}')

        ai_question = {
            'shape': 'Scalar',
            'value': {
                'originalValue': None,
                'resolvedValues': None,
                'interpretedValue': lex_input
            }
        }

        answerQuestionYesNo = None

        slots['ai_question']         = ai_question
        slots['answerQuestionYesNo'] = answerQuestionYesNo
        print(f'({current_intent}) slots: {slots}')
    
        AIfallbackResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'ElicitSlot',
                    'slotToElicit': 'answerQuestionYesNo'
                },
                'intent': {
                    'confirmationState': 'None',
                    'name': "I_have_a_question",
                    'state': 'InProgress',
                    'slots': slots
                },
                'sessionAttributes': session_attributes
            },
            'messages': [
                {
                    'contentType': 'PlainText',
                    'content': f"{generalSentimentStatement} You want to know, {lex_input.replace('?','')}, right?  Yes or No."
                }
            ]
        }

        return AIfallbackResponse
        
    ###########################################################################################################################################
    ### I_have_a_question Intent
    ###########################################################################################################################################
    elif current_intent == "I_have_a_question":

        # get the question passed into this intent by the Fallbackintent
        ai_question_slot = slots['ai_question']['value']['interpretedValue']
        
        # Adjust the question so it can better be read back by Lex
        adjusted_ai_question_slot = ai_question_slot.replace('?','')
        
        # this is the interpreted answer to the Y/N question.  It should also mimic the {lex_input} variable at this point
        try:
            ynSlotValue = slots['answerQuestionYesNo']['value']['interpretedValue']
        except:
            ynSlotValue = 'not defined yet'
            
        if verbose == "True":
            print(f'({current_intent}) ynSlotValue: {ynSlotValue}')
            print(f'({current_intent}) invocationSource = {invocationSource}')
            
            
        if ynSlotValue == 'Yes':
        ############################### DO RAG Start #################################################
        ############################### DO RAG Start #################################################
        ############################### DO RAG Start #################################################

            # Make the OpenAI call
            AIOutput_answer, good_response = makeAIcall(ai_question_slot, userDetailPayload, lambda_client_obj, current_intent, sessionId)
            
            if verbose == "True":
                print(f'({current_intent}) AIOutput_answer: {AIOutput_answer}')
                print(f'({current_intent}) good_response: {good_response}')
            
            if good_response == "False":
                # if you don't get a good answer back you probably need to move to a new topic. This keeps the bad question from getting
                # included in the RAG
                email_blurb = ""
            else:
                email_blurb = "Check your email for the full response and reference details."
            
            # add most recent question to the custom attributes to be included in the RAG
            new_items = json.loads(session_attributes.get('queries', '[]'))
            new_items.append(ai_question_slot)
            session_attributes['queries'] = json.dumps(new_items)
    
            queries = json.loads(session_attributes['queries'])
    
            # check for the number of previous quesitons.  If it exceeds 5, let's let them know this is the last time before the topic
            # is required to be changed.
            
            number_of_items = len(queries)
            
            if verbose == "True":
                print(f'({current_intent}) number_of_items: {number_of_items}')
            
            slots['answered'] = {
                "value": {
                    "interpretedValue": None
                }
            }
            
            if good_response == "False":
                # We got a bad answer so we may have reached the end of the context capacity, so clear the existing queries so they're not inclduded in the next questions and indicate that the topic is witching

                if verbose == "True":
                    print('({current_intent}) good_response == "False"')
               
                clear_queries()
                new_topic_message = f"We're going to start a new topic. What else would you like to know?"
                payload =  {
                    "sessionState": {
                        "dialogAction": {
                            "type": "Close"
                        },
                        "intent": {
                            "name": current_intent,
                            "state": "Fulfilled",
                            "slots": slots
                        },
                        "sessionAttributes": session_attributes
                    },
                    "messages": [
                        {
                            "contentType": "PlainText",
                            "content": f'{AIOutput_answer} {new_topic_message}'
                        }
                    ]
                }
            elif number_of_items > 5:
               # We've reached the end of the context capacity, so clear the existing queries so they're not inclduded in the next questions and indicate that the topic is witching
                
                if verbose == "True":
                    print("({current_intent}) number_of_items > 5")
                    
                clear_queries()
                new_topic_message = f"Starting a new topic: We've covered a lot! What else would you like to know?"
                payload =  {
                    "sessionState": {
                        "dialogAction": {
                            "type": "Close"
                        },
                        "intent": {
                            "name": current_intent,
                            "state": "Fulfilled",
                            "slots": slots
                        },
                        "sessionAttributes": session_attributes
                    },
                    "messages": [
                        {
                            "contentType": "PlainText",
                            "content": f'{AIOutput_answer} {email_blurb} {new_topic_message}'
                        }
                    ]
                }
            else:
                # Bounce to a new Intent that will capture whether the answer was appropriate...
                
                if verbose == "True":
                    print(f"({current_intent}) number_of_items: {number_of_items} | good_response: {good_response}")
                    
                # new_topic_message = ""
                # payload =  {
                #     "sessionState": {
                #         "dialogAction": {
                #             "type": "Close"
                #         },
                #         "intent": {
                #             "name": current_intent,
                #             "state": "Fulfilled",
                #             "slots": slots
                #         },
                #         "sessionAttributes": session_attributes
                #     },
                #     "messages": [
                #         {
                #             "contentType": "PlainText",
                #             "content": f"{AIOutput_answer} {email_blurb} Did this answer your question?  Please response Yes or No before continuing so we can track how we're doing."
                #         }
                #     ]
                # }

                payload = {
                    'sessionState': {
                        'dialogAction': {
                            'type': 'ElicitSlot',
                            'slotToElicit': 'answered'
                        },
                        'intent': {
                            'confirmationState': 'None',
                            'name': "Did_I_answer_your_question",
                            'state': 'InProgress'
                        },
                        'sessionAttributes': session_attributes
                    },
                    'messages': [
                        {
                            'contentType': 'PlainText',
                            'content': f"{AIOutput_answer} {email_blurb} Did this answer your question?  Please respond Yes or No before continuing so we can track how we're doing."
                        }
                    ]
                }
                
                print(f'({current_intent}) payload: {payload}')
                return payload
                
        elif ynSlotValue == 'No':
            # If the user reached this, they were not happy with the way NLU determined what they wanted to ask.  In other words, what they asked was not understood and the read-back
            # to the user identified it was the wrong question (e.g, "where is my home?" was interpreted as "where do i hone?").  So, this offers the user opportunity to ask the question
            # again without wasting time and an AI response 
            
            payload =  {
                "sessionState": {
                    "dialogAction": {
                        "type": "Close"
                    },
                    "intent": {
                        "name": current_intent,
                        "state": "Fulfilled",
                        "slots": slots
                    },
                    "sessionAttributes": session_attributes
                },
                "messages": [
                    {
                        "contentType": "PlainText",
                        "content": f"Ok. "
                    }
                ]
            }
            
        #else:
             # 
            
        return payload

    elif current_intent == "Did_I_answer_your_question":
        #-----------------------------------------------------------------------------------------------------------------------------------------#
        #---------------- validation that the response provided to the user actually answered the question asked. --------------------------------#
        #-----------------------------------------------------------------------------------------------------------------------------------------#

        if verbose == "True":
            print(f'({current_intent}) lex_input: {lex_input}')
        # in the future use a privately deploy NLP or GTP to evalute input to determin real topic/intent

        yes_variations = ["it did", "it did!", "yes", "yes sir!", "sure", "of course", "sure did", "yep, it sure did", "yep sure did", "yep it sure did","it sure did", "yep", "yep it did","yep, it did","yeah", "yes sir", "yes it did","yes, it did","oh yeah", "yes!", "yes, thank you", "yes thank you"]
        no_variations  = ["it didn't", "it did not", "no", "no, it didn't","nope", "no sir", "no it did not", "no it didn't", "not really", "sort of","not a chance"]
    
        if lex_input.strip() == '':
            normalized_input = "blank"
        elif lex_input.lower() in yes_variations:
            normalized_input = "Yes"
        elif lex_input.lower() in no_variations:
            normalized_input = "No"
        else:
            normalized_input = "Unknown"
            
        print(f'({current_intent}) normalized_input: {normalized_input}')
        
        # slots['answered'] = {
        #     "value": {
        #         "interpretedValue": normalized_input
        #     }
        # }
        
        # if the answer is ultimately "no", retrieve FOQ's from session attributes "queries" array and use those to build the buttons.
        
        # ai_question = {
        #     'shape': 'Scalar',
        #     'value': {
        #         'originalValue': None,
        #         'resolvedValues': None,
        #         'interpretedValue': lex_input
        #     }
        # }

        answerQuestionYesNo = normalized_input

        #slots['ai_question'] = ai_question
        slots['answerQuestionYesNo'] = answerQuestionYesNo
        print(f'({current_intent}) slots: {slots}')
        
        # record the disatisfaction
        inputPayload = {
            "user":      connectEmailaddress,
            "channel":   'voice',
            "queries":   get_queries(),
            "sessionid": sessionId,
            "thumb_orientation": "up"
        }
        recordResults(userDetailPayload, lambda_client_obj, 'x_saic4_dwif_ai_kn_pilot_not_helpful_feedback', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'Event')

        if normalized_input == "Yes": 
            
            answeredResponse = {
                'sessionState': {
                    'dialogAction': {
                        'type': 'ElicitSlot',
                        'slotToElicit': 'ai_question'
                    },
                    'intent': {
                        'confirmationState': 'None',
                        'name': "AI_FallbackIntent",
                        'state': 'InProgress'
                    },
                    'sessionAttributes': session_attributes
                },
                'messages': [
                    {
                        'contentType': 'PlainText',
                        'content': f"Great!  Ask another question."
                    }
                ]
            }
            
        elif normalized_input == "No":
            # record the disatisfaction
            inputPayload = {
                "user":      connectEmailaddress,
                "channel":   'voice',
                "queries":   get_queries(),
                "sessionid": sessionId,
                "thumb_orientation": "down"
            }
            recordResults(userDetailPayload, lambda_client_obj, 'x_saic4_dwif_ai_kn_pilot_not_helpful_feedback', 'POST', instance, itsm_account, itsm_account_pwd, inputPayload, 'Event')

            # if the answer is ultimately "no", retrieve FOQ's from session attributes "foqs" array and use those to build the buttons.
            clear_queries()

            new_topic_message = f"I'm very sorry that wasn't sufficient.  I'm starting a new topic so you can try again.  Please ask a question."
            answeredResponse = {
                'sessionState': {
                    'dialogAction': {
                        'type': 'ElicitSlot',
                        'slotToElicit': 'ai_question'
                    },
                    'intent': {
                        'confirmationState': 'None',
                        'name': "AI_FallbackIntent",
                        'state': 'InProgress'
                    },
                    'sessionAttributes': session_attributes
                },
                'messages': [
                    {
                        'contentType': 'PlainText',
                        'content': f"{new_topic_message}"
                    }
                ]
            }
        elif normalized_input == "Unknown":
            # if the answer is ultimately "unknown", reprompt for a "yes" or "no" response.
            answeredResponse =  {
                "sessionState": {
                    "dialogAction": {
                        "type": "ElicitSlot",
                        "slotToElicit": "answered"
                    },
                    "intent": {
                        "name": "Did_I_answer_your_question",
                        "state": "InProgress"
                    },
                    "sessionAttributes": session_attributes
                },
                "messages": [
                    {
                        "contentType": "PlainText",
                        "content": f"I'm sorry but I can't determine if I answered your question or not.  Can you please give me a Yes or a No?" 
                    }
                ]
            }
        elif normalized_input == "blank":
            answeredResponse =  {
                "sessionState": {
                    "dialogAction": {
                        "type": "ElicitSlot",
                        "slotToElicit": "answered"
                    },
                    "intent": {
                        "name": "Did_I_answer_your_question",
                        "state": "InProgress"
                    },
                    "sessionAttributes": session_attributes
                },
                "messages": [
                    {
                        "contentType": "PlainText",
                        "content": f"I'm waiting for your response.  Please answer Yes or No before continuing." 
                    }
                ]
            }
            
        print(f'({current_intent}) answeredResponse: {answeredResponse}')
        
        return answeredResponse

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
                    'contentType': 'PlainText',
                    'content': f'Sure!  All set!'
                 }
            ]
        }
        
        return NewTopicResponse
    
    elif current_intent == "AgentIntent":
        transferResponse = {
            'sessionState': {
                'dialogAction': {
                    'type': 'Close'
                },
                'intent': {
                    'confirmationState': 'None',
                    'name': "AgentIntent",
                    'state': 'Fulfilled',
                    'slots': slots
                }
            },
            'messages': [
                {
                    'contentType': 'PlainText',
                    'content': f"{generalSentimentStatement}"
                }
            ]
        }

        return transferResponse        