# TokenGuard

> Protect AI API keys. Monitor token usage. Block abnormal spending before it becomes an incident.

**Built for the Cursor Cybersecurity London Hackathon — 1 August 2026, London.**

TokenGuard is a lightweight security and cost-control gateway for AI applications.

It keeps provider API keys away from the frontend, tracks token usage and estimated cost, detects suspicious request patterns, and automatically blocks activity that exceeds configured security or spending policies.

---

## Hackathon

This project was created for the **Cursor Cybersecurity London Hackathon**, a one-day event focused on building infrastructure for AI-native cybersecurity.

The hackathon explores areas including:

- AI security
- Incident response
- Threat detection
- Autonomous security operations
- Infrastructure security
- Security tooling for developers
- Safe and responsible AI systems

TokenGuard was designed around the hackathon themes of:

- AI infrastructure security
- Credential protection
- Automated threat response
- Human oversight
- Real-world developer tooling

---

## The Problem

AI applications rely on valuable provider credentials such as OpenAI, Anthropic, Gemini, or other model API keys.

These credentials can be exposed through:

- Frontend source code
- Public repositories
- Client-side network requests
- Logs and error messages
- Misconfigured environment files
- Compromised applications

Once a key is leaked or abused, an attacker may generate large volumes of requests before the developer notices.

This can lead to:

- Unexpected API bills
- Exhausted usage quotas
- Application downtime
- Service abuse
- Difficult incident investigation

Provider billing dashboards are useful for observing usage, but they may only show the problem after the requests have already happened.

TokenGuard adds an application-level enforcement layer before abnormal usage becomes expensive.

---

## The Solution

TokenGuard sits between an AI application and its model provider.

```text
AI Application
      |
      v
TokenGuard Gateway
      |
      +--> Usage Monitor
      |
      +--> Cost Calculator
      |
      +--> Risk Engine
      |
      +--> Incident Logger
      |
      v
AI Model Provider

The provider API key remains on the backend.

Every incoming request is evaluated against configurable policies before being forwarded to the provider.

TokenGuard can:

Keep provider credentials server-side
Monitor input and output token usage
Estimate model cost
Enforce per-request limits
Enforce daily spending limits
Detect suspicious request bursts
Block high-risk requests
Suspend a compromised project
Create security incident records
Display activity in a live dashboard
Core Principle
We do not spend more AI tokens to protect AI tokens.

TokenGuard does not require an additional LLM call to analyse every request.

The normal security path uses deterministic logic for:

Token estimation
Cost calculation
Rate limiting
Budget enforcement
Request-volume checks
Project suspension
Incident generation

This keeps additional LLM token consumption at:

0 additional AI tokens

The user request is forwarded to the model provider only once.

Key Features
Secure Backend Proxy

The provider API key never reaches the browser.

Frontend
   |
   | application request
   v
TokenGuard Backend
   |
   | provider API key stored server-side
   v
Model Provider

The frontend communicates only with the TokenGuard API.

The real provider credential is stored in a backend environment variable or secret-management service.

Token Usage Monitoring

TokenGuard records:

Input tokens
Output tokens
Total tokens
Model used
Request timestamp
Request status
Risk level

After a provider response, TokenGuard reads the usage metadata returned by the provider.

For mock mode or pre-request estimates, it can use a lightweight local approximation.

Cost Monitoring

TokenGuard maps model usage to configured input and output prices.

Example:

Input tokens: 1,200
Output tokens: 300
Estimated cost: $0.00036

Cost calculations are performed locally and do not require another model request.

Cost figures shown by the prototype are estimates based on the configured model pricing and are not presented as provider invoices.

Spending Guard

Projects can define limits such as:

Per-request budget: $0.05
Daily budget: $1.00
Maximum request tokens: 4,000
Maximum requests per minute: 8

When a request violates a policy, TokenGuard can:

Block request
      |
      v
Create incident
      |
      v
Suspend project
      |
      v
Require manual reset
Suspicious Burst Detection

TokenGuard monitors request velocity.

Example:

Normal traffic:
2 requests per minute
      |
      v
Allowed
Suspicious traffic:
12 requests in a few seconds
      |
      v
Burst detected
      |
      v
Requests blocked
      |
      v
Project suspended

This simulates a common credential-compromise scenario in which a leaked key is used repeatedly over a short period.

Security Incident Log

Blocked requests create incident records containing:

Incident severity
Detection reason
Action taken
Timestamp
Estimated prevented cost
Project status

Example:

{
  "severity": "critical",
  "reason": "Suspicious request burst detected.",
  "action_taken": "Request blocked and project suspended.",
  "prevented_cost_usd": 0.048,
  "status": "suspended"
}

Raw provider API keys should never be stored in incident records.

Live Dashboard

The dashboard displays:

Total requests
Blocked requests
Total tokens
Estimated actual cost
Project status
Recent API activity
Security incidents
Risk level
Allowed and blocked decisions
Demo Flow

The hackathon demo follows one clear security story.

1. Normal Request

A developer sends a legitimate AI request.

Request submitted
      |
      v
Policy checks passed
      |
      v
Request forwarded
      |
      v
Model response returned
      |
      v
Usage and cost recorded

Expected result:

Decision: ALLOW
Risk: LOW
Project status: ACTIVE
2. Compromised Credential Simulation

The user selects:

Simulate suspicious burst

The system generates a burst of high-volume requests.

Rapid request activity
      |
      v
Velocity threshold exceeded
      |
      v
Risk marked critical
      |
      v
Subsequent requests blocked
      |
      v
Project suspended
      |
      v
Incident created

Expected result:

Decision: BLOCK
Risk: CRITICAL
Project status: SUSPENDED
3. Incident Review

The dashboard shows:

Number of blocked requests
Detection reason
Security severity
Estimated prevented cost
Time of incident
Automated action taken
4. Manual Reset

The developer reviews the incident and resets the demo project.

SUSPENDED
      |
      v
Manual reset
      |
      v
ACTIVE
Architecture
┌─────────────────────────────┐
│       React Frontend        │
│                             │
│  - Secure Playground        │
│  - Usage Dashboard          │
│  - Incident View            │
│  - Attack Simulation        │
└──────────────┬──────────────┘
               |
               | HTTPS / JSON
               v
┌─────────────────────────────┐
│      TokenGuard Gateway     │
│                             │
│  - Request Validation       │
│  - Server-Side API Key      │
│  - Token Estimation         │
│  - Cost Calculation         │
│  - Policy Enforcement       │
│  - Rate Limiting            │
│  - Incident Generation      │
└───────┬───────────┬─────────┘
        |           |
        |           |
        v           v
┌─────────────┐  ┌──────────────┐
│ Usage Store │  │ Risk Engine  │
│             │  │              │
│ Requests    │  │ Token limit  │
│ Costs       │  │ Cost limit   │
│ Incidents   │  │ Burst limit  │
└─────────────┘  └──────────────┘
        |
        v
┌─────────────────────────────┐
│     AI Model Provider       │
│                             │
│  OpenAI-compatible API      │
└─────────────────────────────┘
Security Workflow
Incoming request
      |
      v
Validate payload
      |
      v
Estimate token usage
      |
      v
Estimate request cost
      |
      v
Check project status
      |
      v
Check token limit
      |
      v
Check per-request budget
      |
      v
Check daily budget
      |
      v
Check request velocity
      |
      +--------------------------+
      |                          |
      v                          v
Request safe                Request suspicious
      |                          |
      v                          v
Forward to provider          Block request
      |                          |
      v                          v
Read usage metadata          Create incident
      |                          |
      v                          v
Record actual cost           Suspend if critical
      |
      v
Return response
Tech Stack
Frontend
React
Vite
JavaScript
CSS
Backend
Python
FastAPI
Pydantic
HTTPX
Data

Hackathon MVP:

In-memory usage store

Optional extension:

Supabase PostgreSQL
AI Provider
Mock provider mode for reliable demonstrations
Optional OpenAI-compatible API integration
Developer Tooling
Cursor
GitHub
REST API
Swagger / OpenAPI
Repository Structure
tokenguard/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── provider.py
│   │   ├── pricing.py
│   │   ├── risk.py
│   │   └── store.py
│   ├── tests/
│   │   └── test_risk.py
│   ├── .env.example
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   ├── index.css
│   │   └── main.jsx
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── .gitignore
└── README.md
API Endpoints
Health Check
GET /health

Example response:

{
  "status": "ok",
  "service": "TokenGuard"
}
Send Secure AI Request
POST /chat

Example request:

{
  "prompt": "Explain why API keys should stay server-side.",
  "max_output_tokens": 300
}

Example allowed response:

{
  "request_id": "example-request-id",
  "answer": "API keys should remain on the server...",
  "input_tokens": 42,
  "output_tokens": 78,
  "estimated_cost_usd": 0.000053,
  "risk_level": "low",
  "decision": "allow",
  "reason": "Request is within configured limits."
}

Example blocked response:

{
  "request_id": "example-request-id",
  "answer": null,
  "input_tokens": 8200,
  "output_tokens": 0,
  "estimated_cost_usd": 0.052,
  "risk_level": "high",
  "decision": "block",
  "reason": "Request exceeds the configured token limit."
}
Get Dashboard Data
GET /dashboard

Returns:

Current project status
Total requests
Blocked requests
Token totals
Cost total
Recent usage
Security incidents
Simulate Compromised Credential
POST /simulate-burst

Example response:

{
  "sent": 12,
  "blocked": 4,
  "status": "suspended"
}
Reset Demo
POST /reset

Example response:

{
  "status": "reset"
}
Environment Variables

Create:

backend/.env

Example:

MOCK_PROVIDER=true

PROVIDER_API_KEY=
PROVIDER_MODEL=gpt-4o-mini
PROVIDER_BASE_URL=https://api.openai.com/v1

DAILY_BUDGET_USD=1.00
PER_REQUEST_BUDGET_USD=0.05
MAX_REQUEST_TOKENS=4000
BURST_LIMIT_PER_MINUTE=8
Important

Never place the provider key in:

frontend/.env

Never commit:

backend/.env

Only commit:

backend/.env.example
Run Locally
Clone the Repository
git clone <repository-url>
cd tokenguard
Start the Backend
cd backend

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env

uvicorn app.main:app --reload --port 8000

Backend:

http://localhost:8000

Swagger documentation:

http://localhost:8000/docs
Start the Frontend

Open another terminal:

cd frontend

npm install

cp .env.example .env

npm run dev

Frontend:

http://localhost:5173
Mock Mode

The application uses mock mode by default:

MOCK_PROVIDER=true

Mock mode allows the full security flow to run without:

A real provider API key
External provider availability
Additional API cost
Risk of exposing a real credential during the demo

It supports:

Normal request simulation
Usage recording
Cost calculation
Risk decisions
Burst simulation
Incident generation
Project suspension
Real Provider Mode

To connect an OpenAI-compatible provider:

MOCK_PROVIDER=false
PROVIDER_API_KEY=your-server-side-api-key
PROVIDER_MODEL=your-selected-model
PROVIDER_BASE_URL=https://api.openai.com/v1

The key must remain server-side.

Do not expose it in:

Browser code
React environment variables
Public repositories
Screenshots
Logs
Demo recordings
Threat Model

The MVP focuses on:

Provider-key exposure through frontend architecture
Excessive token consumption
Unexpected cost growth
Rapid request bursts
Misuse through the protected application route

The MVP does not claim to prevent:

Complete backend infrastructure compromise
Theft of a provider key outside TokenGuard
Every possible distributed attack
Provider-account takeover
Supply-chain compromise
Advanced behavioural attacks
All prompt-injection attacks

TokenGuard should be considered one layer within a broader security architecture.

Responsible Security Design

TokenGuard follows several principles:

Least Exposure

Provider credentials remain on the backend.

Minimal Data Retention

The production design should avoid storing raw prompts unless explicitly required.

No Secret Logging

Secrets must not appear in:

Logs
Incident records
Frontend responses
Analytics
Screenshots
Transparent Decisions

Every blocked request includes a clear reason.

Human Oversight

Critical incidents suspend the project until reviewed or reset.

Safe Demonstration

All attack simulations use fake requests and fake credentials.

Judging Criteria Alignment
Technical Execution
Secure backend proxy
Token and cost accounting
Policy engine
Automated blocking
Incident generation
Live dashboard
Security Impact
Reduced client-side credential exposure
Detection of abnormal API usage
Financial damage containment
Automated response workflow
Product Thinking
Clear target user
Focused one-day MVP
Developer-friendly workflow
Real-world AI infrastructure problem
AI Autonomy
Automated monitoring
Automated policy decisions
Automated incident creation
Automated project suspension
UX Clarity
Clear project status
Visible risk level
Transparent block reason
Simple attack simulation
Immediate dashboard feedback
Real-World Applicability
AI application teams
Startups using paid model APIs
Internal AI tools
Agentic applications
Multi-provider AI infrastructure
Safety and Responsible AI
No additional security LLM call
Human review after suspension
Server-side secrets
Explicit limitations
Deterministic and explainable controls
Why TokenGuard?

Provider dashboards help developers see usage.

TokenGuard is designed to enforce policies before abnormal traffic becomes costly.

Provider dashboard:
Observe usage
TokenGuard:
Protect
Monitor
Detect
Block
Respond

TokenGuard turns AI billing and usage metadata into an active security signal.

Future Roadmap
Short-Term
Supabase persistence
Authentication
Project-specific policy configuration
Model-specific tokenisation
Configurable pricing
Improved dashboard charts
Email or Slack alerts
Medium-Term
Multi-provider support
Managed secret storage
Key rotation workflows
Team workspaces
Audit export
Provider failover
IP and device-based controls
Long-Term
Behavioural usage baselines
Organization-wide policy engine
Self-hosted deployment
Bring-your-own-cloud support
MCP gateway integration
AI agent tool-call controls
Enterprise security reporting
Team
Name	Role
Coral Han	Product, Full-Stack Development, Frontend, Demo and Pitch
Teammate	Backend and Infrastructure
Teammate	Security Logic and Data
Hackathon Scope

For the Cursor Cybersecurity London Hackathon, the core MVP is deliberately limited to:

One secure AI request through a backend gateway
One live token and cost dashboard
One deterministic policy engine
One simulated compromised-credential scenario
One automated blocking and incident-response flow

Features outside this scope are treated as stretch goals.

Disclaimer

TokenGuard is a hackathon prototype.

It is not currently production-ready and should not be used as the sole security control for real API credentials or production AI workloads.

A production implementation would require:

Managed secret storage
Strong authentication and authorization
Encryption
Persistent audit logging
Security testing
Provider-specific tokenisation
Key rotation
Infrastructure hardening
Privacy and compliance review
Built With
Cursor
React
Vite
FastAPI
Python
JavaScript
REST APIs
OpenAI-compatible provider integration
Built For

Cursor Cybersecurity London Hackathon

Date: 1 August 2026
Location: London, United Kingdom
Theme: Building infrastructure for AI-native cybersecurity

Final Message

AI applications need more than intelligence.

They also need:

Credential protection
Cost visibility
Usage controls
Automated incident response
Human oversight

TokenGuard helps developers:

Protect keys. Control spend. Respond before abnormal usage becomes an expensive incident.

