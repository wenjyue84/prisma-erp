"""
AWS Lambda: prisma-erp Wake-on-Demand
Env vars: INSTANCE_ID, REGION, SITE_URL
"""
import json
import os
import boto3

INSTANCE_ID = os.environ["INSTANCE_ID"]  # i-0689ed2e9d9089d0d
REGION      = os.environ["REGION"]       # ap-southeast-1
SITE_URL    = os.environ.get("SITE_URL", "https://prismaerp.click")

ec2 = boto3.client("ec2", region_name=REGION)

CORS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

WAKE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ERPNext &mdash; Starting</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#f5f5f5;display:flex;align-items:center;
          justify-content:center;min-height:100vh;color:#333}}
    .card{{background:#fff;border-radius:12px;padding:48px 56px;
           text-align:center;max-width:460px;width:100%;
           box-shadow:0 4px 24px rgba(0,0,0,.08)}}
    .icon{{font-size:48px;margin-bottom:16px}}
    h1{{font-size:22px;margin-bottom:8px}}
    p{{color:#888;font-size:14px;margin-bottom:32px;line-height:1.6}}
    .spinner{{width:36px;height:36px;border:3px solid #e0e0e0;
              border-top-color:#2490ef;border-radius:50%;
              animation:spin .9s linear infinite;margin:0 auto 20px}}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}
    #msg{{font-size:15px;color:#555;margin-bottom:6px}}
    #elapsed{{font-size:12px;color:#bbb}}
    .bar-wrap{{background:#f0f0f0;border-radius:8px;height:5px;
               margin-top:24px;overflow:hidden}}
    .bar{{height:100%;background:#2490ef;border-radius:8px;
          width:0%;transition:width 1s ease}}
  </style>
</head>
<body>
<div class="card">
  <div class="icon">&#9889;</div>
  <h1>ERPNext is waking up</h1>
  <p>The server was idle and shut down to save costs.<br>
     It will be ready in about <strong>3 minutes</strong>.</p>
  <div class="spinner"></div>
  <p id="msg">Requesting server start&hellip;</p>
  <p id="elapsed">0s elapsed</p>
  <div class="bar-wrap"><div class="bar" id="bar"></div></div>
</div>
<script>
  const API = "{lambda_url}";
  const BOOT_MS = 180000;
  const POLL_MS = 10000;
  const t0 = Date.now();

  const msg = document.getElementById('msg');
  const elapsed = document.getElementById('elapsed');
  const bar = document.getElementById('bar');

  setInterval(() => {{
    const s = Math.floor((Date.now()-t0)/1000);
    elapsed.textContent = s + 's elapsed';
    bar.style.width = Math.min(95,(s/(BOOT_MS/1000))*100)+'%';
  }}, 1000);

  async function wake() {{
    try {{
      const r = await fetch(API+'/wake',{{method:'POST'}});
      const d = await r.json();
      if(d.state==='running'){{msg.textContent='Already running — checking site…';checkSite();return;}}
      msg.textContent='Start command sent — waiting…';
    }} catch(e) {{ msg.textContent='Retrying…'; }}
  }}

  let ec2Running = false;

  const poll = setInterval(async () => {{
    try {{
      const r = await fetch(API+'/status');
      const d = await r.json();
      if(d.state==='running' && !ec2Running){{
        ec2Running = true;
        msg.textContent='EC2 running — waiting for ERPNext to boot…';
        clearInterval(poll);
        checkSite();
      }} else if(!ec2Running) {{
        msg.textContent='EC2 state: '+d.state+'…';
      }}
    }} catch(e) {{}}
  }}, POLL_MS);

  function checkSite() {{
    const siteCheck = setInterval(async () => {{
      try {{
        const r = await fetch(window.location.origin+'/login',{{cache:'no-store'}});
        if(r.ok){{
          const t = await r.text();
          if(t.includes('frappe') || t.includes('login_page')){{
            clearInterval(siteCheck);
            msg.textContent='ERPNext is ready — redirecting…';
            bar.style.width='100%';
            setTimeout(()=>window.location.href=window.location.origin,2000);
            return;
          }}
        }}
        msg.textContent='ERPNext booting (HTTP '+r.status+')…';
      }} catch(e) {{
        msg.textContent='Waiting for ERPNext to start…';
      }}
    }}, 8000);
  }}

  wake();
</script>
</body>
</html>"""


def get_state():
    r = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
    return r["Reservations"][0]["Instances"][0]["State"]["Name"]


def ok(body):
    return {
        "statusCode": 200,
        "headers": {**CORS, "Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def html_response(lambda_url):
    return {
        "statusCode": 503,
        "headers": {
            **CORS,
            "Content-Type": "text/html;charset=UTF-8",
            "Cache-Control": "no-store",
        },
        "body": WAKE_HTML.format(lambda_url=lambda_url),
    }


def lambda_handler(event, context):
    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod", "GET")
    )
    path = event.get("rawPath") or event.get("path", "/")
    lambda_url = "https://" + event.get("requestContext", {}).get("domainName", "")

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS, "body": ""}

    if path == "/wake" and method == "POST":
        state = get_state()
        if state == "stopped":
            ec2.start_instances(InstanceIds=[INSTANCE_ID])
            state = "pending"
        return ok({"state": state})

    if path == "/status":
        return ok({"state": get_state()})

    # Default: wake page (CloudFront failover path)
    return html_response(lambda_url)
