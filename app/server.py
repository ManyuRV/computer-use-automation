"""Local demo target: a deliberately 'legacy' member-servicing web app.

Server-rendered, table-based layout, no ids, no test attributes, no semantic
classes - a stand-in for the legacy back-office surfaces in the brief.

Flows:
  /                 home with member search box
  /member/<id>      member detail (name, savings balance) or 'no member found'
  /member/<id>/open-subaccount  form -> POST -> confirmation, or validation error
Fault injection (query args):
  ?slow=1     adds a 6s delay (transient slowness)
  ?dialog=1   injects an unexpected modal dialog on the detail page
  ?expired=1  renders a 'session expired' page instead
"""
import time
from flask import Flask, request, render_template_string

app = Flask(__name__)

FAULT = {"mode": None}

MEMBERS = {
    "12345": {"name": "A. Rivera", "savings_balance": "4,812.07"},
    "67890": {"name": "J. Chen", "savings_balance": "19,203.55"},
}

LEGACY_WRAPPER = """<html><head><title>Fiserv-ish Member Servicing</title></head>
<body bgcolor="#f4f4f0">
<table width="640" align="center" cellpadding="4" cellspacing="0" border="1">
<tr><td bgcolor="#003366"><font color="white"><b>MemberServ Console v3.2 (Tenant A)</b></font></td></tr>
<tr><td>
{{ body }}
</td></tr>
<tr><td><font size="1">(c) 1998-2026 MemberServ. Unauthorized access prohibited.</font></td></tr>
</table></body></html>"""

def page(body):
    return render_template_string(LEGACY_WRAPPER.replace("{{ body }}", body))

def fault_checks():
    mode = FAULT["mode"]
    if mode == "slow":
        time.sleep(6)
    if mode == "expired":
        return page("<b>Session expired.</b> Please <a href='/'>sign in again</a>."), 440
    return None

@app.route("/")
def home():
    f = fault_checks()
    if f: return f
    return page("""
<b>Member Lookup</b>
<form method="POST" action="/search">
<table cellpadding="2"><tr>
<td>Member ID:</td><td><input type="text" name="member_id" size="12"></td>
<td><input type="submit" value="Search"></td>
</tr></table></form>""")

@app.route("/search", methods=["POST"])
def search():
    mid = request.form.get("member_id", "").strip()
    if not mid:
        return page("<font color='red'>Member ID is required.</font> <a href='/'>Back</a>"), 400
    from flask import redirect
    return redirect(f"/member/{mid}")

@app.route("/member/<mid>")
def member(mid):
    f = fault_checks()
    if f: return f
    if mid not in MEMBERS:
        return page(f"<b>No member found for ID {mid}.</b> Verify the ID and try again. "
                    "<a href='/'>Back to search</a>")
    m = MEMBERS[mid]
    dialog = ""
    if request.args.get("dialog"):
        dialog = ("<div id='modal' style='border:2px solid red;padding:8px;margin:6px'>"
                  "<b>System Notice:</b> Scheduled maintenance Sunday 02:00. "
                  "<button onclick=\"document.getElementById('modal').remove()\">Dismiss</button></div>")
    return page(f"""
{dialog}
<b>Member Detail</b>
<table border="1" cellpadding="3">
<tr><td>Member ID</td><td>{mid}</td></tr>
<tr><td>Name</td><td>{m['name']}</td></tr>
<tr><td>Savings Balance</td><td>${m['savings_balance']}</td></tr>
</table>
<br><a href="/member/{mid}/open-subaccount">Open a new sub-account</a>
&nbsp;|&nbsp;<a href="/">New search</a>""")

@app.route("/member/<mid>/open-subaccount")
def open_sub(mid):
    f = fault_checks()
    if f: return f
    if mid not in MEMBERS:
        return page(f"<b>No member found for ID {mid}.</b>"), 404
    return page(f"""
<b>Open Sub-Account for member {mid}</b>
<form method="POST" action="/member/{mid}/open-subaccount">
<table cellpadding="2">
<tr><td>Account type:</td><td><select name="acct_type">
<option value="">-- choose --</option><option value="SAVINGS">Savings</option>
<option value="CHECKING">Checking</option></select></td></tr>
<tr><td>Initial deposit ($):</td><td><input type="text" name="deposit" size="8"></td></tr>
<tr><td></td><td><input type="submit" value="Submit Application"></td></tr>
</table></form>""")

@app.route("/member/<mid>/open-subaccount", methods=["POST"])
def open_sub_post(mid):
    f = fault_checks()
    if f: return f
    at, dep = request.form.get("acct_type", ""), request.form.get("deposit", "")
    try:
        amt = float(dep)
    except ValueError:
        amt = 0.0
    if not at or amt < 25:
        return page(f"<font color='red'><b>Validation error:</b> account type required and "
                    f"minimum opening deposit is $25.00.</font> "
                    f"<a href='/member/{mid}/open-subaccount'>Back</a>"), 400
    return page(f"""
<b>Confirmation</b><br><br>
New {at.lower()} sub-account opened for member {mid} with opening deposit ${amt:,.2f}.<br>
Confirmation number: <b>CNF-{mid}-{at[:3]}</b><br><br>
<a href="/">Return home</a>""")

@app.route("/_control/fault")
def set_fault():
    FAULT["mode"] = request.args.get("mode") or None
    return f"fault={FAULT['mode']}"

if __name__ == "__main__":
    app.run(port=8377)
