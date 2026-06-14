# Cursor Automation checklist — AJOS Orchestrator

- [ ] Name: `AJOS Orchestrator`
- [ ] Trigger: Webhook (copy URL + token) + Cron `*/30 * * * *`
- [ ] Repo: your opportunity-engine repo / `main`
- [ ] Prompt: copy from [`CLOUD_ORCHESTRATOR_AUTOMATION.md`](../CLOUD_ORCHESTRATOR_AUTOMATION.md)
- [ ] Git: allow commit + push to `main`
- [ ] GitHub secrets: `CURSOR_WEBHOOK_URL`, `CURSOR_WEBHOOK_TOKEN`
- [ ] GitHub Action: `.github/workflows/ajos-orchestrator-trigger.yml` enabled
- [ ] App secret: `GITHUB_TOKEN` for Streamlit data sync
- [ ] (Optional) Slack: deploy `slack_bot.py` with `/ajos` commands
- [ ] Test: submit dev feedback in app → verify queue on GitHub → webhook run
