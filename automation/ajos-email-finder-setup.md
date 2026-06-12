# Cursor Automation checklist — AJOS Email Finder

Quick checklist when creating or fixing the automation in the Cursor UI.

- [ ] Name: `AJOS Email Finder` (or `Email finder agent`)
- [ ] Trigger: Cron `0 10,22 * * *` (twice daily, after discovery)
- [ ] **Repository:** `rishiajofficial/opportunity-ajos` / branch **`main`** ← required; without this the agent sees an empty `/agent` folder
- [ ] **Git:** allow commit + push to `main`
- [ ] **APOLLO_API_KEY in Cursor (not Streamlit):** [cursor.com/dashboard](https://cursor.com/dashboard) → **Cloud Agents** or **Settings** → **Secrets** → add name `APOLLO_API_KEY`, value = Apollo API key. Streamlit `secrets.toml` does **not** reach cloud automations.
- [ ] If your automation has its own **Environment variables** field, set the same `APOLLO_API_KEY` there too.
- [ ] Cloud Agents: enabled in dashboard
- [ ] Prompt: copy from [`CLOUD_EMAIL_FINDER_AUTOMATION.md`](../CLOUD_EMAIL_FINDER_AUTOMATION.md) → Agent instructions block (includes repo + API key checks)
- [ ] Enable automation
- [ ] Test: trigger manually once; agent should print `APOLLO_OK` and list-queue JSON

If the run reports missing files or `gh` auth errors, the **Repository** field is almost always unset — fix that before anything else.

If the run finds the repo and queue but says **APOLLO_API_KEY missing**, the secret is only in Streamlit or your local shell — add it in **Cursor dashboard Secrets**, save, then re-run. Success check: agent prints `APOLLO_OK` before `list-queue`.

**Branch note:** agents may push to `cursor/email-finder-*` branches. Merge to `main` when emails land in `data/contacts/` so Streamlit Cloud picks them up.
