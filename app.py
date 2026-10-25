"""
DisputeLens — Multilingual Payment Dispute Intelligence & Evidence Copilot
Decision-support tool only. Does NOT verify transactions, approve refunds,
or make official bank/RBI/NPCI decisions.
"""

import json
import os
import re
import textwrap
from datetime import datetime

import requests
import streamlit as st
from dotenv import load_dotenv

# ─── Load environment ─────────────────────────────────────────────────────────
load_dotenv(override=True)

# ─── Constants ────────────────────────────────────────────────────────────────
SARVAM_ENDPOINT = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_MODEL    = "sarvam-105b"
API_TIMEOUT     = 40
MAX_TOKENS      = 2048
POLICIES_FILE   = os.path.join(os.path.dirname(__file__), "policies.json")
APP_VERSION     = "2.0.0 — DisputeLens"

# ─── Evidence scoring weights per category ────────────────────────────────────
EVIDENCE_WEIGHTS = {
    "failed_payment": {
        "reference_id":   25,
        "amount":         20,
        "date":           15,
        "merchant":       15,
        "payment_status": 15,
        "screenshot_sms": 10,
    },
    "duplicate_debit": {
        "reference_id":   20,
        "amount":         20,
        "date":           15,
        "merchant":       10,
        "bank_statement": 25,
        "payment_status": 10,
    },
    "unauthorized_transaction": {
        "reference_id":   20,
        "amount":         15,
        "date":           15,
        "payment_status": 20,
        "screenshot_sms": 20,
        "customer_decl":  10,
    },
    "missing_reference": {
        "amount":         25,
        "date":           25,
        "merchant":       20,
        "payment_status": 20,
        "screenshot_sms": 10,
    },
    "merchant_dispute": {
        "reference_id":   15,
        "amount":         15,
        "date":           15,
        "merchant":       20,
        "order_id":       20,
        "delivery_proof": 15,
    },
    "wrong_credit": {
        "reference_id":   20,
        "amount":         20,
        "date":           15,
        "merchant":       15,
        "refund_ref":     20,
        "bank_statement": 10,
    },
    "escalation": {
        "reference_id":   15,
        "amount":         15,
        "date":           10,
        "complaint_ref":  30,
        "bank_response":  20,
        "screenshot_sms": 10,
    },
    "recurring_charge": {
        "reference_id":   15,
        "amount":         20,
        "date":           15,
        "merchant":       20,
        "cancel_proof":   20,
        "bank_statement": 10,
    },
    "default": {
        "reference_id":   25,
        "amount":         25,
        "date":           25,
        "merchant":       25,
    },
}

FIELD_LABELS = {
    "reference_id":   "Transaction Reference / UTR",
    "amount":         "Transaction Amount",
    "date":           "Transaction Date",
    "merchant":       "Merchant / Recipient",
    "payment_status": "Payment Status Evidence",
    "screenshot_sms": "Screenshot or SMS",
    "bank_statement": "Bank Statement",
    "customer_decl":  "Customer Declaration",
    "order_id":       "Order ID",
    "delivery_proof": "Delivery Proof",
    "refund_ref":     "Refund Reference Number",
    "complaint_ref":  "Prior Complaint Reference",
    "bank_response":  "Bank's Written Response",
    "cancel_proof":   "Cancellation Proof",
}

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DisputeLens | Payment Dispute Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #07080c;
    color: #dde1ee;
}

/* ── Hero ── */
.hero {
    background: linear-gradient(135deg, #0a0e1f 0%, #101828 50%, #091520 100%);
    border: 1px solid rgba(56,189,248,0.18);
    border-radius: 18px;
    padding: 2rem 2.5rem 1.5rem;
    margin-bottom: 1.8rem;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content:'';position:absolute;top:-80px;right:-80px;
    width:300px;height:300px;
    background:radial-gradient(circle,rgba(56,189,248,0.12) 0%,transparent 70%);
    pointer-events:none;
}
.hero-logo { font-size:0.72rem;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;color:#38bdf8;margin-bottom:0.3rem; }
.hero-title {
    font-size:2.6rem;font-weight:800;line-height:1.1;margin:0 0 0.25rem;
    background:linear-gradient(90deg,#38bdf8,#818cf8,#c084fc);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.hero-tag { font-size:0.9rem;color:#64748b;font-style:italic;margin-bottom:0.8rem; }
.hero-pills { display:flex;gap:0.6rem;flex-wrap:wrap;margin-top:0.4rem; }
.hero-pill { font-size:0.71rem;font-weight:600;padding:3px 10px;border-radius:20px;letter-spacing:0.05em; }
.pill-blue  { background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.3);color:#38bdf8; }
.pill-purple{ background:rgba(129,140,248,0.12);border:1px solid rgba(129,140,248,0.3);color:#818cf8; }
.pill-green { background:rgba(52,211,153,0.12);border:1px solid rgba(52,211,153,0.3);color:#34d399; }
.pill-orange{ background:rgba(251,146,60,0.12);border:1px solid rgba(251,146,60,0.3);color:#fb923c; }

/* ── Panels / cards ── */
.panel {
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.08);
    border-radius:14px;
    padding:1.2rem 1.4rem;
    margin-bottom:1rem;
}
.panel:hover { border-color:rgba(56,189,248,0.2); }
.panel-title {
    font-size:0.73rem;font-weight:700;text-transform:uppercase;
    letter-spacing:0.12em;color:#38bdf8;margin-bottom:0.7rem;
}
.panel-body { font-size:0.91rem;color:#cbd5e1;line-height:1.7; }

/* ── Section heading ── */
.sec-label {
    font-size:0.7rem;font-weight:700;letter-spacing:0.14em;
    text-transform:uppercase;color:#475569;margin-bottom:0.5rem;
}

/* ── Badges ── */
.badge { display:inline-block;padding:3px 12px;border-radius:20px;font-size:0.73rem;font-weight:700;letter-spacing:0.05em; }
.b-blue   { background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.4);color:#38bdf8; }
.b-green  { background:rgba(52,211,153,0.15);border:1px solid rgba(52,211,153,0.4);color:#34d399; }
.b-yellow { background:rgba(250,204,21,0.15);border:1px solid rgba(250,204,21,0.4);color:#fbbf24; }
.b-red    { background:rgba(248,113,113,0.15);border:1px solid rgba(248,113,113,0.4);color:#f87171; }
.b-purple { background:rgba(192,132,252,0.15);border:1px solid rgba(192,132,252,0.4);color:#c084fc; }
.b-gray   { background:rgba(148,163,184,0.1);border:1px solid rgba(148,163,184,0.25);color:#94a3b8; }

/* ── Evidence bar ── */
.ev-bar-wrap { background:rgba(255,255,255,0.06);border-radius:8px;height:12px;overflow:hidden;margin:0.6rem 0; }
.ev-bar      { height:100%;border-radius:8px;transition:width 0.4s ease; }

/* ── Policy quote ── */
.policy-quote {
    background:rgba(56,189,248,0.06);
    border-left:3px solid #38bdf8;
    border-radius:0 10px 10px 0;
    padding:0.8rem 1rem;
    font-size:0.87rem;color:#bae6fd;font-style:italic;line-height:1.65;
    margin:0.4rem 0 0.8rem;
}
.policy-id-tag {
    display:inline-block;background:rgba(56,189,248,0.15);color:#38bdf8;
    font-size:0.68rem;font-weight:700;padding:2px 8px;border-radius:10px;
    margin-bottom:0.4rem;font-style:normal;
}

/* ── Contradiction row ── */
.contra-ok   { color:#34d399;font-size:0.88rem;margin-bottom:0.3rem; }
.contra-warn { color:#fbbf24;font-size:0.88rem;margin-bottom:0.3rem; }
.contra-crit { color:#f87171;font-size:0.88rem;margin-bottom:0.3rem; }

/* ── Draft box ── */
.draft-box {
    background:rgba(192,132,252,0.06);
    border:1px solid rgba(192,132,252,0.2);
    border-radius:10px;padding:1rem 1.2rem;
    font-size:0.9rem;color:#e9d8fd;line-height:1.75;
    white-space:pre-wrap;
}

/* ── Status strip ── */
.status-strip {
    display:flex;gap:0.6rem;flex-wrap:wrap;
    padding:0.7rem 1rem;
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.07);
    border-radius:10px;margin-bottom:1rem;
    align-items:center;
}

/* ── Info banner ── */
.info-banner {
    background:rgba(251,146,60,0.08);
    border:1px solid rgba(251,146,60,0.28);
    border-radius:10px;padding:0.75rem 1rem;
    font-size:0.82rem;color:#fed7aa;line-height:1.55;margin-bottom:1.2rem;
}
.demo-banner {
    background:rgba(250,204,21,0.07);
    border:1px solid rgba(250,204,21,0.3);
    border-radius:10px;padding:0.75rem 1rem;
    font-size:0.82rem;color:#fef08a;line-height:1.55;margin-bottom:1rem;
}
.error-banner {
    background:rgba(248,113,113,0.07);
    border:1px solid rgba(248,113,113,0.28);
    border-radius:10px;padding:0.8rem 1rem;
    font-size:0.87rem;color:#fca5a5;line-height:1.6;
}

/* ── Checklist ── */
.check-ok   { color:#34d399; }
.check-miss { color:#f87171; }

/* ── Streamlit widget overrides ── */
div[data-testid="stTextArea"] textarea {
    background:rgba(255,255,255,0.04)!important;
    border:1px solid rgba(255,255,255,0.1)!important;
    border-radius:10px!important;color:#dde1ee!important;
    font-family:'Inter',sans-serif!important;font-size:0.92rem!important;
}
div[data-testid="stSelectbox"]>div>div,
div[data-testid="stTextInput"] input {
    background:rgba(255,255,255,0.04)!important;
    border:1px solid rgba(255,255,255,0.1)!important;
    border-radius:10px!important;color:#dde1ee!important;
}
div[data-testid="stButton"]>button {
    background:linear-gradient(135deg,#0ea5e9,#6366f1)!important;
    color:#fff!important;border:none!important;border-radius:10px!important;
    font-weight:700!important;font-size:0.93rem!important;
    padding:0.55rem 1.4rem!important;letter-spacing:0.03em!important;
    box-shadow:0 4px 18px rgba(14,165,233,0.25)!important;
    transition:all 0.2s!important;
}
div[data-testid="stButton"]>button:hover {
    transform:translateY(-1px)!important;
    box-shadow:0 6px 26px rgba(14,165,233,0.4)!important;
}
div[data-testid="stDownloadButton"]>button {
    background:rgba(52,211,153,0.15)!important;
    color:#34d399!important;border:1px solid rgba(52,211,153,0.4)!important;
    border-radius:10px!important;font-weight:600!important;font-size:0.85rem!important;
}
label { color:#64748b!important;font-size:0.8rem!important;font-weight:500!important; }
div[data-testid="stExpander"] {
    background:rgba(255,255,255,0.02)!important;
    border:1px solid rgba(255,255,255,0.07)!important;border-radius:10px!important;
}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data
def load_policies() -> list[dict]:
    with open(POLICIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("policies", [])


def match_policies(complaint: str, category: str, channel: str, policies: list[dict]) -> list[dict]:
    """Keyword + category matching — fully local, no API call."""
    complaint_lower = complaint.lower()
    scored = []
    for p in policies:
        cat_hit  = 1 if p.get("category","").lower() == category.lower() else 0
        ch_hit   = 1 if channel.lower() in [c.lower() for c in p.get("channels",[])] else 0
        kw_hits  = sum(1 for kw in p.get("keywords",[]) if kw.lower() in complaint_lower)
        score = kw_hits * 10 + cat_hit * 20 + ch_hit * 5
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


# ═══════════════════════════════════════════════════════════════════════════════
# EVIDENCE SUFFICIENCY ENGINE  (Feature B — fully deterministic, no API)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_evidence_score(
    category: str,
    extracted: dict,
    tx_amount: str,
    tx_date: str,
    tx_ref: str,
    tx_merchant: str,
    tx_status: str,
) -> dict:
    """
    Compute 0-100 evidence completeness score.
    Each field is a binary present/absent — weighted by category.
    Score = sum of weights of present fields.
    """
    weights = EVIDENCE_WEIGHTS.get(category, EVIDENCE_WEIGHTS["default"])

    # Build availability map from UI + AI-extracted fields
    avail = {
        "reference_id":   bool((tx_ref or "").strip() or (extracted.get("reference_id") or "")),
        "amount":         bool((tx_amount or "").strip() or (extracted.get("amount") or "")),
        "date":           bool((tx_date or "").strip() or (extracted.get("date") or "")),
        "merchant":       bool((tx_merchant or "").strip() or (extracted.get("merchant") or "")),
        "payment_status": bool((tx_status or "").strip() or (extracted.get("channel") or "")),
        "screenshot_sms": False,   # cannot detect from text; keep as unavailable
        "bank_statement": False,
        "customer_decl":  True,    # complaint text itself serves as declaration
        "order_id":       bool(extracted.get("reference_id") or ""),
        "delivery_proof": False,
        "refund_ref":     False,
        "complaint_ref":  bool((tx_ref or "").strip()),
        "bank_response":  False,
        "cancel_proof":   False,
    }

    total_weight = sum(weights.values())
    earned = sum(w for f, w in weights.items() if avail.get(f, False))
    score = int(round(earned / total_weight * 100)) if total_weight > 0 else 0

    present  = [f for f in weights if avail.get(f, False)]
    missing  = [f for f in weights if not avail.get(f, False)]

    return {
        "score": score,
        "present": present,
        "missing": missing,
        "weights": weights,
        "avail": avail,
    }


def evidence_color(score: int) -> str:
    if score >= 75: return "#34d399"
    if score >= 50: return "#fbbf24"
    return "#f87171"


def evidence_status(score: int) -> str:
    if score >= 75: return ("b-green",  "✅ Ready for Analyst Review")
    if score >= 50: return ("b-yellow", "⚠ Information Incomplete")
    return             ("b-red",    "🔴 Insufficient Evidence")


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRADICTION / CONSISTENCY ENGINE  (Feature D — local Python)
# ═══════════════════════════════════════════════════════════════════════════════

def run_consistency_checks(
    complaint: str,
    extracted: dict,
    tx_amount: str,
    tx_ref: str,
    tx_status: str,
    category: str,
) -> list[dict]:
    """
    Returns list of {level:'ok'|'warn'|'crit', message: str}.
    Purely deterministic — no API call.
    """
    checks = []
    comp_lower = complaint.lower()
    ext_amt    = (extracted.get("amount") or "").strip().replace("₹","").replace(",","").strip()
    ui_amt     = (tx_amount or "").strip().replace("₹","").replace(",","").strip()
    ui_status  = (tx_status or "").strip().lower()
    ui_ref     = (tx_ref or "").strip()

    # 1. No transaction fields provided at all
    if not tx_amount and not tx_ref and not tx_status:
        checks.append({"level":"warn",
            "message":"No transaction details supplied via the form. Consistency checks are limited to the complaint text only."})

    # 2. Amount mismatch between UI form and AI extraction
    if ext_amt and ui_amt and ext_amt != ui_amt:
        checks.append({"level":"crit",
            "message":f"Amount mismatch — complaint mentions ₹{ext_amt} but form field shows ₹{ui_amt}. Verify the correct figure before proceeding."})
    elif ext_amt or ui_amt:
        checks.append({"level":"ok", "message":"Transaction amount is consistent across available sources."})

    # 3. Failed-payment complaint vs. "success" status
    if category == "failed_payment" and ui_status in ("success","successful","completed","credited"):
        checks.append({"level":"crit",
            "message":"Critical inconsistency: customer reports a failed payment, but the supplied transaction status is 'successful'. Requires manual verification — do not assume fraud."})
    elif category == "failed_payment" and ui_status in ("failed","declined","pending","reversed"):
        checks.append({"level":"ok", "message":"Transaction status aligns with the reported failed-payment complaint."})

    # 4. Duplicate-debit complaint but only one reference provided
    if category == "duplicate_debit" and ui_ref:
        checks.append({"level":"warn",
            "message":"Only one transaction reference supplied. A duplicate-debit dispute requires references for both debits. Ask the customer to provide both UTR/reference numbers."})
    elif category == "duplicate_debit" and not ui_ref:
        checks.append({"level":"warn",
            "message":"No transaction reference supplied. Cannot verify whether two separate debits occurred."})

    # 5. Unauthorized transaction — status says success
    if category == "unauthorized_transaction" and ui_status in ("success","successful","completed"):
        checks.append({"level":"crit",
            "message":"Transaction status shows 'successful' for a reported unauthorized transaction. Escalate immediately; do not reverse without investigation."})

    # 6. Reference ID present in complaint text but not in form
    utr_in_complaint = re.search(r'\b[A-Z0-9]{10,}\b', complaint.upper())
    if utr_in_complaint and not ui_ref:
        checks.append({"level":"warn",
            "message":f"A possible reference ID ('{utr_in_complaint.group()}') was found in the complaint text but was not entered in the Reference ID field. Confirm and log it."})
    elif ui_ref and not utr_in_complaint:
        checks.append({"level":"ok", "message":"Transaction reference provided via the form."})

    # 7. Status field empty
    if not ui_status:
        checks.append({"level":"warn",
            "message":"No payment status supplied. Resolving this complaint without a transaction status record will be difficult."})

    return checks


# ═══════════════════════════════════════════════════════════════════════════════
# SARVAM API  (one call per analysis)
# ═══════════════════════════════════════════════════════════════════════════════

def build_prompt(channel: str, lang_pref: str) -> str:
    """
    Compact prompt — policy matching is done locally, so we don't ask the model
    to fill it in. This keeps output short and avoids finish_reason=length.
    """
    resp_lang = lang_pref if lang_pref != "Auto-detect" else "the customer's own language"
    return (
        f"You are DisputeLens, a payment dispute assistant for Indian analysts. "
        f"You understand English, Hindi, and Hinglish. "
        f"You provide decision-support ONLY — you cannot verify transactions or approve refunds. "
        f"Channel: {channel}. Reply language for draft: {resp_lang}.\n\n"
        f"Analyse the customer complaint below and return ONLY a valid JSON object "
        f"(no markdown fences, no extra text) with exactly these keys:\n"
        f'{{\n'
        f'  "detected_language": "English|Hindi|Hinglish|Mixed",\n'
        f'  "dispute_category": "failed_payment|duplicate_debit|unauthorized_transaction|missing_reference|merchant_dispute|wrong_credit|escalation|recurring_charge|other",\n'
        f'  "complaint_summary": "1-2 sentence English summary",\n'
        f'  "extracted_details": {{\n'
        f'    "amount": "₹XX or null",\n'
        f'    "date": "date string or null",\n'
        f'    "reference_id": "UTR/order ID or null",\n'
        f'    "merchant": "name or null",\n'
        f'    "channel": "UPI|Card|NetBanking|Wallet|Unknown",\n'
        f'    "customer_resolution_requested": "what customer wants or null",\n'
        f'    "stated_facts": ["fact1", "fact2"],\n'
        f'    "uncertainties": ["unclear point1"]\n'
        f'  }},\n'
        f'  "recommended_next_steps": ["step1", "step2", "step3"],\n'
        f'  "escalation_status": "Low|Medium|High|Immediate",\n'
        f'  "escalation_reason": "one sentence",\n'
        f'  "draft_response": "empathetic 2-3 sentence reply in {resp_lang} — do NOT promise refund",\n'
        f'  "key_uncertainties": ["item1", "item2"],\n'
        f'  "information_sufficient": false\n'
        f'}}\n\n'
        f"Rules: stated_facts = only what customer explicitly said; "
        f"information_sufficient=true only if amount+date+reference_id all present; "
        f"never invent transaction details."
    )


def call_sarvam(complaint: str, prompt: str, api_key: str) -> dict:
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": SARVAM_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user",   "content": f"Customer complaint:\n\n{complaint}"},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.15,
    }
    resp = requests.post(SARVAM_ENDPOINT, headers=headers, json=payload, timeout=API_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # Guard: model sometimes returns null content (e.g. context overflow, refusal)
    choice = data.get("choices", [{}])[0]
    raw = choice.get("message", {}).get("content") or ""
    if not raw.strip():
        finish = choice.get("finish_reason", "unknown")
        raise ValueError(f"Sarvam returned empty content (finish_reason={finish}). "
                         f"Try shortening the complaint or retry.")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO FALLBACK RESULT
# ═══════════════════════════════════════════════════════════════════════════════

DEMO_RESULT = {
    "detected_language": "Hinglish",
    "dispute_category": "failed_payment",
    "complaint_summary": "Customer made a UPI payment of ₹1,850 to Swiggy via Google Pay. The bank account was debited, but the merchant's system shows the payment as failed. Customer is seeking clarification and requesting a refund.",
    "extracted_details": {
        "amount": "₹1,850",
        "date": "Not provided",
        "reference_id": None,
        "merchant": "Swiggy",
        "channel": "UPI",
        "customer_resolution_requested": "Refund of debited amount",
        "stated_facts": [
            "₹1,850 debited from bank account via Google Pay",
            "Merchant (Swiggy) reports payment not received",
            "Debit SMS received on customer's phone",
            "Order remains in pending state",
        ],
        "uncertainties": [
            "UTR/transaction reference not provided",
            "Exact date and time not specified",
            "Whether auto-reversal timer has started is unknown",
        ],
    },
    "matched_policy": {
        "id": "POL-001",
        "title": "Failed Payment – Amount Debited",
        "relevant_quote": "If a customer's account is debited but the merchant's system does not show a successful payment, the transaction may be in a 'pending reversal' state.",
        "applicability": "This illustrative rule directly covers the reported scenario. Auto-reversal should occur within 3–5 business days per the synthetic demo rule.",
    },
    "recommended_next_steps": [
        "Obtain the UTR number from the customer's Google Pay transaction history.",
        "Ask customer to share screenshot of bank debit SMS and Swiggy failure screen.",
        "Advise customer to wait 3–5 business days for automatic reversal.",
        "If not reversed, initiate formal dispute with collected evidence.",
    ],
    "escalation_status": "Medium",
    "escalation_reason": "Debit confirmed but merchant did not receive payment; auto-reversal timeline not yet verified.",
    "draft_response": "Namaste! Aapki shikayat hamein mil gayi hai — ₹1,850 aapke account se debit hua lekin Swiggy ko payment nahi mili. Kripya apna UPI UTR number aur debit ka screenshot share karein. Yeh amount 3–5 business days mein automatically reverse ho sakti hai. Agar nahi hua, toh hum aapki taraf se dispute file karenge.",
    "key_uncertainties": [
        "UTR not available — cannot confirm settlement status.",
        "Auto-reversal may already be in progress.",
        "Merchant system status independently unverified.",
    ],
    "information_sufficient": False,
    "_demo_mode": True,
}


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATION  (Feature E — Analyst Case Pack)
# ═══════════════════════════════════════════════════════════════════════════════

def build_text_report(result: dict, ev: dict, checks: list[dict], complaint: str, channel: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "=" * 68,
        "  DISPUTELENS — ANALYST CASE PACK",
        f"  Generated: {now}",
        "  ⚠  DECISION-SUPPORT ONLY. NOT AN OFFICIAL BANK DETERMINATION.",
        "=" * 68,
        "",
        f"1. DISPUTE CATEGORY     : {result.get('dispute_category','—').upper()}",
        f"   LANGUAGE DETECTED    : {result.get('detected_language','—')}",
        f"   ESCALATION PRIORITY  : {result.get('escalation_status','—')}",
        f"   INFORMATION STATUS   : {'Sufficient' if result.get('information_sufficient') else 'Insufficient'}",
        "",
        "2. COMPLAINT SUMMARY",
        "-" * 40,
        result.get("complaint_summary", "—"),
        "",
        "3. REPORTED TRANSACTION DETAILS (customer-stated, not independently verified)",
        "-" * 40,
    ]
    d = result.get("extracted_details", {})
    for k, v in [("Amount", d.get("amount")), ("Date", d.get("date")),
                  ("Reference/UTR", d.get("reference_id")), ("Merchant", d.get("merchant")),
                  ("Channel", d.get("channel")), ("Customer Wants", d.get("customer_resolution_requested"))]:
        lines.append(f"   {k:<18}: {v or 'Not provided'}")
    lines += ["",
        "4. EVIDENCE SUFFICIENCY",
        "-" * 40,
        f"   Score: {ev['score']}/100",
        "",
        "   AVAILABLE:",
    ]
    for f in ev["present"]:
        lines.append(f"   ✓ {FIELD_LABELS.get(f, f)}")
    lines.append("   MISSING:")
    for f in ev["missing"]:
        lines.append(f"   ✗ {FIELD_LABELS.get(f, f)}")
    lines += ["",
        "5. MATCHED POLICY RULE",
        "-" * 40,
    ]
    mp = result.get("matched_policy", {})
    if mp and mp.get("id"):
        lines += [
            f"   [{mp['id']}] {mp.get('title','')}",
            f"   Quote: \"{mp.get('relevant_quote','—')}\"",
            f"   Relevance: {mp.get('applicability','—')}",
        ]
    else:
        lines.append("   No relevant supplied policy rule found.")
    lines += ["",
        "6. CONSISTENCY CHECKS",
        "-" * 40,
    ]
    for c in checks:
        sym = "✓" if c["level"]=="ok" else ("⚠" if c["level"]=="warn" else "✗")
        lines.append(f"   {sym} {c['message']}")
    lines += ["",
        "7. RECOMMENDED NEXT STEPS",
        "-" * 40,
    ]
    for i, s in enumerate(result.get("recommended_next_steps", []), 1):
        lines.append(f"   {i}. {s}")
    lines += ["",
        "8. ESCALATION",
        "-" * 40,
        f"   Status : {result.get('escalation_status','—')}",
        f"   Reason : {result.get('escalation_reason','—')}",
        "",
        "9. KEY UNCERTAINTIES",
        "-" * 40,
    ]
    for u in result.get("key_uncertainties", []):
        lines.append(f"   • {u}")
    lines += ["",
        "10. DRAFT CUSTOMER RESPONSE",
        "-" * 40,
        result.get("draft_response", "—"),
        "",
        "=" * 68,
        "All policy rules cited are ILLUSTRATIVE SYNTHETIC DEMO RULES only.",
        "DisputeLens does not approve refunds or make official determinations.",
        "=" * 68,
    ]
    return "\n".join(lines)


def build_json_report(result: dict, ev: dict, checks: list[dict]) -> str:
    report = {
        "generated_at": datetime.now().isoformat(),
        "tool": "DisputeLens v2.0",
        "disclaimer": "Decision-support only. Not an official bank or regulatory determination.",
        "analysis": result,
        "evidence_sufficiency": {
            "score": ev["score"],
            "present_fields": [FIELD_LABELS.get(f, f) for f in ev["present"]],
            "missing_fields": [FIELD_LABELS.get(f, f) for f in ev["missing"]],
        },
        "consistency_checks": checks,
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# UI RENDER HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def render_status_strip(result: dict, ev: dict) -> None:
    cat   = result.get("dispute_category","—").replace("_"," ").title()
    lang  = result.get("detected_language","—")
    esc   = result.get("escalation_status","—")
    score = ev["score"]
    cls, label = evidence_status(score)
    esc_cls = {"Low":"b-green","Medium":"b-yellow","High":"b-red","Immediate":"b-red"}.get(esc,"b-gray")
    st.markdown(f"""
    <div class="status-strip">
      <span class="badge b-purple">🗂 {cat}</span>
      <span class="badge b-blue">🌐 {lang}</span>
      <span class="badge {esc_cls}">⚡ {esc} Priority</span>
      <span class="badge {cls}">{label}</span>
      {'<span class="badge b-yellow">⚠ Demo Mode</span>' if result.get("_demo_mode") else ''}
    </div>
    """, unsafe_allow_html=True)


def render_evidence_panel(ev: dict) -> None:
    score = ev["score"]
    color = evidence_color(score)
    cls, label = evidence_status(score)
    present = ev["present"]
    missing = ev["missing"]
    weights = ev["weights"]

    st.markdown(f"""
    <div class="panel">
    <div class="panel-title">📊 Evidence Sufficiency</div>
    <div style="display:flex;align-items:center;gap:1rem;margin-bottom:0.5rem">
      <div style="font-size:2rem;font-weight:800;color:{color}">{score}</div>
      <div>
        <div style="font-size:0.75rem;color:#64748b">out of 100</div>
        <span class="badge {cls}" style="font-size:0.7rem">{label}</span>
      </div>
    </div>
    <div class="ev-bar-wrap">
      <div class="ev-bar" style="width:{score}%;background:linear-gradient(90deg,{color},{color}88)"></div>
    </div>
    <div style="font-size:0.72rem;color:#475569;margin-bottom:0.7rem">
      Score = sum of weights of available evidence fields for this dispute category.<br>
      ⚠ This measures information completeness only — NOT fraud probability or refund likelihood.
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div style="font-size:0.75rem;font-weight:700;color:#34d399;margin-bottom:0.3rem">✅ Available</div>', unsafe_allow_html=True)
        for f in present:
            w = weights.get(f, 0)
            st.markdown(f'<div style="font-size:0.83rem;color:#a7f3d0;margin-bottom:0.15rem">✓ {FIELD_LABELS.get(f,f)} <span style="color:#475569;font-size:0.7rem">({w}pts)</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div style="font-size:0.75rem;font-weight:700;color:#f87171;margin-bottom:0.3rem">❌ Missing</div>', unsafe_allow_html=True)
        for f in missing:
            w = weights.get(f, 0)
            st.markdown(f'<div style="font-size:0.83rem;color:#fca5a5;margin-bottom:0.15rem">✗ {FIELD_LABELS.get(f,f)} <span style="color:#475569;font-size:0.7rem">({w}pts)</span></div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_policy_panel(result: dict) -> None:
    mp = result.get("matched_policy", {})
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="panel-title">📜 Matched Policy Rule</div>', unsafe_allow_html=True)
    if mp and mp.get("id"):
        st.markdown(f'<span class="policy-id-tag">{mp["id"]} — {mp.get("title","")}</span>', unsafe_allow_html=True)
        st.markdown(f'<div class="policy-quote">"{mp.get("relevant_quote","—")}"</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="panel-body">{mp.get("applicability","—")}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="panel-body" style="color:#fb923c">No relevant supplied policy rule found. The case may fall outside covered illustrative categories or require manual review.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_consistency_panel(checks: list[dict]) -> None:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="panel-title">🔄 Consistency Checks</div>', unsafe_allow_html=True)
    for c in checks:
        if c["level"] == "ok":
            st.markdown(f'<div class="contra-ok">✓ {c["message"]}</div>', unsafe_allow_html=True)
        elif c["level"] == "warn":
            st.markdown(f'<div class="contra-warn">⚠ {c["message"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="contra-crit">✗ {c["message"]}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_full_report(result: dict, ev: dict, checks: list[dict], complaint: str, channel: str) -> None:
    if result.get("_demo_mode"):
        st.markdown("""<div class="demo-banner">
        ⚠️ <strong>Demo Mode Active:</strong> The analysis below is a pre-written demonstration.
        It does NOT reflect a live Sarvam AI analysis. Add your <code>SARVAM_API_KEY</code> to <code>.env</code>
        and restart the app for live analysis.
        </div>""", unsafe_allow_html=True)

    render_status_strip(result, ev)

    # Row 1: Summary + Details
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(f"""<div class="panel">
        <div class="panel-title">📋 Case Summary</div>
        <div class="panel-body">{result.get("complaint_summary","—")}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        d = result.get("extracted_details", {})
        rows = ""
        for lbl, key in [("💰 Amount","amount"),("📅 Date","date"),
                          ("🔖 Reference","reference_id"),("🏪 Merchant","merchant"),
                          ("📡 Channel","channel"),("🎯 Customer Wants","customer_resolution_requested")]:
            val = d.get(key) or "<span style='color:#475569'>Not provided</span>"
            rows += f"<div style='margin-bottom:0.45rem'><span style='color:#475569;font-size:0.76rem'>{lbl}</span><br><span style='color:#dde1ee;font-size:0.88rem'>{val}</span></div>"
        st.markdown(f"""<div class="panel">
        <div class="panel-title">🔍 Reported Transaction Details</div>
        <div class="panel-body">{rows}</div>
        </div>""", unsafe_allow_html=True)

    # Row 2: Evidence + Policy
    c3, c4 = st.columns(2)
    with c3:
        render_evidence_panel(ev)
    with c4:
        render_policy_panel(result)

    # Row 3: Consistency checks + Next steps
    c5, c6 = st.columns(2)
    with c5:
        render_consistency_panel(checks)
    with c6:
        steps = result.get("recommended_next_steps", [])
        items = "".join(
            f"<div style='display:flex;gap:0.5rem;margin-bottom:0.45rem'>"
            f"<span style='color:#38bdf8;font-weight:700;min-width:1.2rem'>{i+1}.</span>"
            f"<span style='color:#cbd5e1;font-size:0.88rem'>{s}</span></div>"
            for i, s in enumerate(steps)
        )
        st.markdown(f"""<div class="panel">
        <div class="panel-title">✅ Recommended Next Steps</div>
        {items}
        </div>""", unsafe_allow_html=True)

    # Row 4: Draft response
    draft = result.get("draft_response", "")
    if draft:
        st.markdown(f"""<div class="panel">
        <div class="panel-title">✉️ Draft Customer Response</div>
        <div class="draft-box">{draft}</div>
        </div>""", unsafe_allow_html=True)

    # Row 5: Escalation + Uncertainties + Stated facts
    c7, c8, c9 = st.columns(3)
    with c7:
        esc = result.get("escalation_status","—")
        esc_cls = {"Low":"b-green","Medium":"b-yellow","High":"b-red","Immediate":"b-red"}.get(esc,"b-gray")
        st.markdown(f"""<div class="panel">
        <div class="panel-title">⚡ Escalation</div>
        <span class="badge {esc_cls}" style="margin-bottom:0.5rem;display:inline-block">{esc}</span>
        <div class="panel-body" style="font-size:0.85rem">{result.get("escalation_reason","—")}</div>
        </div>""", unsafe_allow_html=True)
    with c8:
        uncert = result.get("key_uncertainties", [])
        items = "".join(f"<div style='color:#fcd34d;font-size:0.85rem;margin-bottom:0.3rem'>• {u}</div>" for u in uncert)
        st.markdown(f"""<div class="panel">
        <div class="panel-title">🔎 Key Uncertainties</div>
        {items}
        </div>""", unsafe_allow_html=True)
    with c9:
        facts = result.get("extracted_details", {}).get("stated_facts", [])
        items = "".join(f"<div style='color:#a7f3d0;font-size:0.85rem;margin-bottom:0.3rem'>• {f}</div>" for f in facts)
        st.markdown(f"""<div class="panel">
        <div class="panel-title">📌 Stated Facts</div>
        {items if items else '<span style="color:#475569;font-size:0.85rem">None extracted.</span>'}
        </div>""", unsafe_allow_html=True)

    # Downloads
    st.markdown("<br>", unsafe_allow_html=True)
    dc1, dc2, _ = st.columns([1, 1, 3])
    txt_report  = build_text_report(result, ev, checks, complaint, channel)
    json_report = build_json_report(result, ev, checks)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    with dc1:
        st.download_button("📄 Download .txt Report", data=txt_report,
                           file_name=f"disputelens_case_{ts}.txt", mime="text/plain",
                           use_container_width=True)
    with dc2:
        st.download_button("📦 Download .json Report", data=json_report,
                           file_name=f"disputelens_case_{ts}.json", mime="application/json",
                           use_container_width=True)

    # Legal footer
    st.markdown("""<div style="margin-top:1.2rem;padding:0.75rem 1rem;
    background:rgba(0,0,0,0.3);border-radius:8px;border:1px solid rgba(255,255,255,0.05);
    font-size:0.72rem;color:#334155;line-height:1.6">
    ⚖️ <strong>Disclaimer:</strong> DisputeLens is a decision-support tool only. It does not verify live
    transactions, approve refunds, reverse payments, or constitute an official bank, RBI, NPCI, Visa,
    or Mastercard determination. All policy rules shown are illustrative synthetic demo examples only.
    Always use your bank's official dispute process for binding resolution.
    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SAMPLE COMPLAINTS
# ═══════════════════════════════════════════════════════════════════════════════

SAMPLES = [
    {
        "label": "💸 Failed UPI Payment",
        "complaint": "Mera Google Pay se ₹1,850 Swiggy ko gaya hai. Mere phone mein debit ka message aaya lekin Swiggy bol raha hai payment nahi mili. Order abhi bhi pending hai. Kya mere paise wapas aayenge?",
        "channel": "UPI", "lang": "Hinglish",
        "tx_amount": "1850", "tx_date": "", "tx_ref": "", "tx_merchant": "Swiggy", "tx_status": "",
    },
    {
        "label": "🔁 Duplicate Debit",
        "complaint": "I was charged twice for the same Amazon order. My HDFC credit card shows two identical charges of ₹3,299 on 20 Oct 2024. Only one order exists (Order #408-1234567). Please reverse the duplicate charge.",
        "channel": "Card / E-Commerce", "lang": "English",
        "tx_amount": "3299", "tx_date": "20 Oct 2024", "tx_ref": "408-1234567", "tx_merchant": "Amazon", "tx_status": "",
    },
    {
        "label": "🚨 Unauthorized Transaction",
        "complaint": "Mere account se ₹12,500 ka ek anjaan transaction hua hai jo maine bilkul nahi ki. Mujhe aaj subah SMS mila — 'Walmart International' ka charge dikh raha hai. Mera card mere paas hai, kisi ko OTP nahi bataya. Card block karna chahiye?",
        "channel": "Card / E-Commerce", "lang": "Hinglish",
        "tx_amount": "12500", "tx_date": "", "tx_ref": "", "tx_merchant": "Walmart International", "tx_status": "success",
    },
    {
        "label": "⚡ Conflicting Status (Demo)",
        "complaint": "My UPI payment of ₹5,000 to FashionHub failed — I got a failure message in PhonePe. But the money has been deducted from my account.",
        "channel": "UPI", "lang": "English",
        "tx_amount": "5000", "tx_date": "25 Oct 2024", "tx_ref": "UTR425001234567", "tx_merchant": "FashionHub", "tx_status": "successful",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # ── Hero header
    st.markdown("""
    <div class="hero">
      <div class="hero-logo">🔍 DisputeLens · Powered by Sarvam AI</div>
      <div class="hero-title">DisputeLens</div>
      <div class="hero-tag">"From customer complaint to evidence-backed dispute case."</div>
      <div class="hero-pills">
        <span class="hero-pill pill-blue">Evidence Sufficiency Engine</span>
        <span class="hero-pill pill-purple">Policy Matching</span>
        <span class="hero-pill pill-green">Consistency Checks</span>
        <span class="hero-pill pill-orange">Analyst Case Pack</span>
        <span class="hero-pill pill-blue">English · Hindi · Hinglish</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── API key detection
    api_key = os.getenv("SARVAM_API_KEY", "").strip()
    api_ok  = bool(api_key and api_key not in ("your_sarvam_api_key_here", "paste_your_key_here"))

    if not api_ok:
        st.markdown("""<div class="info-banner">
        ℹ️ <strong>No API key detected.</strong> Add <code>SARVAM_API_KEY=your_key</code> to
        <code>.env</code> and restart the app. Without it, the Analyze button shows a pre-written demo result.
        </div>""", unsafe_allow_html=True)

    # ── Sample buttons
    st.markdown('<div class="sec-label">⚡ One-Click Example Complaints (Synthetic Demonstration Data)</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    for i, (col, s) in enumerate(zip(cols, SAMPLES)):
        with col:
            if st.button(s["label"], key=f"samp_{i}", use_container_width=True):
                for k in ["complaint_text","channel_sel","lang_sel","tx_amount","tx_date","tx_ref","tx_merchant","tx_status"]:
                    st.session_state.pop(k, None)
                st.session_state.update({
                    "complaint_text": s["complaint"],
                    "channel_sel":    s["channel"],
                    "lang_sel":       s["lang"],
                    "tx_amount":      s["tx_amount"],
                    "tx_date":        s["tx_date"],
                    "tx_ref":         s["tx_ref"],
                    "tx_merchant":    s["tx_merchant"],
                    "tx_status":      s["tx_status"],
                })
                st.session_state.pop("last_result", None)
                st.rerun()

    st.markdown("<hr style='border-color:rgba(255,255,255,0.06);margin:1.2rem 0'>", unsafe_allow_html=True)

    # ── Input form
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown('<div class="sec-label">Customer Complaint</div>', unsafe_allow_html=True)
        complaint = st.text_area("complaint_label", label_visibility="collapsed",
            placeholder="Paste or type the complaint here — English, Hindi, or Hinglish…",
            height=185, key="complaint_text")

        b1, b2 = st.columns([2, 1])
        with b1:
            analyze = st.button("🔍 Analyze Dispute", key="analyze_btn", use_container_width=True)
        with b2:
            if st.button("🗑 Clear", key="clear_btn", use_container_width=True):
                for k in ["complaint_text","tx_amount","tx_date","tx_ref","tx_merchant","tx_status","last_result"]:
                    st.session_state.pop(k, None)
                st.rerun()

    with col_right:
        st.markdown('<div class="sec-label">Transaction Details (Optional — improves accuracy)</div>', unsafe_allow_html=True)
        channel = st.selectbox("Payment Channel",
            ["UPI","Card / E-Commerce","Net Banking","Wallet / Prepaid"], key="channel_sel")
        lang = st.selectbox("Preferred Response Language",
            ["Auto-detect","Hinglish","Hindi","English"], key="lang_sel")
        tx_amount   = st.text_input("Amount (₹)",        placeholder="e.g. 2500",         key="tx_amount")
        tx_date     = st.text_input("Transaction Date",  placeholder="e.g. 20 Oct 2024",  key="tx_date")
        mc1, mc2    = st.columns(2)
        with mc1:
            tx_ref  = st.text_input("Reference / UTR",   placeholder="e.g. UTR4250012…", key="tx_ref")
        with mc2:
            tx_merchant = st.text_input("Merchant",      placeholder="e.g. Swiggy",       key="tx_merchant")
        tx_status   = st.text_input("Transaction Status","",
            placeholder="e.g. success / failed / pending", key="tx_status")

    # ── Run analysis
    if analyze:
        complaint_val = (complaint or "").strip()
        if not complaint_val:
            st.error("⚠️ Please enter a complaint before clicking Analyze.")
            return

        # Enrich complaint with form metadata
        enriched = complaint_val
        extras = []
        if tx_amount:   extras.append(f"Amount: ₹{tx_amount}")
        if tx_date:     extras.append(f"Date: {tx_date}")
        if tx_ref:      extras.append(f"Reference: {tx_ref}")
        if tx_merchant: extras.append(f"Merchant: {tx_merchant}")
        if tx_status:   extras.append(f"Status: {tx_status}")
        if extras:
            enriched += "\n\n[Form data: " + "; ".join(extras) + "]"

        policies = load_policies()
        # Quick keyword pre-match to pick best policy for prompt context
        matched   = match_policies(enriched, "", channel.split("/")[0].strip().lower(), policies)
        best_pol  = matched[0] if matched else None

        st.markdown("<hr style='border-color:rgba(255,255,255,0.06);margin:1.2rem 0'>", unsafe_allow_html=True)
        st.markdown('<div class="sec-label" style="font-size:0.8rem;margin-bottom:0.8rem">📊 DisputeLens Analyst Case Pack</div>', unsafe_allow_html=True)

        if not api_ok:
            result = dict(DEMO_RESULT)
            result["_demo_mode"] = True
        else:
            sys_prompt = build_prompt(channel, lang)
            try:
                with st.spinner("🤖 Analysing with Sarvam AI…"):
                    result = call_sarvam(enriched, sys_prompt, api_key)
                result["_demo_mode"] = False
            except requests.exceptions.Timeout:
                st.markdown('<div class="error-banner">⏱️ <strong>Timeout:</strong> Sarvam API did not respond in 40s. No retries made. Check your connection.</div>', unsafe_allow_html=True)
                return
            except requests.exceptions.ConnectionError:
                st.markdown('<div class="error-banner">🌐 <strong>Network error:</strong> Cannot reach Sarvam API. Check your internet connection.</div>', unsafe_allow_html=True)
                return
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                msgs = {401:"Invalid API key — check SARVAM_API_KEY in .env.",
                        429:"Rate limit reached — wait a moment and try again.",
                        500:"Sarvam server error — try again in a few minutes."}
                st.markdown(f'<div class="error-banner">🔴 <strong>HTTP {code}:</strong> {msgs.get(code, "Unexpected API error.")}</div>', unsafe_allow_html=True)
                return
            except (json.JSONDecodeError, KeyError) as e:
                st.markdown(f'<div class="error-banner">🔧 <strong>Parse error:</strong> AI returned unexpected format. Try again — usually transient. ({type(e).__name__}: {e})</div>', unsafe_allow_html=True)
                return
            except ValueError as e:
                st.markdown(
                    f'<div class="error-banner">🔴 <strong>Empty response from Sarvam:</strong> {e}<br><br>'
                    f'<strong>What to try:</strong> Shorten the complaint text and click Analyze again, '
                    f'or wait 10 seconds if you hit a rate limit. '
                    f'Your API key is valid — this is a model response issue.</div>',
                    unsafe_allow_html=True
                )
                return

        # Re-run local policy match using AI-detected category
        category = result.get("dispute_category", "")
        matched2 = match_policies(enriched, category, channel.split("/")[0].strip().lower(), policies)
        if matched2 and (not result.get("matched_policy",{}).get("id")):
            bp = matched2[0]
            result["matched_policy"] = {
                "id": bp["id"],
                "title": bp["title"],
                "relevant_quote": bp["rule_text"][:200] + "…" if len(bp["rule_text"]) > 200 else bp["rule_text"],
                "applicability": f"This rule covers the '{bp['category']}' scenario identified in the complaint.",
            }

        # Evidence scoring
        extracted = result.get("extracted_details", {})
        ev = compute_evidence_score(category, extracted, tx_amount, tx_date, tx_ref, tx_merchant, tx_status)

        # Consistency checks
        checks = run_consistency_checks(complaint_val, extracted, tx_amount, tx_ref, tx_status, category)

        # Store for persistence
        st.session_state["last_result"] = (result, ev, checks, complaint_val, channel)

        render_full_report(result, ev, checks, complaint_val, channel)

    elif "last_result" in st.session_state:
        st.markdown("<hr style='border-color:rgba(255,255,255,0.06);margin:1.2rem 0'>", unsafe_allow_html=True)
        st.markdown('<div class="sec-label" style="font-size:0.8rem;margin-bottom:0.8rem">📊 DisputeLens Analyst Case Pack</div>', unsafe_allow_html=True)
        render_full_report(*st.session_state["last_result"])

    # Footer
    st.markdown(f"""<div style="text-align:center;padding:1.5rem 0 0.5rem;color:#1e293b;font-size:0.72rem">
    DisputeLens · {APP_VERSION} · Built with Streamlit &amp; Sarvam AI ·
    All policy rules are synthetic illustrations only.
    </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
