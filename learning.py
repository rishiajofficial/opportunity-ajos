import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEARNING_DIR = Path(__file__).parent / "data" / "learning"
QUESTIONS_PATH = LEARNING_DIR / "questions.json"
STATE_PATH = LEARNING_DIR / "state.json"
PROPOSALS_PATH = LEARNING_DIR / "proposals.json"

FEEDBACK_ADJUSTMENTS = {
    "Like": 6,
    "Neutral": 0,
    "Not Interested": -6,
}
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


def build_alignment_memory(
    state: dict[str, Any], questions: list[dict[str, Any]]
) -> dict[str, list]:
    memory = empty_memory()
    question_map = {question["id"]: question for question in questions}
    latest_answers = latest_by(state["answers"], "question_id")
    latest_feedback = latest_by(state["feedback"], "company")
    latest_outcomes = latest_by(state["outcomes"], "company")

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


def get_open_questions(
    state: dict[str, Any], questions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    answered_ids = {answer["question_id"] for answer in state["answers"]}
    return [question for question in questions if question["id"] not in answered_ids]


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
    }
