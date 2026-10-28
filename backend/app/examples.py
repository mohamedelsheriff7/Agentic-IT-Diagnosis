"""Documented request examples; IDs returned by earlier calls must be substituted."""
EXAMPLES={
'create_ticket':{'action_id':'create-demo-001','summary':'Cannot sign in','description':'The portal rejects my sign-in.','reported_by_id':'USR-001'},
'search_similar_tickets':{'description':'password expired sign in','limit':5},
'assign_ticket':{'action_id':'assign-demo-001','resolver_group_id':'GRP-APP','confidence':'HIGH','reason':'Only the application fails; identity checks are healthy.','alternative_resolver_group_ids':['GRP-IAM'],'evidence_ids':[]},
'add_worklog_entry':{'action_id':'note-demo-001','entry_type':'QUESTION','summary':'Do other applications work?','rationale':'Discriminate shared identity from app-specific failure.'},
'resolve_ticket':{'action_id':'resolve-demo-001','diagnosis_code':'PASSWORD_EXPIRED','resolution_summary':'User completed self-service change and confirmed successful sign-in.','steps_completed':['PASSWORD_EXPIRED-1'],'knowledge_article_id':'KB-001','user_confirmed_success':True,'evidence_ids':['EV-from-account-check']},
'count_recent_tickets':{'category':'VPN','configuration_item_id':'CI-VPN','location_id':'LOC-A','window_minutes':30},
'find_open_global_tickets':{'category':'VPN','configuration_item_id':'CI-VPN','location_id':'LOC-A'},
'create_global_ticket':{'action_id':'outage-demo-001','summary':'VPN unavailable at site A','description':'Three affected synthetic users within 30 minutes.','severity':'SEV2','category':'VPN','configuration_item_id':'CI-VPN','location_id':'LOC-A','owner_group_id':'GRP-NET','related_ticket_ids':['CLUSTER-1-1','CLUSTER-1-2'],'reason':'Cluster and independent health observation support outage investigation.'},
'link_ticket_to_global_ticket':{'action_id':'link-demo-001','global_ticket_id':'GLB-from-create','reason':'Same service, category and site.'},
'check_account_status':{'action_id':'account-demo-001','ticket_id':'INC-1001','user_id':'USR-001'},
'check_application_entitlement':{'action_id':'entitlement-demo-001','ticket_id':'INC-1004','user_id':'USR-004','application_id':'APP-PORTAL','required_role':'USER'},
'check_service_health':{'action_id':'health-demo-001','ticket_id':'CLUSTER-1-1','configuration_item_id':'CI-VPN','location_id':'LOC-A'},
'request_human_review':{'action_id':'review-demo-001','reason':'Insufficient evidence to diagnose safely.','review_type':'INVESTIGATION','suggested_group_id':'GRP-L1'},
'notify_resolver_group':{'action_id':'notify-demo-001','resolver_group_id':'GRP-NET','severity':'SEV2','message':'Synthetic VPN outage investigation requested.'},
'search_diagnostic_knowledge':{'query':'password expired','limit':5},
'record_diagnostic_result':{'action_id':'diagnosis-demo-001','diagnosis_code':'PASSWORD_EXPIRED','outcome':'DIAGNOSED','candidate_diagnoses':[{'diagnosis_code':'PASSWORD_EXPIRED','reason':'Expiry observation with active unlocked account.'}],'eliminated_diagnoses':[{'diagnosis_code':'ACCOUNT_LOCKED','reason':'Account check reports unlocked.'}],'evidence_ids':['EV-from-account-check'],'knowledge_article_ids':['KB-001'],'confidence':'HIGH','confidence_basis':{'knowledge_match_strength':'HIGH','evidence_completeness':'HIGH','historical_agreement':'NOT_AVAILABLE','alternatives_excluded':True},'recommended_action':'RESOLVE','missing_information':[],'rationale':'User response and recorded account evidence agree.'}}


def enrich(spec):
    for methods in spec['paths'].values():
        for operation in methods.values():
            example=EXAMPLES.get(operation.get('operationId'))
            if example and 'requestBody' in operation:
                operation['requestBody']['content']['application/json']['example']=example
    return spec
