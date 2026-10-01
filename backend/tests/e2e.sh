#!/bin/zsh
# End-to-end API test: spins up a server on a temp DB, exercises all endpoints.
set -u
cd "$(dirname "$0")/.."

PORT=8001
DB=/tmp/findash_test.db
DATA=/tmp/findash_test_data
rm -rf "$DB" "$DATA"

.venv/bin/python tests/make_samples.py > /dev/null
FINDASH_DB="$DB" FAMILYBIZ_DATA="$DATA" .venv/bin/uvicorn app.main:app --port $PORT > /tmp/uvicorn_test.log 2>&1 &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null" EXIT
sleep 3

B="http://localhost:$PORT/api"
J() { python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin), ensure_ascii=False)[:600])"; }

echo "=== upload ==="
curl -s -X POST $B/upload -F "files=@tests/samples/credit_sample.csv" -F "files=@tests/samples/bank_sample.csv" -F "files=@tests/samples/etrade_sample.csv" | J
echo "=== re-upload (dedup) ==="
curl -s -X POST $B/upload -F "files=@tests/samples/credit_sample.csv" | J
echo "=== rules ==="
curl -s -X POST $B/rules -H 'Content-Type: application/json' -d '{"pattern":"שכ\"ד","category":"שכר דירה - הכנסה"}' | J
curl -s -X POST $B/rules -H 'Content-Type: application/json' -d '{"pattern":"ועד בית","category":"דירה - הוצאות"}' | J
curl -s -X POST $B/rules/apply | J
echo "=== budget ==="
curl -s -X POST $B/budgets -H 'Content-Type: application/json' -d '{"category":"מזון","monthly_limit":200}' | J
curl -s "$B/budgets/status?period=2026-08&period_type=month" | J
echo "=== pension (account_id from response) ==="
PENSION_ACC=$(curl -s -X POST $B/pension -H 'Content-Type: application/json' -d '{"name":"פנסיה - מנורה","provider":"מנורה","product_type":"pension","fee_deposit_pct":2.5,"fee_accrual_pct":0.3}' | python3 -c "import json,sys; print(json.load(sys.stdin)['account_id'])")
curl -s -X POST $B/snapshots -H 'Content-Type: application/json' -d "{\"account_id\":$PENSION_ACC,\"date\":\"2026-09-01\",\"value\":350000}" | J
curl -s $B/pension | J
echo "=== property ==="
PROP_ACC=$(curl -s -X POST $B/properties -H 'Content-Type: application/json' -d '{"name":"דירה בחיפה","monthly_rent":4200}' | python3 -c "import json,sys; print(json.load(sys.stdin)['account_id'])")
curl -s -X POST $B/snapshots -H 'Content-Type: application/json' -d "{\"account_id\":$PROP_ACC,\"date\":\"2026-09-01\",\"value\":1500000}" | J
curl -s $B/properties | J
curl -s $B/properties/1/stats | J
echo "=== transactions summary + cashflow ==="
curl -s "$B/transactions/summary?source=credit&period_type=cycle" | J
curl -s "$B/transactions/cashflow?source=bank" | J
echo "=== category edit ==="
curl -s -X PATCH $B/transactions/1 -H 'Content-Type: application/json' -d '{"category":"סופרמרקט"}' | J
echo "=== dashboard ==="
curl -s $B/dashboard | J
echo "=== family app ==="
curl -s -X POST $B/members -H 'Content-Type: application/json' -d '{"name":"בדיקה","aliases":"בדיקה ישראלי"}' | J
curl -s -X POST "$B/products/credit_card/upload" -F "files=@tests/samples/credit_sample.csv" -F "member_id=1" | J
curl -s "$B/products/credit_card?member=1" | J
curl -s "$B/sheets/income-expense" | J
curl -s -X PUT $B/entries -H 'Content-Type: application/json' -d '{"line":"הפקדות לקרן פנסיה","month":"2026-08","amount":1500}' | J
curl -s "$B/sheets/networth" | J
curl -s -X POST $B/sheets/manual-items -H 'Content-Type: application/json' -d '{"name":"רכב","nw_bucket":"car","value":60000}' | J
curl -s "$B/sheets/calculator-defaults" | J
curl -s "$B/sheets/inflation" | J
