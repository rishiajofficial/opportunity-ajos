# Cursor Automation checklist — AJOS Discovery

Quick checklist when creating the automation in the Cursor UI.

- [ ] Name: `AJOS Discovery`
- [ ] Trigger: Cron `0 8,20 * * *` (twice daily)
- [ ] Repo: `rishiajofficial/opportunity-ajos` / `main`
- [ ] Prompt: copy from [`CLOUD_DISCOVERY_AUTOMATION.md`](../CLOUD_DISCOVERY_AUTOMATION.md) → Agent instructions block
- [ ] Git: allow commit + push to `main`
- [ ] Cloud Agents: enabled in dashboard
- [ ] (Optional) Slack: Post to Slack tool + channel selected
- [ ] Enable automation
- [ ] Test: wait for first run or trigger manually; check GitHub for `discovery:` commit

After first successful run, open Streamlit AJOS on your phone — new **Discovered** cards should appear after redeploy.
