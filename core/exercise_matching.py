from typing import Optional

from sqlalchemy.orm import Session

from core.models import Exercise


def resolve_exercise_id(session: Session, testo: str) -> Optional[int]:
    """Best-effort match of free-text exercise names against the tracked Exercise table.

    Matches if a tracked exercise's canonical name appears as a substring of the given
    text (case-insensitive) - e.g. "Back Squat" matches "Bb Back Squats 60% 1rm".
    """
    if not testo:
        return None
    testo_lower = testo.lower()
    for exercise in session.query(Exercise).all():
        if exercise.nome_canonico.lower() in testo_lower:
            return exercise.id
    return None
