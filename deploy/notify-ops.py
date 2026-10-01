#!/usr/bin/env python3
"""Optional operator-configured HTTPS webhook; sends only service name/severity."""
import json,os,sys,urllib.request,subprocess
unit=sys.argv[1] if len(sys.argv)>1 else 'unknown'
subprocess.run(['/usr/bin/logger','--priority','daemon.crit','--tag','forvalta','Operational failure: '+unit],check=True)
url=os.getenv('FORVALTA_ALERT_WEBHOOK')
if not url:raise SystemExit('No external alert route configured; failure is in the system journal.')
if not url.startswith('https://'):raise SystemExit('Alert endpoint must use HTTPS')
body=json.dumps({'service':'forvalta','severity':'critical','unit':unit}).encode()
headers={'Content-Type':'application/json'}
if os.getenv('FORVALTA_ALERT_TOKEN'):headers['Authorization']='Bearer '+os.environ['FORVALTA_ALERT_TOKEN']
try:
    with urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers),timeout=15) as response:
        if response.status>=300:raise ValueError()
except Exception:raise SystemExit('Alert delivery failed; inspect the local journal.') from None
