# Cursor Automation checklist — AJOS Content

- [ ] Name: `AJOS Content`
- [ ] Trigger: Cron `30 9,21 * * *` (after discovery runs)
- [ ] Repo: `rishiajofficial/opportunity-ajos` / `main`
- [ ] Prompt: copy from [`CLOUD_CONTENT_AUTOMATION.md`](../CLOUD_CONTENT_AUTOMATION.md) → Agent instructions block
- [ ] Git: allow commit + push to `main`
- [ ] Enable automation
- [ ] Test: mark one profile "Didn't understand" in AJOS, wait for run, check `companies.csv` commit

After refine, the profile should reappear in the review queue with clearer Hinglish bullets.
