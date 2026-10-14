# Northstar Commerce demo

Northstar Commerce is a small Python and TypeScript codebase included with Regora. It contains authentication, users, checkout, payments, a Stripe boundary, and database writes. It also includes an intentional import cycle and an unused legacy function so Regora has realistic architecture findings to surface.

Regora analyzes this code as text. It does not install its dependencies or execute it.

## Five-minute walkthrough

1. [Start Regora locally](../README.md#run-locally) and open [http://localhost:3000](http://localhost:3000).
2. Select **Try sample repository**.
3. Wait until indexing reaches **Ready**. The first run can take longer while local AI models download.
4. Complete the checks below in the workspace.

### 1. Find the authentication flow

Ask the assistant:

> Where is authentication handled?

Expected result:

- The answer cites `api/middleware.py`, `services/auth.py`, and `utils/tokens.py`.
- The dependency graph connects `require_user` to `AuthService.authenticate` and then to `verify_token`.
- Selecting a citation opens the relevant source lines.

### 2. Trace checkout to the database

Ask:

> Trace POST /checkout to the database.

Expected result:

- The trace starts at `POST /checkout` in `api/routes.py`.
- It passes through `OrderService.checkout` in `services/orders.py`.
- The evidence includes `get_session`, the `Order` entity, `session.add`, and `session.commit`.

### 3. Check a change's impact

Ask:

> What breaks if PaymentService changes?

Expected result:

- Regora identifies `OrderService.checkout` as a dependent.
- The affected path reaches the checkout API route.
- The answer reports a potential blast radius and links it to static graph evidence.

## Explore the interface

- **Architecture** groups symbols into codebase components.
- **Dependencies** shows symbol-level calls, imports, inheritance, and data access.
- **Overview** summarizes languages, connected components, cycles, and unresolved relationships.
- **Inspector** shows source, callers, callees, and local graph neighborhoods.
- **Analyze Impact** estimates the files, routes, and dependent symbols affected by a change.

You can also try:

- `What could break if I modify verify_token?`
- `Trace checkout to StripeClient.`
- `Which API endpoints depend on UserService?`
- `Where is the database updated when an order is created?`

The TypeScript client contains a visible `fetch('/checkout')` call. Regora does not automatically connect that request to the Python endpoint because deployment routing can rewrite paths. This is an intentional example of the product preferring incomplete evidence over a fabricated relationship.

For installation, configuration, and troubleshooting, see the [main README](../README.md). For measured demo results, see [evaluation-results.json](../docs/evaluation-results.json).
