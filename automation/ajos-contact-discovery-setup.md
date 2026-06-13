# Cursor Automation checklist — AJOS Contact Discovery

- [ ] Name: `AJOS Contact Discovery`
- [ ] Trigger: Cron `0 9,21 * * *` (before email finder at 10/22 UTC)
- [ ] **Repository:** `rishiajofficial/opportunity-ajos` / branch **`main`**
- [ ] **Git:** allow commit + push to `main`
- [ ] **HUNTER_API_KEY in Cursor Secrets** — [hunter.io/api-keys](https://hunter.io/api-keys); free plan works (50 credits/month)
- [ ] Prompt: copy from [`CLOUD_CONTACT_DISCOVERY_AUTOMATION.md`](../CLOUD_CONTACT_DISCOVERY_AUTOMATION.md)
- [ ] Enable automation
- [ ] Test: trigger manually; agent should print `HUNTER_OK` and list-queue JSON

Runs **before** the email finder automation so contacts exist before email enrichment.
