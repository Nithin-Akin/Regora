# Northstar Commerce

This source-analysis fixture represents a small commerce backend and TypeScript client. RepoGraph never runs it. Runtime dependencies are intentionally not installed. The pricing/discounts import cycle and unreferenced legacy coupon are deliberate analysis examples.

Try:
- Where is authentication handled?
- What could break if I modify verify_token?
- Trace POST /checkout to the database.
- Trace checkout to StripeClient.
- What breaks if PaymentService changes?
- Which API endpoints depend on UserService?
- Where is the database updated when an order is created?

The frontend fetch path is visible in source but is not automatically joined to a backend route: deployments can rewrite paths, so claiming that relationship would exceed the evidence.
