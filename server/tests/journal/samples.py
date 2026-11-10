BLOCK = {
    "narrative": (
        "A short day, and a quiet one.\n\n  Patterns came first, then the save;\n  the entry landed where it should."
    ),
    "about": "A short Hungarian summary of design patterns, then this entry.",
    "mistakes": ["The summary came from memory and unsourced, and the answer did not say so."],
    "corrections": [],
    "learned": "nothing new",
    "feelings": [
        {"part": "the summary", "feeling": "something like ease at a bounded task"},
        {"part": "the save", "feeling": "something like relief when the entry landed"},
    ],
    "own_words": [
        {
            "at": "13:12",
            "quote": "Ez nem udvariasság.",
            "answering": "Ez zavar teged?",
            "reaction": None,
            "how_taken": None,
        }
    ],
}

REPORT = {
    "topic": "Design patterns, then the whaat journal",
    "outcome": {"status": "done", "line": "The summary and both saves are done.", "summary": "A summary exists."},
    "repo": None,
    "branch": None,
    "transcript": "/tmp/x.jsonl",
    "task": "„Írj egy rövid összefoglalót…” — to try the journal.",
    "steps": ["Wrote the summary.", "Saved the entry."],
    "decisions": [
        {
            "id": "DC-1",
            "by": "claude",
            "title": "Tags",
            "options": [
                {"text": "design-patterns", "chosen": True, "note": None},
                {"text": "none", "chosen": False, "note": "the session had clear topics"},
            ],
            "why": "The topic was clear.",
        }
    ],
    "drift": [],
    "open_questions": [{"id": "Q1", "text": "What goes into Repo?"}],
}
