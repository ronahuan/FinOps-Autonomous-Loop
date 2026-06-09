#!/usr/bin/env bash
# Reset the demo to baseline state
export KUBECONFIG=~/.crc/machines/crc/kubeconfig
rm -f actor/out/suppress.txt actor/out/savings.csv
oc apply -f actor/test-workload.yaml

# Update fixture timestamp so the recommendation isn't stale
FRESH_TS=$(python3 -c "from datetime import datetime,timezone,timedelta; print((datetime.now(timezone.utc)-timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%SZ'))")
FIXTURE="observer/tests/fixtures/recommendation.json"
python3 -c "
import json
data = json.load(open('$FIXTURE'))
data[0]['last_reported'] = '$FRESH_TS'
json.dump(data, open('$FIXTURE','w'), indent=2)
print('Fixture timestamp updated to $FRESH_TS')
"

echo "Reset complete — suppress.txt and savings.csv cleared, waster restored to 500m/512Mi"
