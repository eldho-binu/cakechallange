import os
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

MASTER_ADMIN_EMAIL = os.getenv("MASTER_ADMIN_EMAIL", "margregoriousyouthpancode123@gmail.com")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "Christmas Cake Challenge <onboarding@resend.dev>")


def send_member_request_notification(applicant_name, phone_number, location, message, request_date):
    """
    Sends an email notification to the master administrator when a new member request is submitted.
    Wrapped in resilient try-except block so failure does NOT disrupt the request workflow.
    """
    if not RESEND_API_KEY:
        msg = "RESEND_API_KEY is not configured. Email notification skipped."
        logger.warning(msg)
        return False, msg

    subject = f"🔔 New Member Access Request: {applicant_name} ({location})"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #fdfbf7; color: #1c2e22; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2ebd8; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }}
        .header {{ background: linear-gradient(135deg, #14452F, #0D3322); color: #ffffff; padding: 28px 24px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 22px; letter-spacing: 0.5px; }}
        .header p {{ margin: 6px 0 0; color: #f3e5ab; font-size: 14px; font-weight: 500; }}
        .content {{ padding: 28px 24px; line-height: 1.6; }}
        .card {{ background: #f7faf4; border-left: 4px solid #C41E3A; border-radius: 6px; padding: 16px 20px; margin: 20px 0; }}
        .row {{ margin-bottom: 10px; }}
        .label {{ font-weight: 600; color: #14452F; display: inline-block; width: 140px; }}
        .value {{ color: #222; }}
        .footer {{ background: #f5f5f5; padding: 16px 24px; text-align: center; font-size: 12px; color: #777; border-top: 1px solid #eee; }}
        .btn {{ display: inline-block; background-color: #C41E3A; color: #ffffff !important; text-decoration: none; padding: 10px 22px; border-radius: 6px; font-weight: bold; margin-top: 15px; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>Christmas Cake Challenge</h1>
          <p>Church Youth Group — Member Request</p>
        </div>
        <div class="content">
          <p>Hello Administrator,</p>
          <p>A new member has submitted a request to join the Christmas Cake Challenge order management platform:</p>
          
          <div class="card">
            <div class="row"><span class="label">Applicant Name:</span> <span class="value"><strong>{applicant_name}</strong></span></div>
            <div class="row"><span class="label">Phone Number:</span> <span class="value">{phone_number}</span></div>
            <div class="row"><span class="label">Location / Parish:</span> <span class="value">{location}</span></div>
            <div class="row"><span class="label">Request Date:</span> <span class="value">{request_date}</span></div>
            <div class="row"><span class="label">Applicant Note:</span> <span class="value">{message if message else "None"}</span></div>
          </div>

          <p>Please log in to the administrator portal to review this application, assign a unique member code, and activate their account.</p>
        </div>
        <div class="footer">
          Sent by Christmas Cake Challenge Order System &bull; Pancode Youth Group
        </div>
      </div>
    </body>
    </html>
    """

    payload = {
        "from": RESEND_FROM_EMAIL,
        "to": [MASTER_ADMIN_EMAIL],
        "subject": subject,
        "html": html_content
    }

    try:
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY.strip()}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            logger.info(f"Resend notification sent successfully: {resp_body}")
            return True, "Notification email sent to master administrator."
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8") if e.fp else str(e)
        logger.error(f"Resend HTTP error ({e.code}): {err_msg}")
        return False, f"Resend API error: {err_msg}"
    except Exception as e:
        logger.error(f"Failed to send email via Resend: {e}")
        return False, f"Failed to send email: {str(e)}"
