import os
import html
import requests
import gradio as gr

FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:8000")


# ============================================================
# API LAYER
# ============================================================

def call_api(endpoint, payload):
    try:
        response = requests.post(
            f"{FASTAPI_BASE_URL}{endpoint}",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.ConnectionError:
        return {
            "_ui_error": True,
            "title": "API Connection Failed",
            "message": f"Could not connect to FastAPI at {FASTAPI_BASE_URL}.",
            "hint": "Start the FastAPI server first, then run this Gradio application.",
        }
    except requests.exceptions.Timeout:
        return {
            "_ui_error": True,
            "title": "Request Timed Out",
            "message": "The prediction API did not respond within 30 seconds.",
            "hint": "Check that the FastAPI model endpoint is running correctly.",
        }
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        return {
            "_ui_error": True,
            "title": f"API Error ({response.status_code})",
            "message": str(detail),
            "hint": "Check the FastAPI endpoint and the request payload.",
        }
    except Exception as e:
        return {
            "_ui_error": True,
            "title": "Unexpected Error",
            "message": str(e),
            "hint": "Check the terminal running FastAPI for more details.",
        }


# ============================================================
# RESULT FORMATTER
# Converts the JSON API response into a premium visual card.
# The API itself is NOT changed.
# ============================================================

def _pretty_key(key):
    text = str(key).replace("_", " ").replace("-", " ")
    return text.strip().title()


def _fmt_value(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, float):
        if 0 < abs(value) < 1:
            return f"{value:.2%}"
        return f"{value:,.3f}".rstrip("0").rstrip(".")

    if isinstance(value, (int, float)):
        return f"{value:,}"

    if value is None:
        return "—"

    return str(value)


def _find_value(data, possible_names):
    if not isinstance(data, dict):
        return None
    normalized = {str(k).lower().replace(" ", "_"): v for k, v in data.items()}
    for name in possible_names:
        if name in normalized:
            return normalized[name]
    return None


def render_result(data, result_type="risk"):
    """Render any normal JSON API response as a polished HTML result card."""

    if not isinstance(data, dict):
        data = {"result": data}

    if data.get("_ui_error"):
        return f"""
        <div class="result-card error-card">
            <div class="result-icon">⚠️</div>
            <div>
                <div class="result-eyebrow">SYSTEM ERROR</div>
                <h2>{html.escape(str(data.get("title", "Prediction Error")))}</h2>
                <p>{html.escape(str(data.get("message", "")))}</p>
                <div class="error-hint">💡 {html.escape(str(data.get("hint", "")))}</div>
            </div>
        </div>
        """

    # Common response names used by ML APIs.
    prediction = _find_value(
        data,
        [
            "prediction", "predicted_class", "predicted_label",
            "risk_level", "risk", "claim_prediction",
            "claim_status", "result", "label", "output"
        ],
    )

    model = _find_value(data, ["model", "model_name", "algorithm"])
    status = _find_value(data, ["status", "message"])

    if prediction is None:
        # Try the first meaningful scalar value.
        for k, v in data.items():
            if not str(k).startswith("_") and not isinstance(v, (dict, list)):
                if k.lower() not in {"status", "message"}:
                    prediction = v
                    break

    title = "PATIENT RISK ASSESSMENT" if result_type == "risk" else "INSURANCE CLAIM ASSESSMENT"
    accent = "risk" if result_type == "risk" else "claim"

    pred_text = _fmt_value(prediction) if prediction is not None else "Prediction Available"

    # Semantic styling for common labels.
    low = str(pred_text).lower()
    if any(x in low for x in ["low", "safe", "approved", "no", "0", "normal"]):
        badge_class = "good"
        icon = "✓"
        badge_text = "LOW / POSITIVE"
    elif any(x in low for x in ["medium", "moderate", "review", "pending"]):
        badge_class = "medium"
        icon = "!"
        badge_text = "MODERATE"
    elif any(x in low for x in ["high", "risk", "rejected", "yes", "1", "critical"]):
        badge_class = "danger"
        icon = "!"
        badge_text = "HIGH / ATTENTION"
    else:
        badge_class = "info"
        icon = "✦"
        badge_text = "AI RESULT"

    model_display = _fmt_value(model) if model is not None else "FastAPI ML Service"

    # Keep the full response available in a compact technical section.
    rows = []
    for key, value in data.items():
        if str(key).startswith("_"):
            continue
        if key in {"prediction", "predicted_class", "predicted_label", "risk_level",
                   "risk", "claim_prediction", "claim_status", "result", "label", "output",
                   "probability", "prediction_probability", "confidence", "risk_probability",
                   "claim_probability", "score"}: # Ignore probability keys in details as well
            continue
        if isinstance(value, (dict, list)):
            value = str(value)
        rows.append(
            f'<div class="detail-row"><span>{html.escape(_pretty_key(key))}</span>'
            f'<strong>{html.escape(_fmt_value(value))}</strong></div>'
        )

    details_html = "".join(rows) or '<div class="empty-details">No additional metadata returned by the API.</div>'

    return f"""
    <div class="result-shell {accent}-result">
        <div class="result-card">
            <div class="result-top">
                <div>
                    <div class="result-eyebrow">AI PREDICTION • {title}</div>
                    <h2>Prediction Complete</h2>
                    <p>Your request was processed successfully by the healthcare ML service.</p>
                </div>
                <div class="success-mark">✓</div>
            </div>

            <div class="prediction-panel">
                <div class="prediction-copy">
                    <span class="prediction-label">Predicted Outcome</span>
                    <div class="prediction-value">{html.escape(pred_text)}</div>
                    <span class="status-pill {badge_class}">
                        <span>{icon}</span> {badge_text}
                    </span>
                </div>
            </div>

            <div class="result-meta">
                <div><span>MODEL SERVICE</span><b>{html.escape(model_display)}</b></div>
                <div><span>API STATUS</span><b class="online">● Online</b></div>
                <div><span>RESPONSE</span><b>{html.escape(_fmt_value(status) if status else "Successful")}</b></div>
            </div>

            <details class="technical-details">
                <summary>View technical response details</summary>
                <div class="details-list">{details_html}</div>
            </details>
        </div>
    </div>
    """


# ============================================================
# PREDICTION FUNCTIONS
# ============================================================

def predict_risk(age, gender, city, insurance, chronic, department,
                 visit_type, doctor, stay, days, frequency, avg_los,
                 month, weekday):

    payload = {
        "age": age,
        "gender": gender,
        "city": city,
        "insurance_provider": insurance,
        "chronic_flag": chronic,
        "department": department,
        "visit_type": visit_type,
        "doctor_id": doctor,
        "length_of_stay_hours": stay,
        "days_since_registration": days,
        "visit_frequency": frequency,
        "avg_los_per_patient": avg_los,
        "visit_month": month,
        "visit_dayofweek": weekday,
    }

    result = call_api("/predict/risk", payload)
    return render_result(result, "risk")


def predict_claim(age, gender, city, insurance, chronic, department,
                  visit_type, doctor, stay, risk, amount, days, frequency,
                  avg_los, rejection, month, weekday, high_cost):

    payload = {
        "age": age,
        "gender": gender,
        "city": city,
        "insurance_provider": insurance,
        "chronic_flag": chronic,
        "department": department,
        "visit_type": visit_type,
        "doctor_id": doctor,
        "length_of_stay_hours": stay,
        "risk_score": risk,
        "billed_amount": amount,
        "days_since_registration": days,
        "visit_frequency": frequency,
        "avg_los_per_patient": avg_los,
        "provider_rejection_rate": rejection,
        "visit_month": month,
        "visit_dayofweek": weekday,
        "high_cost_visit_flag": high_cost,
    }

    result = call_api("/predict/claim", payload)
    return render_result(result, "claim")


# ============================================================
# PREMIUM UI
# ============================================================

css = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
    --bg: #070b14;
    --panel: rgba(17, 24, 39, 0.72);
    --panel2: rgba(30, 41, 59, 0.52);
    --border: rgba(148, 163, 184, 0.16);
    --text: #f8fafc;
    --muted: #94a3b8;
    --cyan: #22d3ee;
    --blue: #3b82f6;
    --purple: #8b5cf6;
    --green: #34d399;
    --orange: #fbbf24;
    --red: #fb7185;
}

* { box-sizing: border-box; }

body {
    margin: 0;
    background:
        radial-gradient(circle at 10% 0%, rgba(59,130,246,.18), transparent 28%),
        radial-gradient(circle at 90% 8%, rgba(139,92,246,.18), transparent 28%),
        radial-gradient(circle at 50% 100%, rgba(34,211,238,.08), transparent 35%),
        var(--bg);
    color: var(--text);
    font-family: Inter, sans-serif;
}

.gradio-container {
    max-width: 1480px !important;
    margin: auto !important;
    padding: 22px !important;
    background: transparent !important;
}

.header {
    position: relative;
    overflow: hidden;
    padding: 42px 34px;
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 30px;
    background:
        linear-gradient(135deg, rgba(37,99,235,.30), rgba(6,182,212,.12) 48%, rgba(139,92,246,.22)),
        rgba(15,23,42,.72);
    box-shadow: 0 30px 80px rgba(0,0,0,.30);
    backdrop-filter: blur(20px);
    text-align: center;
}

.header:before, .header:after {
    content: "";
    position: absolute;
    border-radius: 999px;
    filter: blur(2px);
    opacity: .55;
}
.header:before {
    width: 180px; height: 180px;
    background: rgba(34,211,238,.18);
    top: -100px; left: -40px;
}
.header:after {
    width: 220px; height: 220px;
    background: rgba(139,92,246,.16);
    right: -80px; bottom: -130px;
}

.header h1 {
    position: relative;
    z-index: 2;
    margin: 0;
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(30px, 4vw, 52px);
    letter-spacing: -1.8px;
}

.header p {
    position: relative;
    z-index: 2;
    margin: 12px auto 0;
    color: #cbd5e1;
    font-size: 16px;
    max-width: 760px;
}

.section-title {
    font-family: "Space Grotesk", sans-serif;
    color: #f8fafc;
    margin-bottom: 8px;
}

.info-grid {
    margin: 18px 0 26px;
}

.info-card {
    min-height: 125px;
    padding: 22px;
    border: 1px solid var(--border);
    border-radius: 22px;
    background: var(--panel);
    box-shadow: 0 18px 50px rgba(0,0,0,.18);
    backdrop-filter: blur(16px);
}

.info-card h3 {
    margin: 0 0 8px;
    font-family: "Space Grotesk", sans-serif;
    font-size: 17px;
}

.info-card p {
    margin: 5px 0;
    color: var(--muted);
    font-size: 13px;
}

.live-dot { color: var(--green); }
.live-dot::before { content: "●"; margin-right: 7px; }

.tab-nav button {
    border-radius: 14px !important;
    font-weight: 700 !important;
}

.input-card {
    border: 1px solid var(--border) !important;
    border-radius: 24px !important;
    padding: 22px !important;
    background: rgba(15,23,42,.62) !important;
    box-shadow: 0 18px 55px rgba(0,0,0,.16);
}

label span {
    color: #cbd5e1 !important;
    font-weight: 600 !important;
}

input, textarea, select {
    border-radius: 13px !important;
    border: 1px solid rgba(148,163,184,.16) !important;
    background: rgba(2,6,23,.55) !important;
}

button.primary {
    border: 0 !important;
    border-radius: 15px !important;
    min-height: 58px !important;
    font-size: 16px !important;
    font-weight: 800 !important;
    letter-spacing: .2px;
    background: linear-gradient(135deg, #2563eb, #06b6d4) !important;
    box-shadow: 0 14px 35px rgba(37,99,235,.25) !important;
    transition: transform .18s ease, box-shadow .18s ease !important;
}

button.primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 18px 45px rgba(6,182,212,.25) !important;
}

.result-shell { margin-top: 10px; }

.result-card {
    padding: 26px;
    border-radius: 26px;
    border: 1px solid rgba(148,163,184,.17);
    background:
        linear-gradient(145deg, rgba(15,23,42,.94), rgba(15,23,42,.68)),
        rgba(15,23,42,.80);
    box-shadow: 0 24px 70px rgba(0,0,0,.28);
    backdrop-filter: blur(18px);
}

.result-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
}

.result-eyebrow {
    color: var(--cyan);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1.5px;
}

.result-top h2 {
    margin: 7px 0 4px;
    font-family: "Space Grotesk", sans-serif;
    font-size: 28px;
}

.result-top p {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
}

.success-mark {
    display: grid;
    place-items: center;
    width: 48px;
    height: 48px;
    border-radius: 15px;
    color: #052e1b;
    background: var(--green);
    font-size: 25px;
    font-weight: 900;
    box-shadow: 0 0 30px rgba(52,211,153,.22);
}

.prediction-panel {
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 18px;
    margin-top: 24px;
    padding: 34px 24px;
    border-radius: 21px;
    border: 1px solid rgba(34,211,238,.13);
    background: linear-gradient(120deg, rgba(34,211,238,.07), rgba(139,92,246,.07));
}

.prediction-copy { flex: 1; display: flex; flex-direction: column; align-items: center; }

.prediction-label {
    display: block;
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .9px;
}

.prediction-value {
    margin: 5px 0 12px;
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(28px, 4vw, 43px);
    font-weight: 700;
    letter-spacing: -1px;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 11px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: .6px;
}
.status-pill.good { color: #6ee7b7; background: rgba(52,211,153,.12); border: 1px solid rgba(52,211,153,.20); }
.status-pill.medium { color: #fde68a; background: rgba(251,191,36,.12); border: 1px solid rgba(251,191,36,.20); }
.status-pill.danger { color: #fda4af; background: rgba(251,113,133,.12); border: 1px solid rgba(251,113,133,.20); }
.status-pill.info { color: #67e8f9; background: rgba(34,211,238,.12); border: 1px solid rgba(34,211,238,.20); }

.result-meta {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 14px;
}
.result-meta > div {
    padding: 15px;
    border-radius: 15px;
    background: rgba(2,6,23,.28);
    border: 1px solid rgba(148,163,184,.10);
}
.result-meta span {
    display: block;
    color: #64748b;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 1px;
}
.result-meta b {
    display: block;
    margin-top: 6px;
    color: #cbd5e1;
    font-size: 12px;
}
.result-meta .online { color: var(--green); }

.technical-details {
    margin-top: 15px;
    border-top: 1px solid rgba(148,163,184,.11);
    padding-top: 15px;
}
.technical-details summary {
    cursor: pointer;
    color: #94a3b8;
    font-size: 12px;
    font-weight: 700;
}
.details-list { margin-top: 12px; }
.detail-row {
    display: flex;
    justify-content: space-between;
    gap: 20px;
    padding: 10px 0;
    border-bottom: 1px solid rgba(148,163,184,.07);
}
.detail-row span { color: #64748b; font-size: 11px; }
.detail-row strong { color: #cbd5e1; font-size: 11px; text-align: right; }
.empty-details { color: #64748b; font-size: 12px; }

.error-card {
    display: flex;
    gap: 18px;
    align-items: flex-start;
    border-color: rgba(251,113,133,.22);
    background: linear-gradient(135deg, rgba(127,29,29,.22), rgba(15,23,42,.88));
}
.result-icon { font-size: 30px; }
.error-card h2 { margin: 3px 0 7px; font-family: "Space Grotesk", sans-serif; }
.error-card p { color: #cbd5e1; font-size: 13px; }
.error-hint {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 11px;
    color: #fda4af;
    background: rgba(251,113,133,.08);
    font-size: 11px;
}

.footer {
    margin: 30px 0 8px;
    padding: 18px;
    color: #64748b;
    text-align: center;
    font-size: 11px;
    border-top: 1px solid rgba(148,163,184,.08);
}

@media (max-width: 760px) {
    .gradio-container { padding: 12px !important; }
    .header { padding: 30px 18px; }
    .prediction-panel { flex-direction: column; }
    .result-meta { grid-template-columns: 1fr; }
}
"""


# ============================================================
# GRADIO APPLICATION
# ============================================================

with gr.Blocks(css=css, title="Healthcare AI Intelligence") as app:

    gr.HTML("""
    <div class="header">
        <h1>🏥 Healthcare AI Intelligence</h1>
        <p>
            Production-style machine learning interface for patient risk
            assessment and insurance claim prediction.
        </p>
    </div>
    """)

    with gr.Row(elem_classes="info-grid"):
        with gr.Column(elem_classes="info-card"):
            gr.HTML("""
            <h3>🤖 AI Models</h3>
            <p>🟢 Patient Risk Prediction</p>
            <p>🟢 Insurance Claim Prediction</p>
            """)
        with gr.Column(elem_classes="info-card"):
            gr.HTML("""
            <h3>⚡ Inference Layer</h3>
            <p>FastAPI REST API</p>
            <p>JSON request → visual AI response</p>
            """)
        with gr.Column(elem_classes="info-card"):
            gr.HTML("""
            <h3>📡 System Status</h3>
            <p><span class="live-dot">API Ready</span></p>
            <p>Two prediction workflows available</p>
            """)

    # --------------------------------------------------------
    # RISK TAB
    # --------------------------------------------------------
    with gr.Tab("🩺  Patient Risk Prediction"):

        gr.Markdown("## Patient Information", elem_classes="section-title")

        with gr.Row():
            with gr.Column(elem_classes="input-card"):
                age = gr.Number(value=52, label="Age")
                gender = gr.Dropdown(["M", "F"], value="M", label="Gender")
                city = gr.Textbox(value="Bangalore", label="City")
                insurance = gr.Textbox(value="CareOne", label="Insurance Provider")
                chronic = gr.Dropdown([0, 1], value=1, label="Chronic Disease Flag")
                department = gr.Textbox(value="Cardiology", label="Department")
                visit_type = gr.Textbox(value="ER", label="Visit Type")

            with gr.Column(elem_classes="input-card"):
                gr.Markdown("### Visit Details")
                doctor = gr.Number(value=101, label="Doctor ID")
                stay = gr.Number(value=48, label="Length of Stay — Hours")
                days = gr.Number(value=300, label="Days Since Registration")
                frequency = gr.Number(value=4, label="Visit Frequency")
                avg_los = gr.Number(value=36.5, label="Average LOS per Patient")
                month = gr.Number(value=3, label="Visit Month")
                weekday = gr.Number(value=2, label="Visit Day of Week")

        risk_btn = gr.Button("🔮  Predict Patient Risk", variant="primary")
        risk_output = gr.HTML(
            value="""
            <div class="result-card">
                <div class="result-eyebrow">AI PREDICTION</div>
                <h2>Ready for analysis</h2>
                <p style="color:#94a3b8">
                    Enter patient information and run the model to see the
                    prediction in a visual dashboard.
                </p>
            </div>
            """,
            label="AI Prediction Result",
        )

        risk_btn.click(
            predict_risk,
            inputs=[
                age, gender, city, insurance, chronic, department,
                visit_type, doctor, stay, days, frequency, avg_los,
                month, weekday
            ],
            outputs=risk_output,
        )

    # --------------------------------------------------------
    # CLAIM TAB
    # --------------------------------------------------------
    with gr.Tab("💳  Insurance Claim Prediction"):

        gr.Markdown("## Claim & Patient Information", elem_classes="section-title")

        with gr.Row():
            with gr.Column(elem_classes="input-card"):
                age2 = gr.Number(52, label="Age")
                gender2 = gr.Dropdown(["M", "F"], value="M", label="Gender")
                city2 = gr.Textbox("Bangalore", label="City")
                insurance2 = gr.Textbox("CareOne", label="Insurance Provider")
                chronic2 = gr.Dropdown([0, 1], value=1, label="Chronic Disease Flag")
                department2 = gr.Textbox("Cardiology", label="Department")
                visit_type2 = gr.Textbox("ER", label="Visit Type")

            with gr.Column(elem_classes="input-card"):
                gr.Markdown("### Claim Details")
                doctor2 = gr.Number(101, label="Doctor ID")
                stay2 = gr.Number(48, label="Length of Stay — Hours")
                risk2 = gr.Dropdown(
                    ["Low", "Medium", "High"],
                    value="High",
                    label="Risk Score"
                )
                amount = gr.Number(65000, label="Billed Amount")
                days2 = gr.Number(300, label="Days Since Registration")
                frequency2 = gr.Number(4, label="Visit Frequency")
                avg2 = gr.Number(36.5, label="Average LOS per Patient")
                rejection = gr.Number(0.257, label="Provider Rejection Rate")
                month2 = gr.Number(3, label="Visit Month")
                weekday2 = gr.Number(2, label="Visit Day of Week")
                high = gr.Dropdown([0, 1], value=1, label="High Cost Visit Flag")

        claim_btn = gr.Button("🚀  Predict Insurance Claim", variant="primary")
        claim_output = gr.HTML(
            value="""
            <div class="result-card">
                <div class="result-eyebrow">CLAIM AI PREDICTION</div>
                <h2>Ready for analysis</h2>
                <p style="color:#94a3b8">
                    Submit the claim details to generate a visual AI assessment.
                </p>
            </div>
            """,
            label="Claim AI Result",
        )

        claim_btn.click(
            predict_claim,
            inputs=[
                age2, gender2, city2, insurance2, chronic2, department2,
                visit_type2, doctor2, stay2, risk2, amount, days2,
                frequency2, avg2, rejection, month2, weekday2, high
            ],
            outputs=claim_output,
        )

    gr.HTML("""
    <div class="footer">
        Healthcare AI Intelligence • Gradio Frontend • FastAPI Inference API
        • ML-powered decision support interface
    </div>
    """)


if __name__ == "__main__":
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )