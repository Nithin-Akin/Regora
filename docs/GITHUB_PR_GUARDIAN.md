# GitHub PR Guardian

Regora can review every pull request update automatically. A signed GitHub webhook queues an isolated review, builds a temporary graph from the exact pull request head, maps changed lines and downstream impact, updates one persistent pull request comment, and publishes the `Regora / PR Guardian` commit status.

The review includes changed symbols, downstream files and routes, connected tests, coverage gaps, architecture quality gates, and exact source locations. Regora reports a failed status when `.regora.yml` has an error-level violation. Other attention items remain visible in a successful review because they are guidance rather than enforced policy.

## Create the GitHub App

Create a GitHub App under **GitHub Settings → Developer settings → GitHub Apps → New GitHub App**.

Set the webhook URL to:

```text
https://YOUR_PUBLIC_HOST/api/github/webhooks
```

Generate a webhook secret and enable these repository permissions:

| Permission | Access |
| --- | --- |
| Contents | Read-only |
| Pull requests | Read-only |
| Issues | Read and write |
| Commit statuses | Read and write |
| Metadata | Read-only |

Subscribe to **Push**, **Pull request**, and **Issue comment** events. Generate and download a private key, then install the App on the repositories Regora should review. Push events keep the indexed default branch synchronized while the existing graph remains available to readers.

Add the App values to `.env`. Store the private key on one line with literal `\n` separators:

```dotenv
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----
GITHUB_WEBHOOK_SECRET=replace-with-the-webhook-secret
```

Restart the application:

```bash
docker compose up -d --build
docker compose logs -f backend pull-request-worker
```

GitHub must reach the webhook over public HTTPS. For local testing, expose port 8000 through a trusted HTTPS tunnel and use its `/api/github/webhooks` URL.

## Use it

First index the same GitHub repository in Regora. The first valid webhook binds that indexed repository to the GitHub App installation.

Open the repository workspace and select **Guardian**. The Integration Center reports authentication, signed webhook, and installation binding health without returning credentials to the browser. It also shows the 50 most recent reviews with their commit, command, result, GitHub comment, and failure message.

Regora automatically reviews pull requests when they are opened, reopened, updated, or marked ready for review. Draft pull requests are skipped. Repository owners, members, and collaborators can also add one of these comments:

```text
/regora review
/regora impact
/regora explain
```

Repeated updates edit the same Regora comment instead of adding new comments. GitHub delivery IDs are retained for 24 hours, so retried webhook deliveries do not create duplicate jobs. Regora retains up to 200 Guardian run records per repository and returns the newest 50 in the Integration Center.

Failed runs include a **Retry** action. A retry creates a linked attempt and uses the original trusted pull request URL, installation, command, and known commit. Repeated clicks reuse the same queued retry instead of creating concurrent jobs.

Each review fetches GitHub's numeric pull-request ref into a bounded temporary workspace, evaluates the pull request's own `.regora.yml`, and deletes the workspace after analysis. The persistent indexed graph is never replaced by a pull request review. Regora parses source statically and does not execute pull request code.

## Troubleshooting

- **Webhook returns 401:** verify `GITHUB_WEBHOOK_SECRET` and the GitHub App webhook secret match.
- **Webhook says `repository_not_indexed`:** index the repository using its canonical GitHub URL first.
- **Webhook says `ambiguous_repository_binding`:** delete duplicate indexed copies of the GitHub repository, keep one ready copy, then redeliver the event.
- **Webhook says `repository_binding_conflict`:** another installation claimed the indexed copy; index a separate copy before retrying.
- **Authentication fails:** verify the App ID, private key, and installation are correct.
- **Comment fails:** confirm **Issues: Read and write** is enabled; pull request comments use the Issues API.
- **Status is missing:** confirm **Commit statuses: Read and write** is enabled.
- **Job remains queued:** inspect `docker compose logs pull-request-worker redis`.
