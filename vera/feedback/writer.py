"""UserProfileWriter — escreve APENAS na seção ## Feedback loop do USER.md."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from vera.feedback.patterns import Inference

MAX_ACTIVE_INFERENCES = 15
USER_MD_PATH = Path("workspace/USER.md")
INFERENCES_STATE_PATH = Path("state/inferences.json")
SECTION_HEADER = "## Feedback loop"


class UserProfileWriter:
    """Atualiza seção ## Feedback loop do USER.md com inferências ativas."""

    def update(self, inferences: list[Inference]) -> dict:
        """Atualiza USER.md com novas inferências. Retorna {added, removed, total}."""
        # Load existing active inferences
        existing = self._load_active_inferences()
        existing_ids = {inf["id"] for inf in existing}

        # Merge new inferences (skip duplicates)
        added = 0
        for inf in inferences:
            if inf.id not in existing_ids:
                existing.append(asdict(inf))
                existing_ids.add(inf.id)
                added += 1

        # Remove expired
        today = date.today().isoformat()
        before_count = len(existing)
        existing = [inf for inf in existing if inf.get("expires_at", "") >= today]
        removed = before_count - len(existing)

        # Enforce max limit — remove oldest by created_at
        if len(existing) > MAX_ACTIVE_INFERENCES:
            existing.sort(key=lambda x: x.get("created_at", ""))
            removed += len(existing) - MAX_ACTIVE_INFERENCES
            existing = existing[-MAX_ACTIVE_INFERENCES:]

        # Save inferences state
        self._save_active_inferences(existing)

        # Update USER.md only if there are changes
        if added > 0 or removed > 0:
            self._write_to_user_md(existing)

        return {"added": added, "removed": removed, "total": len(existing)}

    def _write_to_user_md(self, active_inferences: list[dict]) -> None:
        """Writes ONLY to ## Feedback loop section. Never touches other sections."""
        if not USER_MD_PATH.exists():
            # Create minimal USER.md with just the feedback section
            content = f"\n{SECTION_HEADER}\n"
            content += self._format_inferences(active_inferences)
            USER_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
            USER_MD_PATH.write_text(content, encoding="utf-8")
            return

        full_text = USER_MD_PATH.read_text(encoding="utf-8")
        lines = full_text.split("\n")

        # Find ## Feedback loop section boundaries
        section_start = None
        section_end = None

        for i, line in enumerate(lines):
            if line.strip().lower().startswith("## feedback"):
                section_start = i
            elif section_start is not None and line.strip().startswith("## ") and i > section_start:
                section_end = i
                break

        new_section = self._format_inferences(active_inferences)

        if section_start is not None:
            # Replace existing section
            if section_end is None:
                section_end = len(lines)
            new_lines = lines[:section_start] + [f"{SECTION_HEADER}", new_section] + lines[section_end:]
        else:
            # Append section at end
            new_lines = lines + ["", f"{SECTION_HEADER}", new_section]

        new_text = "\n".join(new_lines)

        # Only write if content actually changed
        if new_text.rstrip() != full_text.rstrip():
            USER_MD_PATH.write_text(new_text, encoding="utf-8")

    def _format_inferences(self, inferences: list[dict]) -> str:
        """Formata inferências como linhas markdown."""
        if not inferences:
            return "Nenhuma inferência ativa.\n"

        lines = []
        for inf in inferences:
            created = inf.get("created_at", "?")
            text = inf.get("text", "")
            lines.append(f"- [inferido {created}] {text}")

        return "\n".join(lines) + "\n"

    def _load_active_inferences(self) -> list[dict]:
        INFERENCES_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if INFERENCES_STATE_PATH.exists():
            try:
                data = json.loads(INFERENCES_STATE_PATH.read_text(encoding="utf-8"))
                return data.get("active", [])
            except (json.JSONDecodeError, ValueError):
                pass
        return []

    def _save_active_inferences(self, inferences: list[dict]) -> None:
        INFERENCES_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        INFERENCES_STATE_PATH.write_text(
            json.dumps({"active": inferences}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
