URL=https://b9jgkp10t7.execute-api.us-west-2.amazonaws.com/
ORDER='{"price": 14955, "discount_pct": 12, "delivery_days": 5, "customer_tenure_days": 902, "prior_orders": 12, "prior_returns": 2, "is_gift": 0, "seller_rating": 3.4, "category": "electronics", "payment_method": "card"}'
#curl -s -w '\nHTTP %{http_code}\n' -X POST $URL/predict -H 'Content-Type: application/json' -d "$ORDER"


for i in 1 2 3 4; do curl -s -w '  %{time_total} s\n' -X POST $URL/predict -H 'Content-Type: application/json' -d "$ORDER"; done
