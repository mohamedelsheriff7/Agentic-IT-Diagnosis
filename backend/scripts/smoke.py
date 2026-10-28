"""Smoke test an actual HTTP server using environment credentials; no ASGI test client."""
import os
from uuid import uuid4
import httpx

def main():
    base=os.getenv('SMOKE_BASE_URL','http://127.0.0.1:8000')
    with httpx.Client(base_url=base,headers={'X-API-Key':os.environ['API_KEY']},timeout=10) as c:
        assert c.get('/health').status_code==200
        assert c.get('/tickets/INC-1001',headers={'X-API-Key':''}).status_code==401
        ticket=c.get('/tickets/INC-1001');ticket.raise_for_status()
        assert ticket.json()['diagnosis_code'] is None
        b={'action_id':'smoke-'+uuid4().hex,'summary':'Smoke HTTP issue','description':'Synthetic smoke test','reported_by_id':'USR-001'}
        created=c.post('/tickets',json=b);created.raise_for_status()
        assert c.post('/tickets',json=b).json()==created.json()
        t=created.json()['ticket_id']
        checked=c.post('/diagnostics/account-status',json={'ticket_id':t,'user_id':'USR-001','action_id':'smoke-'+uuid4().hex});checked.raise_for_status()
        assert checked.json()['password_expired']=='TRUE'
        count=c.post('/tickets/count-recent',json={'category':'VPN','configuration_item_id':'CI-VPN','location_id':'LOC-A','window_minutes':30});count.raise_for_status()
        assert count.json()['count']==3
        assert c.get('/evaluation/ground_truth.json').status_code==404
        assert c.get('/docs').status_code==200
        print('PASS real HTTP smoke: health, authentication, ticket read/create/retry, account evidence, outage count, hidden-file denial, Swagger')
if __name__=='__main__': main()
