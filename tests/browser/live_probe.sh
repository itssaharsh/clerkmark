#!/usr/bin/env bash
# T09 live probes against a running server (default :8030). Prints one line per check; exit 1 on any FAIL.
B=${1:-http://127.0.0.1:8030}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fails=0
check() { if [ "$2" = "$3" ]; then echo "PASS $1 ($2)"; else echo "FAIL $1 (got $2, want $3)"; fails=$((fails+1)); fi; }
code() { curl -s -o "$T/body" -w "%{http_code}" "$@"; }
# validation
printf 'hello, not a pdf' > "$T/x.txt"
check "non-PDF bytes -> 415" "$(code -X POST -H 'X-Forwarded-For: 192.0.2.1' -F "file=@$T/x.txt;type=application/pdf;filename=x.pdf" $B/api/memo)" 415
check "empty body -> 400" "$(code -X POST -H 'X-Forwarded-For: 192.0.2.2' $B/api/memo)" 400
check "empty text -> 400" "$(code -X POST -H 'X-Forwarded-For: 192.0.2.2' -F 'text=   ' $B/api/memo)" 400
head -c 4300000 /dev/zero | sed 's/^/%PDF-1.4\n/' > "$T/big.pdf" 2>/dev/null || true
( printf '%%PDF-1.4\n'; head -c 4300000 /dev/zero ) > "$T/big.pdf"
check "> 4 MB upload -> 413" "$(code -X POST -H 'X-Forwarded-For: 192.0.2.3' -F "file=@$T/big.pdf;type=application/pdf" $B/api/memo)" 413
check "> 4 MB chunked upload -> 413" "$(code -X POST -H 'X-Forwarded-For: 192.0.2.4' -H 'Transfer-Encoding: chunked' -F "file=@$T/big.pdf;type=application/pdf" $B/api/memo)" 413
python3 -c "print('x'*200001, end='')" > "$T/long.txt"
check "> 200k chars text -> 413" "$(code -X POST -H 'X-Forwarded-For: 192.0.2.5' --data-urlencode "text@$T/long.txt" $B/api/memo)" 413
# traversal
for p in "/static/../main.py" "/static/%2e%2e/main.py" "/static/..%2fmain.py" "/static/%2e%2e/%2e%2e/etc/passwd"; do
  check "GET $p -> 404" "$(code --path-as-is $B$p)" 404
done
for s in "../../etc/passwd" "%2e%2e" "..%2f..%2fetc%2fpasswd"; do
  check "POST sample $s -> 404" "$(code --path-as-is -X POST $B/api/memo/sample/$s)" 404
done
# rate limit: 11 rapid requests from one address
codes=""
for i in $(seq 1 11); do codes="$codes $(code -X POST -H 'X-Forwarded-For: 192.0.2.77' -F 'text=Prose without any citation.' $B/api/memo)"; done
check "11 rapid POST /api/memo -> 10x200 then 429" "$(echo $codes)" "200 200 200 200 200 200 200 200 200 200 429"
python3 - "$T/body" <<'PY' || fails=$((fails+1))
import json, sys
e = json.load(open(sys.argv[1]))["error"]
assert e == {"code": "rate_limited", "message": "Too many checks from this address: this prototype runs 10 memos per minute.", "hint": "Wait a minute and run again, or use the sample filing."}, e
print("PASS 429 body is the rate_limited envelope")
PY
# headers
h=$(curl -s -D - -o /dev/null $B/)
echo "$h" | grep -qi "^content-security-policy: default-src 'self'; script-src 'self';" && echo "PASS GET / CSP" || { echo "FAIL GET / CSP"; fails=$((fails+1)); }
curl -s -D - -o /dev/null $B/api/health | grep -qi "^x-content-type-options: nosniff" && echo "PASS /api/health nosniff" || { echo "FAIL nosniff"; fails=$((fails+1)); }
# never-red: real cases in brief form
python3 - "$B" <<'PY' || fails=$((fails+1))
import json, sys, urllib.request, urllib.parse
B = sys.argv[1]
cites = ["EEOC v. Arabian Am. Oil Co., 499 U.S. 244 (1991).", "Dave v. D.C. Metro. Police Dep't, 905 F. Supp. 2d 1, 5 (D.D.C. 2012).",
         "Pac. Mar. Ass'n v. NLRB, 905 F. Supp. 2d 55 (D.D.C. 2012).", "Alaska Dep't of Env't Conservation v. EPA, 540 U.S. 461 (2004)."]
data = urllib.parse.urlencode({"text": " ".join(cites)}).encode()
req = urllib.request.Request(B + "/api/memo", data=data, headers={"X-Forwarded-For": "192.0.2.90"})
memo = json.load(urllib.request.urlopen(req))
bad = [(r["cite_text"], r["class"]) for r in memo["results"] if r["class"] == "likely_fabricated"]
for r in memo["results"]:
    print("     ", r["class"].ljust(18), r["cite_text"])
assert not bad, bad
print("PASS real cases in Bluebook form are never likely_fabricated (%d rows)" % len(memo["results"]))
PY
[ $fails -eq 0 ] && echo "PASS all live probes" || { echo "FAIL $fails"; exit 1; }
