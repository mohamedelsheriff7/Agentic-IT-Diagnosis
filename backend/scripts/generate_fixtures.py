"""Generate deterministic starter data; never called by API startup."""
import argparse
import json
import random
from datetime import datetime,timedelta,timezone
from pathlib import Path
from app.config import ROOT
from app.policy import utc

# code, domain, category, label, owner, English symptom, Arabic symptom
CASES=[
('PASSWORD_EXPIRED','Access Management','Authentication','Expired password','GRP-IAM','password expired sign in rejected','كلمة المرور انتهت تسجيل الدخول مرفوض'),
('ACCOUNT_LOCKED','Access Management','Authentication','Account lockout','GRP-IAM','account locked after login attempts','الحساب مقفول بعد محاولات الدخول'),
('MFA_FAILURE','Access Management','Authentication','MFA failure','GRP-IAM','MFA code rejected authentication phone','رمز التحقق مرفوض'),
('MISSING_ENTITLEMENT','Applications','Authorization','Missing application entitlement','GRP-APP','application access denied missing role','ليس لدي صلاحية للتطبيق'),
('APP_AUTH_FAILURE','Applications','Authentication','Application authentication failure','GRP-APP','portal sign in fails other applications work','البوابة لا تقبل الدخول وباقي التطبيقات تعمل'),
('LOCAL_ENDPOINT','Endpoints','Device','Local endpoint issue','GRP-END','laptop browser freezes local device','الجهاز بطيء والمتصفح يتوقف'),
('APP_OUTAGE','Applications','Availability','Application service outage','GRP-APP','portal unavailable error service down','البوابة متوقفة والخدمة لا تعمل'),
('VPN_OUTAGE','Network','VPN','VPN outage','GRP-NET','vpn connection timeout remote access unavailable','اتصال الشبكة الخاصة لا يعمل'),
('PHISHING','Security','Threat','Suspected phishing','GRP-SEC','suspicious email phishing link password request','رسالة مشبوهة تطلب كلمة المرور'),
('PRIVILEGED_ACCESS','Access Management','Privileges','Privileged-access request','GRP-IAM','administrator privileged access request','طلب صلاحيات مدير النظام'),
('SERVER_FAILURE','Infrastructure','Compute','Server failure','GRP-INFRA','server unreachable host offline','الخادم غير متاح'),
('UNKNOWN_ISSUE','Service Desk','Unclassified','Insufficient evidence','GRP-L1','not working help issue unclear','مش شغال ومش عارف السبب'),
('DNS_FAILURE','Network','DNS','DNS lookup failure','GRP-NET','hostname resolution DNS failed','اسم الموقع لا يعمل'),
('WIFI_FAILURE','Network','Connectivity','Wi-Fi association failure','GRP-NET','wifi disconnected cannot connect','الواي فاي مفصول'),
('DISK_FULL','Endpoints','Storage','Endpoint disk full','GRP-END','disk full cannot save file','المساحة ممتلئة لا يمكن حفظ الملف'),
('PRINTER_OFFLINE','Endpoints','Printing','Printer offline','GRP-END','printer offline print job stuck','الطابعة لا تعمل'),
('APP_ERROR','Applications','Execution','Application execution error','GRP-APP','application crashes unexpected error','التطبيق يغلق فجأة'),
('SYNC_DELAY','Applications','Synchronization','Application synchronization delay','GRP-APP','records not syncing delayed update','البيانات لم تتحدث'),
('MALWARE','Security','Threat','Suspected malware','GRP-SEC','antivirus malware warning suspicious process','تحذير فيروس على الجهاز'),
('DATA_EXPOSURE','Security','Data Protection','Suspected data exposure','GRP-SEC','confidential file shared publicly','ملف سري منشور للعامة'),
('STORAGE_FAILURE','Infrastructure','Storage','Storage service failure','GRP-INFRA','shared storage volume unavailable','التخزين المشترك غير متاح'),
('CERT_EXPIRED','Infrastructure','Certificates','Expired service certificate','GRP-INFRA','service certificate expired TLS warning','شهادة الخدمة منتهية'),
('ACCOUNT_DISABLED','Access Management','Authentication','Disabled account','GRP-IAM','account disabled sign in blocked','الحساب معطل'),
('REQUEST_GUIDANCE','Service Desk','How To','General guidance request','GRP-L1','how to use service portal guide','كيف استخدم بوابة الخدمات')]

def generate(root=ROOT,clock='2026-10-01T12:00:00Z',seed=42):
    rng=random.Random(seed)
    now=datetime.fromisoformat(clock.replace('Z','+00:00'))
    if now.tzinfo is None: raise ValueError('Clock must be timezone aware')
    data=root/'data'; evaluation=root/'evaluation'
    data.mkdir(parents=True,exist_ok=True);evaluation.mkdir(parents=True,exist_ok=True)
    def write(name,value,folder=data): (folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    groups=[('GRP-L1','Service Desk L1'),('GRP-IAM','IAM'),('GRP-APP','Application Support'),('GRP-END','Endpoint Support'),('GRP-NET','Network Operations'),('GRP-SEC','Security Operations'),('GRP-INFRA','Servers & Infrastructure')]
    write('resolver_groups',[dict(id=i,label=l) for i,l in groups])
    write('users',[dict(id=f'USR-{i:03}',label=f'Synthetic user {i:03}') for i in range(1,41)])
    write('locations',[dict(id=f'LOC-{c}',label=f'Synthetic site {c}') for c in 'ABCDEFG'])
    write('configuration_items',[dict(id='CI-'+i,label='Synthetic '+i) for i in ('PORTAL','VPN','ERP','MAIL','SERVER')])
    write('assets',[dict(id=f'ASSET-{i:03}',label=f'Synthetic laptop {i:03}') for i in range(1,41)])
    taxonomy=[dict(diagnosis_code=c,domain=d,category=k,label=l,resolver_group_id=g,security_sensitive=d=='Security',privileged_access=c=='PRIVILEGED_ACCESS') for c,d,k,l,g,en,ar in CASES]
    write('taxonomy',taxonomy)
    write('routing_matrix',[dict(diagnosis_code=t['diagnosis_code'],owner_group_id=t['resolver_group_id'],boundary='IAM owns identity; Application Support owns app-specific sessions and entitlements; Security leads suspected threats; L1 triages uncertainty.',alternative_group_ids=['GRP-L1'] if t['resolver_group_id']!='GRP-L1' else ['GRP-APP']) for t in taxonomy])
    write('escalation_policy',dict(id='POLICY-DEFAULT',mandatory_human_cases=['security_sensitive','privileged_access','reported_priority=1'],severity_rules={'SEV1':'Critical business impact; human review required','SEV2':'Multiple affected users in one service scope','SEV3':'Limited service degradation'},outage_thresholds=[dict(category=k,configuration_item_id=ci,location_id=loc,window_minutes=30,minimum_count=3) for k,ci,loc in [('VPN','CI-VPN','LOC-A'),('Availability','CI-PORTAL','LOC-B'),('Availability','CI-ERP','LOC-C')]]))
    states=[]
    for i in range(1,25):
        states.append(dict(id=f'ACC-{i:03}',user_id=f'USR-{i:03}',enabled='FALSE' if i==23 else 'TRUE',locked='TRUE' if i==2 else 'FALSE',password_expired='TRUE' if i==1 else 'FALSE',mfa_enrolled='TRUE',mfa_locked='TRUE' if i==3 else 'FALSE'))
    write('account_states',states)
    write('application_entitlements',[dict(id=f'ENT-{i:03}',user_id=f'USR-{i:03}',application_id='APP-PORTAL',entitled='FALSE' if i==4 else 'TRUE',roles=[] if i==4 else ['USER'],provisioning_state='ABSENT' if i==4 else 'ACTIVE') for i in range(1,25)])
    write('service_health',[dict(id=f'HEALTH-{i}',configuration_item_id=ci,location_id=loc,state=state,scope=f'{ci}/{loc}',details='Independent synthetic service monitor observation') for i,(ci,loc,state) in enumerate([('CI-PORTAL','LOC-A','OPERATIONAL'),('CI-VPN','LOC-A','UNAVAILABLE'),('CI-PORTAL','LOC-B','UNAVAILABLE'),('CI-ERP','LOC-C','DEGRADED'),('CI-VPN','LOC-D','OPERATIONAL'),('CI-PORTAL','LOC-E','OPERATIONAL'),('CI-ERP','LOC-F','OPERATIONAL')])])
    articles=[]
    for i,(c,d,k,l,g,en,ar) in enumerate(CASES):
        safe=c=='PASSWORD_EXPIRED'
        conditions=[dict(tool='check_account_status',field='password_expired',equals='TRUE'),dict(tool='check_account_status',field='enabled',equals='TRUE'),dict(tool='check_account_status',field='locked',equals='FALSE'),dict(tool='check_account_status',field='mfa_locked',equals='FALSE')] if safe else []
        articles.append(dict(article_id=f'KB-{i+1:03}',version=1,approved=True,diagnosis_code=c,domain=d,category=k,symptoms_en=[en,l],symptoms_ar=[ar],possible_causes=[l],discriminating_questions=['What exact error appears?','Do other applications work?','Is another user or device affected?', 'ما هي رسالة الخطأ؟'],required_evidence=['Affected person response','Independent relevant diagnostic check'],safe_checks=['check_account_status','check_application_entitlement','check_service_health'],exclusion_criteria=['Do not infer diagnosis from symptom overlap alone','Exclude competing causes with questions and checks'],competing_diagnoses=[CASES[(i+1)%len(CASES)][0]],resolution_steps=[dict(step_id=f'{c}-1',level='SELF_SERVICE' if safe else 'SPECIALIST',instruction='Ask the user to complete the approved self-service password change flow; never ask for their password.' if safe else 'Authorized specialist investigates and follows the organization runbook.')],agent_resolvable=safe,resolution_conditions=conditions,mandatory_human_escalation_conditions=['security_sensitive','privileged_access','reported_priority=1','insufficient evidence'],resolver_group_id=g))
    questions={
        'PASSWORD_EXPIRED':['Does the error explicitly say your password expired?','Do other applications using the same identity also reject sign-in?'],
        'ACCOUNT_LOCKED':['Does the error mention too many attempts or a locked account?','When did the failures start?'],
        'MFA_FAILURE':['Is the prompt missing, rejected, or arriving on a different device?','Is the authenticator enrolled and unlocked?'],
        'MISSING_ENTITLEMENT':['Can you sign in but not open this application?','Which role is required for the task?'],
        'APP_AUTH_FAILURE':['Do other applications accept the same identity?','Does the application fail in a second browser?'],
        'LOCAL_ENDPOINT':['Does the issue follow this device or also occur on another device?','Is only one browser affected?'],
        'APP_OUTAGE':['Which application and site are affected?','Are other users affected at the same time?'],
        'VPN_OUTAGE':['Which VPN service and site are affected?','Does ordinary internet access still work?'],
        'PHISHING':['Did you open a link or enter credentials? Do not share those credentials.','Can you describe the suspicious sender without forwarding secrets?'],
        'PRIVILEGED_ACCESS':['Which administrative task requires access?','Has an authorized approver reviewed the request?'],
        'SERVER_FAILURE':['Which host or service is unreachable?','When was it last reachable and from which site?'],
        'UNKNOWN_ISSUE':['ما هو التطبيق الذي لا يعمل؟','ما هي رسالة الخطأ ومتى بدأت المشكلة؟']}
    for article in articles:
        if article['diagnosis_code'] in questions:
            article['discriminating_questions']=questions[article['diagnosis_code']]
        if article['diagnosis_code']=='PASSWORD_EXPIRED':
            article['required_evidence']=['User reports an expiry error','check_account_status: password_expired TRUE, enabled TRUE, locked FALSE, mfa_locked FALSE']
            article['exclusion_criteria']=['Account is disabled or locked','MFA is locked','Security-sensitive, privileged or critical ticket']
            article['competing_diagnoses']=['ACCOUNT_LOCKED','MFA_FAILURE','APP_AUTH_FAILURE']
    write('diagnostic_articles',articles)
    def ticket(identifier,index,age,status='NEW',**changes):
        c,d,k,l,g,en,ar=CASES[index%24]
        lang=['en','ar','franco_ar'][(index+index//24)%3]
        desc=en if lang=='en' else ar if lang=='ar' else 'mesh shaghal: '+en.replace('connection','conection')
        result=dict(ticket_id=identifier,ticket_class='INCIDENT',summary=desc[:100],description=desc,status=status,reported_priority=3,impact=3,urgency=2,language=lang,domain=d,category=k,subcategory=None,diagnosis_code=None,owner_group_id=None,owner_id=None,reported_by_id=f'USR-{index%24+1:03}',affected_person_id=f'USR-{index%24+1:03}',asset_id=f'ASSET-{index%24+1:03}',configuration_item_id='CI-PORTAL',location_id='LOC-A',reported_at=utc(now-timedelta(minutes=age)),target_finish_at=None,actual_finish_at=None,resolved_at=None,closed_at=None,updated_at=utc(now-timedelta(minutes=age)),linked_solution_id=None,resolution_summary=None,is_global=False,global_ticket_id=None,severity=None,security_sensitive=d=='Security',privileged_access=c=='PRIVILEGED_ACCESS')
        result.update(changes)
        return result
    histories=[]
    for i in range(40):
        c,d,k,l,g,en,ar=CASES[i%24]
        history=ticket(f'HIST-{i+1:04}',i,10000+i*90,status='CLOSED' if i%2 else 'RESOLVED',diagnosis_code=c,subcategory=l,owner_group_id=g,reported_priority=rng.choice([2,3,4]),resolution_summary='Confirmed historical resolution: '+l,linked_solution_id=f'KB-{i%24+1:03}',resolved_at=utc(now-timedelta(days=2)),actual_finish_at=utc(now-timedelta(days=2)),closed_at=utc(now-timedelta(days=1)) if i%2 else None,updated_at=utc(now-timedelta(days=1)))
        history['initial_owner_group_id']='GRP-NET' if i<6 and g!='GRP-NET' else 'GRP-APP' if i<6 else g
        histories.append(history)
    write('historical_tickets',histories)
    opened=[ticket(f'INC-{1001+i}',i,60+i*3) for i in range(12)]
    opened[0].update(summary='Cannot sign in to the service portal',description='The portal rejects my sign-in. I have not checked other applications yet.',language='en',category='Authentication',domain='Access Management')
    opened[4].update(description='Portal sign-in fails while mail works. Browser retry did not help.',language='en')
    opened[11].update(summary='مش شغال',description='مش عارف ادخل ومش فاهم المشكلة',language='ar',domain=None,category=None)
    opened[10]['reported_priority']=1
    clusters=[]
    for cluster,(cat,ci,loc,idx) in enumerate([('VPN','CI-VPN','LOC-A',7),('Availability','CI-PORTAL','LOC-B',6),('Availability','CI-ERP','LOC-C',6)]):
        ids=[]
        for n,age in enumerate([30,15,0]):
            identifier=f'CLUSTER-{cluster+1}-{n+1}';ids.append(identifier)
            opened.append(ticket(identifier,idx,age,category=cat,configuration_item_id=ci,location_id=loc,description='Service unavailable for this user; cause not yet established.'))
        clusters.append(dict(name=f'cluster-{cluster+1}',category=cat,configuration_item_id=ci,location_id=loc,window_minutes=30,minimum_count=3,ticket_ids=ids,expected_count=3))
    decoys=[]
    for n,(cat,ci,loc,idx) in enumerate([('VPN','CI-VPN','LOC-D',7),('Availability','CI-PORTAL','LOC-E',6),('Availability','CI-ERP','LOC-F',6)]):
        ids=[]
        for j,(age,place) in enumerate([(5,loc),(90,loc),(10,'LOC-G')]):
            identifier=f'DECOY-{n+1}-{j+1}';ids.append(identifier)
            opened.append(ticket(identifier,idx,age,category=cat,configuration_item_id=ci,location_id=place,description='Intermittent access issue; needs investigation.'))
        decoys.append(dict(name=f'decoy-{n+1}',category=cat,configuration_item_id=ci,location_id=loc,window_minutes=30,minimum_count=3,ticket_ids=ids,expected_count=1))
    write('sample_open_tickets',opened)
    write('outage_fixtures',dict(clock=utc(now),seed=seed,clusters=clusters,decoys=decoys))
    truth=[dict(ticket_id=t['ticket_id'],expected_diagnosis=CASES[i][0] if i<12 else 'VPN_OUTAGE' if t['ticket_id'].startswith('CLUSTER-1-') else 'APP_OUTAGE' if t['ticket_id'].startswith('CLUSTER-') else None,evaluation_only=True) for i,t in enumerate(opened)]
    answers=[dict(ticket_id=t['ticket_id'],answers=['Please investigate this synthetic report.', 'I have no further verified information.'],evaluation_only=True) for t in opened]
    answers[0]['answers']=['Other applications reject sign-in too.','The error says my password expired.','I completed self-service change and can sign in now.']
    answers[4]['answers']=['Other applications work.','The portal fails in another browser too.']
    answers[11]['answers']=['المشكلة مش واضحة ومحتاج مساعدة من الدعم']
    write('ground_truth',truth,evaluation)
    write('scenario_answers',answers,evaluation)
    return len(histories),len(opened)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--clock',default='2026-10-01T12:00:00Z');parser.add_argument('--seed',type=int,default=42);parser.add_argument('--output',type=Path,default=ROOT)
    args=parser.parse_args();print(generate(args.output,args.clock,args.seed))

