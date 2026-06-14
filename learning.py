import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEARNING_DIR = Path(__file__).parent / "data" / "learning"
QUESTIONS_PATH = LEARNING_DIR / "questions.json"
STATE_PATH = LEARNING_DIR / "state.json"
PROPOSALS_PATH = LEARNING_DIR / "proposals.json"
DEV_FEEDBACK_PATH = LEARNING_DIR / "dev_feedback.json"
DEV_AGENT_QUEUE_PATH = LEARNING_DIR / "dev_agent_queue.json"

UNCLEAR_RATING = "Didn't Understand"

FEEDBACK_ADJUSTMENTS = {
    "Like": 6,
    "Neutral": 0,
    "Saved": 0,
    "Not Interested": -6,
    UNCLEAR_RATING: 0,
}

REVIEW_DECISION_RATINGS = {
    "pass": "Not Interested",
    "saved": "Saved",
    "interested": "Like",
    "unclear": UNCLEAR_RATING,
}

QUEUE_EXCLUDED_RATINGS = frozenset(
    {"Not Interested", "Saved", "Like", UNCLEAR_RATING}
)
OUTCOME_ADJUSTMENTS = {
    "Not Pursued": -3,
    "Reached Out": 2,
    "Conversation Started": 4,
    "Ongoing Discussion": 6,
    "Opportunity Created": 8,
}
POSITIVE_OUTCOMES = {
    "Reached Out",
    "Conversation Started",
    "Ongoing Discussion",
    "Opportunity Created",
}

ACTION_STATUS_ADJUSTMENTS = {
    "Sent": 8,
    "Replied": 10,
    "Meeting Scheduled": 12,
    "Opportunity Created": 14,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_memory() -> dict[str, list]:
    return {
        "preferences": [],
        "answers": [],
        "actions": [],
        "opportunity_signals": [],
        "founder_signals": [],
        "facts": [],
        "beliefs": [],
        "hypotheses": [],
    }


def default_state() -> dict[str, Any]:
    return {
        "answers": [],
        "feedback": [],
        "outcomes": [],
        "alignment_memory": empty_memory(),
    }


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as destination:
        json.dump(data, destination, indent=2, ensure_ascii=True)
        destination.write("\n")
    try:
        from github_sync import schedule_sync

        if path.is_relative_to(LEARNING_DIR):
            schedule_sync(f"learning/{path.name}")
    except ImportError:
        pass


def load_questions() -> list[dict[str, Any]]:
    return load_json(QUESTIONS_PATH, [])


def load_state() -> dict[str, Any]:
    state = load_json(STATE_PATH, default_state())
    for key in ("answers", "feedback", "outcomes"):
        state.setdefault(key, [])
    state["alignment_memory"] = build_alignment_memory(state, load_questions())
    return state


def latest_by(records: list[dict], key: str) -> dict[str, dict]:
    latest = {}
    for record in records:
        latest[record[key]] = record
    return latest


def answer_question(
    state: dict[str, Any],
    question: dict[str, Any],
    answer: str | list[str],
) -> dict[str, Any]:
    state["answers"].append(
        {
            "question_id": question["id"],
            "question": question["prompt"],
            "answer": answer,
            "signal": question["signal"],
            "timestamp": now_iso(),
        }
    )
    return persist_learning(state)


def record_feedback(
    state: dict[str, Any],
    company: dict[str, Any],
    rating: str,
    reason: str,
) -> dict[str, Any]:
    state["feedback"].append(
        {
            "company": company["company"],
            "country": company["country"],
            "theme": company["theme"],
            "suggested_role": company["suggested_role"],
            "rating": rating,
            "reason": reason.strip(),
            "timestamp": now_iso(),
        }
    )
    return persist_learning(state)


def latest_company_feedback(
    state: dict[str, Any], company_name: str
) -> dict[str, Any] | None:
    return latest_by(state["feedback"], "company").get(company_name)


def record_review_decision(
    state: dict[str, Any],
    company: dict[str, Any],
    decision: str,
    reason: str = "",
) -> dict[str, Any]:
    rating = REVIEW_DECISION_RATINGS[decision]
    return record_feedback(state, company, rating, reason)


def filter_companies_by_latest_rating(
    companies: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    rating: str | None = None,
    exclude_ratings: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    feedback_map = latest_by(state["feedback"], "company")
    filtered = []
    for company in companies:
        feedback = feedback_map.get(company["company"])
        latest_rating = feedback["rating"] if feedback else None
        if rating is not None and latest_rating != rating:
            continue
        if exclude_ratings and latest_rating in exclude_ratings:
            continue
        filtered.append(company)
    return filtered


def get_review_queue(
    companies: list[dict[str, Any]], state: dict[str, Any]
) -> list[dict[str, Any]]:
    return filter_companies_by_latest_rating(
        companies,
        state,
        exclude_ratings=QUEUE_EXCLUDED_RATINGS,
    )


def get_saved_companies(
    companies: list[dict[str, Any]], state: dict[str, Any]
) -> list[dict[str, Any]]:
    return filter_companies_by_latest_rating(companies, state, rating="Saved")


def get_interested_companies(
    companies: list[dict[str, Any]], state: dict[str, Any]
) -> list[dict[str, Any]]:
    return filter_companies_by_latest_rating(companies, state, rating="Like")


def record_outcome(
    state: dict[str, Any],
    company: dict[str, Any],
    outcome: str,
) -> dict[str, Any]:
    state["outcomes"].append(
        {
            "company": company["company"],
            "country": company["country"],
            "theme": company["theme"],
            "suggested_role": company["suggested_role"],
            "outcome": outcome,
            "timestamp": now_iso(),
        }
    )
    return persist_learning(state)


def persist_learning(state: dict[str, Any]) -> dict[str, Any]:
    questions = load_questions()
    state["alignment_memory"] = build_alignment_memory(state, questions)
    save_json(STATE_PATH, state)
    save_json(PROPOSALS_PATH, generate_proposals(state, questions))
    return state


def get_action_memory_signals() -> list[dict[str, Any]]:
    try:
        from action_engine import get_action_signals_for_memory
    except ImportError:
        return []
    return get_action_signals_for_memory()


def build_alignment_memory(
    state: dict[str, Any], questions: list[dict[str, Any]]
) -> dict[str, list]:
    memory = empty_memory()
    question_map = {question["id"]: question for question in questions}
    latest_answers = latest_by(state["answers"], "question_id")
    latest_feedback = latest_by(state["feedback"], "company")
    latest_outcomes = latest_by(state["outcomes"], "company")
    action_signals = get_action_memory_signals()

    for answer in state["answers"]:
        memory["answers"].append(answer.copy())
        memory["facts"].append(
            {
                "statement": f"AJ answered '{answer['question']}' with: "
                f"{format_value(answer['answer'])}.",
                "source": "answer",
                "timestamp": answer["timestamp"],
            }
        )

    for question_id, answer in latest_answers.items():
        question = question_map.get(question_id, {})
        signal = question.get("signal", answer.get("signal", "preference"))
        preference = {
            "type": signal,
            "value": answer["answer"],
            "evidence": question_id,
            "timestamp": answer["timestamp"],
        }
        memory["preferences"].append(preference)
        if signal == "founder_style":
            memory["founder_signals"].append(preference.copy())

    for feedback in state["feedback"]:
        memory["facts"].append(
            {
                "statement": f"AJ rated {feedback['company']} as "
                f"{feedback['rating']}."
                + (f" Reason: {feedback['reason']}" if feedback["reason"] else ""),
                "source": "feedback",
                "timestamp": feedback["timestamp"],
            }
        )

    for outcome in state["outcomes"]:
        action = {
            "company": outcome["company"],
            "outcome": outcome["outcome"],
            "timestamp": outcome["timestamp"],
        }
        memory["actions"].append(action)
        memory["facts"].append(
            {
                "statement": f"{outcome['company']} outcome recorded as "
                f"{outcome['outcome']}.",
                "source": "action",
                "timestamp": outcome["timestamp"],
            }
        )

    for signal in action_signals:
        memory["actions"].append(
            {
                "company": signal["entity_id"],
                "outcome": signal["status"],
                "timestamp": signal["timestamp"],
            }
        )
        memory["facts"].append(
            {
                "statement": (
                    f"{signal['entity_id']} action '{signal['recommended_action']}' "
                    f"reached status {signal['status']}."
                ),
                "source": "action_engine",
                "timestamp": signal["timestamp"],
            }
        )
        direction = (
            "positive"
            if signal["weight"] > 0
            else "negative" if signal["weight"] < 0 else "neutral"
        )
        memory["opportunity_signals"].append(
            {
                "direction": direction,
                "type": "action_outcome",
                "value": signal["entity_id"],
                "evidence": signal["status"],
            }
        )

    theme_evidence: dict[str, list[int]] = defaultdict(list)
    for feedback in latest_feedback.values():
        direction = FEEDBACK_ADJUSTMENTS[feedback["rating"]]
        theme_evidence[feedback["theme"]].append(direction)
        memory["opportunity_signals"].append(
            {
                "direction": direction_label(direction),
                "type": "company_feedback",
                "value": feedback["company"],
                "evidence": feedback["rating"],
            }
        )

    for outcome in latest_outcomes.values():
        direction = OUTCOME_ADJUSTMENTS[outcome["outcome"]]
        theme_evidence[outcome["theme"]].append(direction)
        memory["opportunity_signals"].append(
            {
                "direction": direction_label(direction),
                "type": "opportunity_outcome",
                "value": outcome["company"],
                "evidence": outcome["outcome"],
            }
        )

    action_theme_evidence: dict[str, list[int]] = defaultdict(list)
    for signal in action_signals:
        if signal["status"] not in ACTION_STATUS_ADJUSTMENTS:
            continue
        adjustment = ACTION_STATUS_ADJUSTMENTS[signal["status"]]
        action_theme_evidence[signal["theme"]].append(adjustment)
        theme_evidence[signal["theme"]].append(adjustment)

    for theme, evidence in action_theme_evidence.items():
        if len(evidence) >= 2 and all(value > 0 for value in evidence):
            memory["beliefs"].append(
                {
                    "statement": (
                        f"Action outcomes in {theme} suggest this theme converts "
                        "well into real conversations."
                    ),
                    "evidence_count": len(evidence),
                }
            )

    for theme, evidence in theme_evidence.items():
        non_zero = [value for value in evidence if value]
        if len(non_zero) >= 2 and all(value > 0 for value in non_zero):
            memory["beliefs"].append(
                {
                    "statement": f"{theme} opportunities appear positively aligned.",
                    "evidence_count": len(non_zero),
                }
            )
        elif len(non_zero) >= 2 and all(value < 0 for value in non_zero):
            memory["beliefs"].append(
                {
                    "statement": f"{theme} opportunities appear less aligned.",
                    "evidence_count": len(non_zero),
                }
            )
        elif non_zero:
            memory["hypotheses"].append(
                {
                    "statement": f"Alignment with {theme} may depend on the specific "
                    "company, role, or founder.",
                    "evidence_count": len(non_zero),
                }
            )

    for answer in latest_answers.values():
        if answer["signal"] in {"company_stage", "collaboration_model", "problem"}:
            memory["hypotheses"].append(
                {
                    "statement": f"{format_value(answer['answer'])} may be an important "
                    f"{answer['signal'].replace('_', ' ')} signal.",
                    "evidence_count": 1,
                }
            )

    return memory


def direction_label(value: int) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def format_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(value)
    return str(value)


def is_answered_value(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def latest_answer_for(
    state: dict[str, Any], question_id: str
) -> dict[str, Any] | None:
    return latest_by(state["answers"], "question_id").get(question_id)


def is_question_answered(state: dict[str, Any], question_id: str) -> bool:
    answer = latest_answer_for(state, question_id)
    return answer is not None and is_answered_value(answer.get("answer"))


def get_open_questions(
    state: dict[str, Any], questions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        question
        for question in questions
        if not is_question_answered(state, question["id"])
    ]


def skip_question(
    state: dict[str, Any], question: dict[str, Any], note: str = "Skipped for now"
) -> dict[str, Any]:
    return answer_question(state, question, note)


def default_dev_feedback_store() -> dict[str, list]:
    return {"items": []}


def default_dev_agent_queue() -> dict[str, list]:
    return {"items": []}


def load_dev_feedback() -> dict[str, list]:
    return load_json(DEV_FEEDBACK_PATH, default_dev_feedback_store())


def save_dev_feedback(store: dict[str, list]) -> None:
    save_json(DEV_FEEDBACK_PATH, store)


def load_dev_agent_queue() -> dict[str, list]:
    return load_json(DEV_AGENT_QUEUE_PATH, default_dev_agent_queue())


def save_dev_agent_queue(store: dict[str, list]) -> None:
    save_json(DEV_AGENT_QUEUE_PATH, store)


def dev_feedback_id() -> str:
    return f"dev_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def suggest_dev_action(feedback: str) -> str:
    trimmed = feedback.strip()
    if len(trimmed) > 100:
        trimmed = trimmed[:97] + "..."
    return f"Implement in opportunity-engine: {trimmed}"


def submit_dev_feedback(feedback: str, *, auto_queue: bool | None = None) -> dict[str, Any]:
    text = feedback.strip()
    if not text:
        raise ValueError("Feedback cannot be empty.")
    store = load_dev_feedback()
    item = {
        "id": dev_feedback_id(),
        "feedback": text,
        "suggested_action": suggest_dev_action(text),
        "status": "pending",
        "submitted_at": now_iso(),
        "approved_at": None,
        "dismissed_at": None,
    }

    should_auto_queue = auto_queue
    if should_auto_queue is None:
        try:
            from orchestrator_engine import load_config as load_orch_config

            should_auto_queue = load_orch_config().get("auto_approve_dev_feedback", True)
        except ImportError:
            should_auto_queue = True

    if should_auto_queue:
        item["status"] = "approved"
        item["approved_at"] = now_iso()
        store["items"].append(item)
        save_dev_feedback(store)

        queue = load_dev_agent_queue()
        queue["items"].append(
            {
                "id": item["id"],
                "feedback": item["feedback"],
                "suggested_action": item["suggested_action"],
                "approved_at": item["approved_at"],
                "status": "queued",
            }
        )
        save_dev_agent_queue(queue)

        try:
            from orchestrator_engine import enqueue

            enqueue(
                "dev_implement",
                feedback_id=item["id"],
                notes=text[:120],
                source="dev_feedback_submit",
                priority=2,
            )
        except ImportError:
            pass

        try:
            from slack_notify import notify_dev_feedback

            notify_dev_feedback(text)
        except ImportError:
            pass
    else:
        store["items"].append(item)
        save_dev_feedback(store)

    state = load_state()
    save_json(PROPOSALS_PATH, generate_proposals(state, load_questions()))
    return item


def find_dev_feedback_item(store: dict[str, list], item_id: str) -> dict[str, Any] | None:
    return next((item for item in store["items"] if item["id"] == item_id), None)


def dismiss_dev_feedback(item_id: str) -> dict[str, Any] | None:
    store = load_dev_feedback()
    item = find_dev_feedback_item(store, item_id)
    if not item or item["status"] != "pending":
        return item
    item["status"] = "dismissed"
    item["dismissed_at"] = now_iso()
    save_dev_feedback(store)
    state = load_state()
    save_json(PROPOSALS_PATH, generate_proposals(state, load_questions()))
    return item


def approve_dev_feedback(item_id: str) -> dict[str, Any] | None:
    store = load_dev_feedback()
    item = find_dev_feedback_item(store, item_id)
    if not item or item["status"] != "pending":
        return item
    item["status"] = "approved"
    item["approved_at"] = now_iso()
    save_dev_feedback(store)

    queue = load_dev_agent_queue()
    queue["items"].append(
        {
            "id": item["id"],
            "feedback": item["feedback"],
            "suggested_action": item["suggested_action"],
            "approved_at": item["approved_at"],
            "status": "queued",
        }
    )
    save_dev_agent_queue(queue)

    state = load_state()
    save_json(PROPOSALS_PATH, generate_proposals(state, load_questions()))
    return item


def generate_dev_proposals() -> list[dict[str, Any]]:
    store = load_dev_feedback()
    return [
        {
            "id": item["id"],
            "feedback": item["feedback"],
            "suggested_action": item["suggested_action"],
            "status": item["status"],
            "submitted_at": item["submitted_at"],
        }
        for item in store["items"]
        if item["status"] == "pending"
    ]


def calculate_personalization(
    company: dict[str, Any], state: dict[str, Any]
) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    latest_feedback = latest_by(state["feedback"], "company")
    latest_outcomes = latest_by(state["outcomes"], "company")
    company_feedback = latest_feedback.get(company["company"])
    company_outcome = latest_outcomes.get(company["company"])

    if company_feedback:
        value = FEEDBACK_ADJUSTMENTS[company_feedback["rating"]]
        score += value
        reasons.append(f"{company_feedback['rating']} feedback: {value:+d}")

    if company_outcome:
        value = OUTCOME_ADJUSTMENTS[company_outcome["outcome"]]
        score += value
        reasons.append(f"{company_outcome['outcome']} outcome: {value:+d}")

    theme_values = [
        FEEDBACK_ADJUSTMENTS[feedback["rating"]]
        for feedback in latest_feedback.values()
        if feedback["company"] != company["company"]
        and feedback["theme"] == company["theme"]
    ]
    if theme_values:
        average = sum(theme_values) / len(theme_values)
        theme_adjustment = 2 if average > 1 else -2 if average < -1 else 0
        if theme_adjustment:
            score += theme_adjustment
            reasons.append(
                f"Feedback on other {company['theme']} opportunities: "
                f"{theme_adjustment:+d}"
            )

    latest_answers = latest_by(state["answers"], "question_id")
    preference_checks = {
        "preferred_themes": company["theme"],
        "preferred_geographies": company["country"],
    }
    for question_id, company_value in preference_checks.items():
        answer = latest_answers.get(question_id)
        if answer and company_value in answer["answer"]:
            score += 1
            reasons.append(f"Matches stated preference: {company_value} (+1)")

    collaboration = latest_answers.get("collaboration_models")
    if collaboration:
        role = company["suggested_role"].lower()
        matched = [
            value
            for value in collaboration["answer"]
            if collaboration_matches_role(value, role)
        ]
        if matched:
            score += 1
            reasons.append(f"Matches collaboration preference: {matched[0]} (+1)")

    try:
        from action_engine import get_action_pattern_adjustment, load_action_patterns

        action_adjustment, action_reasons = get_action_pattern_adjustment(
            company, load_action_patterns()
        )
        if action_adjustment:
            score += action_adjustment
            reasons.extend(action_reasons)
    except ImportError:
        pass

    adjustment = max(-10, min(10, score))
    if adjustment != score:
        reasons.append(f"Adjustment capped from {score:+d} to {adjustment:+d}")
    if not reasons:
        reasons.append("No learned evidence for this opportunity yet.")
    return adjustment, reasons


def collaboration_matches_role(model: str, role: str) -> bool:
    keywords = {
        "Advisory": ("advisor", "advisory"),
        "Founder in Residence": ("founder in residence",),
        "Entrepreneur in Residence": ("entrepreneur in residence",),
        "Strategic Partnership": ("partner", "partnership"),
        "Leadership Role": ("lead", "head", "director"),
        "Venture Creation": ("venture", "entrepreneur", "founder"),
    }
    return any(keyword in role for keyword in keywords.get(model, ()))


def generate_insights(
    state: dict[str, Any], questions: list[dict[str, Any]]
) -> dict[str, list[str]]:
    memory = state["alignment_memory"]
    learned = [
        f"Preference for {item['type'].replace('_', ' ')}: "
        f"{format_value(item['value'])}"
        for item in memory["preferences"]
    ]
    learned.extend(
        f"{item['company']}: {item['outcome']}" for item in memory["actions"]
    )

    positive = [
        f"{signal['value']} ({signal['evidence']})"
        for signal in memory["opportunity_signals"]
        if signal["direction"] == "positive"
    ]
    negative = [
        f"{signal['value']} ({signal['evidence']})"
        for signal in memory["opportunity_signals"]
        if signal["direction"] == "negative"
    ]
    hypotheses = [
        item["statement"] for item in memory["beliefs"] + memory["hypotheses"]
    ]
    open_questions = [
        question["prompt"] for question in get_open_questions(state, questions)
    ]
    return {
        "learned": learned,
        "hypotheses": hypotheses,
        "positive_signals": positive,
        "negative_signals": negative,
        "open_questions": open_questions,
    }


def generate_proposals(
    state: dict[str, Any], questions: list[dict[str, Any]]
) -> dict[str, Any]:
    memory = state["alignment_memory"]
    latest_feedback = latest_by(state["feedback"], "company")
    ratings = Counter(item["rating"] for item in latest_feedback.values())
    open_questions = get_open_questions(state, questions)

    source_suggestions = []
    preferred_themes = next(
        (
            item["value"]
            for item in memory["preferences"]
            if item["type"] == "theme"
        ),
        [],
    )
    for theme in preferred_themes:
        source_suggestions.append(
            f"Add founder communities, accelerators, and emerging companies in {theme}."
        )
    if not source_suggestions:
        source_suggestions.append(
            "Collect theme preferences before expanding opportunity sources."
        )

    scoring_suggestions = []
    if ratings["Not Interested"] >= 2:
        scoring_suggestions.append(
            "Review score components shared by highly ranked opportunities marked "
            "Not Interested."
        )
    if ratings["Like"] >= 2:
        scoring_suggestions.append(
            "Compare liked opportunities for recurring theme, role, and geography "
            "signals that may deserve additional weight."
        )
    if not scoring_suggestions:
        scoring_suggestions.append(
            "Gather more feedback before proposing changes to the base scoring model."
        )

    roadmap_suggestions = [
        "Prioritize founder discovery after enough founder-style evidence is collected."
    ]
    if any(
        outcome["outcome"] in POSITIVE_OUTCOMES for outcome in state["outcomes"]
    ):
        roadmap_suggestions.append(
            "Bring relationship tracking forward as real outreach activity grows."
        )

    feature_suggestions = []
    if open_questions:
        feature_suggestions.append(
            "Keep the one-question learning flow until the core opportunity "
            "intelligence questions are answered."
        )
    if state["feedback"]:
        feature_suggestions.append(
            "Later add feedback-pattern filtering when the history is large enough "
            "to be difficult to review manually."
        )
    if not feature_suggestions:
        feature_suggestions.append(
            "Collect initial questions and feedback before proposing another feature."
        )

    content_suggestions = []
    unclear_feedback = [
        item for item in latest_feedback.values() if item["rating"] == UNCLEAR_RATING
    ]
    if unclear_feedback:
        feature_suggestions.append(
            f"{len(unclear_feedback)} profile(s) marked as unclear — run the content "
            "refinement agent to rewrite copy in Ankit's Hinglish voice."
        )
    for feedback in unclear_feedback:
        line = f"Refine {feedback['company']} ({feedback['theme']}) — copy was unclear."
        if feedback.get("reason"):
            line += f" AJ said: {feedback['reason']}"
        content_suggestions.append(line)

    return {
        "generated_at": now_iso(),
        "notice": (
            "Suggestions only. AJOS does not automatically modify MEMORY.md, "
            "DECISIONS.md, ROADMAP.md, or VISION.md."
        ),
        "opportunity_source_suggestions": source_suggestions,
        "scoring_suggestions": scoring_suggestions,
        "roadmap_suggestions": roadmap_suggestions,
        "feature_suggestions": feature_suggestions,
        "content_suggestions": content_suggestions,
        "dev_proposals": generate_dev_proposals(),
    }
