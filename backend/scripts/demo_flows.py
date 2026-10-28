"""Four fixed integration demonstrations, not a Diagnostic Agent. Run after fresh import."""
import os
from uuid import uuid4
import httpx
from app.examples import EXAMPLES


def run_flows(client):
    def post(path,body,write=True):
        payload=dict(body)
        if write: payload['action_id']='demo-'+uuid4().hex
        response=client.post(path,json=payload);response.raise_for_status();return response.json()
    # 1. Ambiguous access issue: record a discriminating question and caller-supplied answer.
    post('/tickets/INC-1001/worklogs',EXAMPLES['add_worklog_entry'])
    post('/tickets/INC-1001/worklogs',dict(entry_type='EVIDENCE',summary='User reports expiry error',rationale='User assertion, corroborated by stored account check',evidence=[dict(source_type='USER_RESPONSE',source_id='USR-001',observation='Other applications fail too; the message says password expired.')]))
    evidence=post('/diagnostics/account-status',EXAMPLES['check_account_status'])['evidence_id']
    d=dict(EXAMPLES['record_diagnostic_result'],evidence_ids=[evidence])
    post('/tickets/INC-1001/diagnostic-results',d)
    resolved=post('/tickets/INC-1001/resolution',dict(EXAMPLES['resolve_ticket'],evidence_ids=[evidence]))
    assert resolved['status']=='RESOLVED'
    # 2. App-specific auth issue; checks are observations, conclusion is an explicit demo assertion.
    account=post('/diagnostics/account-status',dict(ticket_id='INC-1005',user_id='USR-005'))
    entitlement=post('/diagnostics/application-entitlement',dict(ticket_id='INC-1005',user_id='USR-005',application_id='APP-PORTAL'))
    health=post('/diagnostics/service-health',dict(ticket_id='INC-1005',configuration_item_id='CI-PORTAL',location_id='LOC-A'))
    d=dict(EXAMPLES['record_diagnostic_result'],diagnosis_code='APP_AUTH_FAILURE',candidate_diagnoses=[],eliminated_diagnoses=[],recommended_action='ROUTE',knowledge_article_ids=['KB-005'],evidence_ids=[account['evidence_id'],entitlement['evidence_id'],health['evidence_id']],rationale='App fails while other applications work; specialist investigation is appropriate.')
    post('/tickets/INC-1005/diagnostic-results',d)
    assignment=post('/tickets/INC-1005/assignment',dict(EXAMPLES['assign_ticket'],evidence_ids=d['evidence_ids']))
    assert assignment['assigned_group_id']=='GRP-APP'
    # 3. Vague Arabic description: ask, record uncertainty, request a human.
    post('/tickets/INC-1012/worklogs',dict(entry_type='QUESTION',summary='ما هو التطبيق وما هي رسالة الخطأ؟',rationale='الوصف الحالي لا يكفي للتشخيص'))
    d=dict(EXAMPLES['record_diagnostic_result'],diagnosis_code=None,outcome='INCONCLUSIVE',candidate_diagnoses=[],eliminated_diagnoses=[],evidence_ids=[],knowledge_article_ids=[],confidence='LOW',recommended_action='ASK_MORE',missing_information=['اسم التطبيق ورسالة الخطأ'],rationale='لا توجد أدلة كافية')
    post('/tickets/INC-1012/diagnostic-results',d)
    review=post('/tickets/INC-1012/human-reviews',EXAMPLES['request_human_review'])
    assert review['state']=='REQUESTED'
    # 4. VPN burst: count, independently observe, create/reuse, then link a later arrival.
    count=post('/tickets/count-recent',EXAMPLES['count_recent_tickets'],False)
    assert count['count']==3
    observed=post('/diagnostics/service-health',EXAMPLES['check_service_health'])
    issue=post('/global-tickets',dict(EXAMPLES['create_global_ticket'],evidence_ids=[observed['evidence_id']]))
    post('/tickets/CLUSTER-1-3/global-link',dict(global_ticket_id=issue['ticket_id'],reason='Same scope; later-arriving report.'))
    assert post('/tickets/count-recent',EXAMPLES['count_recent_tickets'],False)['count']==0
    post('/tickets/'+issue['ticket_id']+'/notifications',EXAMPLES['notify_resolver_group'])
    return {'resolved_ticket':resolved['ticket_id'],'specialist_group':assignment['assigned_group_id'],'arabic_review':review['review_id'],'vpn_global':issue['ticket_id']}


def main():
    with httpx.Client(base_url=os.getenv('SMOKE_BASE_URL','http://127.0.0.1:8000'),headers={'X-API-Key':os.environ['API_KEY']},timeout=20) as client:
        print(run_flows(client))
if __name__=='__main__':main()
