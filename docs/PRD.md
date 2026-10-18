# RetailNova: product requirements

**Theme:** Retail & Commerce: Intelligent Customer and Business Experiences (AI Builder Cup 2026)
**One line:** Every shopper conversation is a demand signal.

## 1. Problem
Retailers forecast demand from what they **sold**. When an item is out of stock, the demand behind it never shows up in the sales data.

1. Out-of-stock items record zero sales.
2. The forecast concludes the item "doesn't sell".
3. The next order is smaller, so the gap repeats every season.

The **unmet demand** is the shopper who asked for a maroon silk saree before Diwali and walked away. That demand is spoken in chats, searches and store conversations, then thrown away.

## 2. Users
| User | Job to be done | Today | With RetailNova |
|---|---|---|---|
| **Priya**, a shopper in Chennai | Find the right festive outfit within budget and pick it up nearby | Generic search; "out of stock" is a dead end | Conversational help in her own language, real stock across stores, reserve or notify-me |
| **Arjun**, a store / category manager | Get the right stock into the right store before Diwali | Spreadsheets of past sales; blind to lost demand | A live Demand Radar of what customers asked for; AI-proposed transfers and reorders with evidence; one-click approval |

## 3. The loop (core experience)
1. Priya asks the **Concierge**, in text (English, Hinglish or Tamil) or with a photo.
2. The Concierge answers **only from the real catalog and live inventory**. It shows stock at each store, offers alternatives, and lets her reserve or ask to be notified.
3. A **Signal Extractor** turns the conversation into a structured demand signal: category, attributes, price band, outcome and reason.
4. Arjun's **Demand Radar** updates live. It shows unmet demand next to two forecasts: one built from sales only, and one "demand-sensed" (sales plus captured unmet demand), both from BigQuery TimesFM.
5. The **Ops Planner** gathers forecast, signals, inventory and transfer options in parallel. It then proposes **transfers and reorders** with evidence, confidence and the revenue protected.
6. Arjun **approves**. Inventory updates, and Priya is notified: "Reserved for you at T. Nagar". The loop closes.

## 4. Scope
**P0, the submission:**
- Concierge chat with text and image search
- Grounding validator
- Reserve and notify-me
- Live signal extraction
- Demand Radar with two-forecast chart, live feed and top gaps
- Ops plan with streamed steps, proposals and approve
- Notifications
- Judge Mode landing page, Live Loop split-screen view, demo reset
- Backtest and concierge evals
- Deployed on Firebase Hosting and Cloud Run

**P1, only if P0 is green by 15:30 on 18 Oct:**
- Google Search–grounded trend step
- Model Armor prompt screening
- Cloud Trace
- Memory Bank for shopper preferences
- Nightly demo reset with Cloud Scheduler

**P2, roadmap:**
- Voice shopping (Gemini Live)
- Virtual try-on
- Universal Commerce Protocol checkout
- Agent-to-agent supplier agent
- WhatsApp channel
- Shelf photo audits

**Non-goals:**
- Real payments
- Real customer data
- Authentication (judges need zero friction)
- Automated actions without human approval

## 5. Success metrics (measured, reported honestly)
| Area | Metric |
|---|---|
| Forecast | Backtest WAPE against true demand: sales-only vs demand-sensed, across signal capture rates of 10–50% |
| Business | Stockout days and lost revenue (₹) under the same replenishment policy, A vs B |
| Concierge | SKU grounding rate (target 100%), constraint adherence, correct refusals, signal-extraction accuracy |
| Experience | Chat turn latency p50/p95; plan latency; time-to-value for a first-time judge under 2 minutes |

## 6. Responsible AI
- **No personal data.** Signals are aggregated and anonymized before analytics, and BigQuery holds no personal data. Consent for conversation analytics, framed against India's DPDP Act 2023, is on the roadmap.
- **A human approves every inventory action.** The AI supports the decision; it doesn't make it.
- **Grounding is enforced on the server.** The assistant also refuses off-topic requests and prompt injection, and there are input limits and rate limits.
- **All data is synthetic** and labelled as such everywhere.
