# Test Queries by Agent (MEGATRADE_DEMO)

Copy-paste queries for exercising every agent path against the demo SAP B1
database (`MEGATRADE_DEMO` on MSSQL — tables `OCRD`, `OITM`, `OINV`, `INV1`,
`ORDR`, `OWHS`). Use them in the chat UI, or run the automated harness
`test_agent_queries.py` at the repo root (which also checks routing + errors).

The pipeline classifies each question into one intent and routes it to the
matching agent: **Lookup / Aggregation / Trend / Comparative** (analytical
text-to-SQL), **RCA**, **Document** (RAG), **Hybrid**, **Web**.

---

## Before you start

- **Demo data is dated early January 2025.** Relative ranges like "this year" /
  "this quarter" anchor to the current date and return **empty** results. For
  analytical queries that should return rows, phrase with an **explicit year**
  (e.g. "…in 2025"). See the ✅-marked variants below.
- **RAG and Hybrid need an uploaded document.** Upload `sample_company_policy.md`
  (repo root) via the Documents page / `POST /api/v1/documents/upload` and wait
  until its status is `ready` before running the Document/Hybrid queries.
- A Celery **worker must be running** for document embedding (`./run_local.sh
  --workers` or a manual worker on queues `default,discovery`).

---

## 🔍 Analytical — Lookup (retrieve a specific record/value)

- Show me the details for customer C20000.
- List all open sales orders.
- What's the credit limit and current balance for customer C20000?
- Give me the contact details for the business partner "Mega Retail".

## 📊 Analytical — Aggregation (SUM / COUNT / AVG)

- What is our total revenue this year?
- How many open A/R invoices do we have?
- What is the total outstanding receivables across all customers?
- ✅ What was our total invoiced revenue in 2025?   *(explicit year → returns data)*
- ✅ What is the average invoice value in 2025?

## 📈 Analytical — Trend (time-series / period-over-period)

- Show the monthly revenue trend for the last 6 months.
- How have sales orders trended week over week this quarter?
- ✅ Show the monthly sales trend across 2025.

> Note: the demo DB has only one month (Jan 2025) of data, so trends will report
> a "single data point". This is a data limitation, not a bug — load multi-month
> data to see a real trend line.

## 📊 Analytical — Comparative (compare groups / periods)

- Top 10 customers by revenue this year.
- Compare sales this quarter versus last quarter.
- ✅ Top 5 customers by revenue in 2025.
- ✅ Compare invoiced revenue between Q1 2025 and Q2 2025.

## 🧭 RCA — Root cause analysis ("why" questions)

- Why did sales drop last month?
- What is driving the spike in overdue invoices?
- Why did revenue from our top customer decline?

> Known issue: RCA's generated SQL sometimes uses `UNION` for period-over-period
> comparison, which the SQL validator currently rejects ("Only SELECT statements
> are allowed (got Union)"), so this path can error intermittently.

## 📄 Document / RAG — answered from uploaded documents

*(Upload `sample_company_policy.md` first.)*

- What is our customer payment terms policy?
- Summarize the return and refund policy.
- What does our credit policy say about new customers?
- What are the purchase-order approval thresholds in our procurement policy?

## 🔀 Hybrid — database data blended with document/policy knowledge

*(Upload `sample_company_policy.md` first.)*

- Are any open invoices past the payment terms stated in our policy?
- Which customers are exceeding the credit limit defined in our credit policy?
- Show overdue customers and what our collections policy says we should do.

> The "payment terms" query blends in a single turn. The "credit limit" query
> currently asks a clarifying question first ("which customers?"); answer it
> (e.g. *"all customers, use 50000 as the threshold"*) to continue. See the
> two-turn flow below.

## 🌐 Web — current external/public information

- What is the latest SAP Business One release version?
- What is the current industry benchmark for DSO in distribution?
- What are current best practices for inventory turnover in wholesale trade?

---

## Multi-turn flows (conversation memory)

Ask these as consecutive turns in the **same** conversation:

**Follow-up / context carry-over**

1. What was our total invoiced revenue in 2025?
2. Now break that down by customer.
3. Just the top 3.

**Hybrid "clarify then blend"**

1. Which customers are exceeding the credit limit defined in our credit policy?
2. *(agent asks which customers)* → Use 50000 as the credit limit threshold for all customers.

**Meta / conversational** (answered without hitting the database)

- What did I just ask?
- How many questions have I asked?
- Who are you and what can you do?

---

## Disambiguation spot-checks

Confirms the classifier doesn't confuse internal data with the web:

- "the latest SAP B1 release" → **Web**, vs "our latest sales order" → **Lookup**
- "what is our payment policy?" → **Document**, vs "what are this customer's
  payment terms?" → **Lookup**
