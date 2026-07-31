# TokenGuard
Protect your AI API keys. Monitor token usage. Stop abnormal spending before it becomes an expensive incident.
TokenGuard

AI API Security Gateway for Cost Monitoring & API Key Protection

Protect your AI API keys. Monitor token usage. Stop abnormal spending before it becomes an expensive incident.

⸻

🚀 Inspiration

As AI applications become increasingly autonomous, API keys are more valuable than ever.

A leaked OpenAI or Anthropic API key can lead to:

* Unexpected API bills
* Resource abuse
* Service disruption
* Data exposure
* Difficult incident investigation

Current dashboards tell developers what happened after the money is gone.

TokenGuard focuses on preventing the damage before it happens.

⸻

💡 What it does

TokenGuard is a lightweight AI security gateway that sits between AI applications and LLM providers.

Instead of exposing provider API keys directly to frontend applications, all requests pass through TokenGuard.

For every request it:

✅ Protects provider API keys

✅ Tracks token usage

✅ Estimates API cost

✅ Detects abnormal usage

✅ Blocks suspicious requests

✅ Generates security incidents

⸻

✨ Features

🔐 API Key Protection

Provider API keys never reach the frontend.

Browser
      │
      ▼
TokenGuard Proxy
      │
      ▼
OpenAI / Anthropic

Keys remain securely stored on the server.

⸻

📊 Token Cost Dashboard

Monitor:

* Total tokens
* Input tokens
* Output tokens
* Estimated cost
* Request history
* Model usage

⸻

🚨 Spending Guard

Configure limits such as

* Daily budget
* Per-request budget
* Maximum token count

When limits are exceeded TokenGuard automatically blocks requests.

⸻

🤖  Deterministic Security Detection

Detects

* Abnormally high token usage
* Burst requests
* Suspicious request frequency
* Potential compromised credentials

## Low-overhead by design

TokenGuard does not require an additional LLM call to analyse each request.

Usage monitoring, cost calculation, rate limiting, budget enforcement and
credential-pattern detection are performed locally using deterministic rules.

This means TokenGuard adds no additional AI-token consumption to the normal
request path.
⸻

📋 Incident Log

Every blocked request is logged with

* Timestamp
* Risk level
* Reason
* Estimated prevented cost

🏗 Architecture
                    User

                     │

                     ▼

          React Frontend Dashboard

                     │

                     ▼

         TokenGuard API Gateway

      ┌──────────┬────────────┐
      │          │            │

Usage Monitor  Risk Engine  Secret Manager

      │          │            │

      └──────────┴────────────┘

                     │

                     ▼

           OpenAI / Anthropic API

⚙ Tech Stack

Frontend

* React
* Vite
* TypeScript

Backend

* FastAPI (or Express)
* Python

Database

* Supabase PostgreSQL

Charts

* Recharts

Deployment

* Vercel
* Modal / Railway

AI

* OpenAI-compatible API

🛡 Security Workflow
Incoming Request

        │

        ▼

Validate Request

        │

        ▼

Estimate Token Cost

        │

        ▼

Risk Analysis

        │

 ┌──────┴────────┐

 │               │

Safe          Suspicious

 │               │

 ▼               ▼

Forward      Block Request

 │               │

 ▼               ▼

Record Usage  Create Incident
🎯 Example Scenario

Developer accidentally exposes an API key.

An attacker starts sending thousands of requests.

Without TokenGuard
API Bill

$0

↓

$520

↓

Developer notices too late.

With TokenGuard
Abnormal traffic detected

↓

Budget exceeded

↓

API key temporarily suspended

↓

Incident generated

↓

Estimated loss prevented
📈 Roadmap

MVP

* API proxy
* Token monitoring
* Cost estimation
* Dashboard
* Spending guard

Next

* Multi-provider support
* Prompt Injection Detection
* Secret Leakage Detection
* GitHub Secret Scanner
* Slack/Discord Alerts
* Email Notifications

Future

* AI-powered anomaly detection
* Organization policy engine
* Team analytics
* Enterprise dashboard
* MCP security gateway

⸻

🎥 Demo

1. Send an AI request

↓

2. TokenGuard records token usage

↓

3. Dashboard updates in real time

↓

4. Simulate abnormal traffic

↓

5. TokenGuard blocks requests

↓

6. Incident appears in dashboard

⸻

📊 Judging Criteria

✅ Technical Execution

* Secure API proxy
* Real-time monitoring

✅ Security Impact

* API key protection
* Spending prevention

✅ Product Thinking

* Developer-first workflow

✅ AI Autonomy

* Automatic anomaly detection

✅ Responsible AI

* Human approval before high-risk requests

👥 Team
Name

Role

Coral Han

Product Lead · Full Stack Developer

TBD

Backend / Security

TBD

Frontend / Infrastructure

🌍 Why TokenGuard?

AI applications are becoming autonomous.

Autonomous systems require autonomous security.

TokenGuard helps developers build AI applications that are not only intelligent—but also secure, observable, and cost-aware.

