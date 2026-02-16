from __future__ import annotations

from typing import Iterable


def format_module_count(count: int) -> str:
    value = int(count or 0)
    n10 = value % 10
    n100 = value % 100
    if n10 == 1 and n100 != 11:
        suffix = "модуль"
    elif 2 <= n10 <= 4 and not (12 <= n100 <= 14):
        suffix = "модуля"
    else:
        suffix = "модулей"
    return f"{value} {suffix}"


def build_personal_account_progress(courses: list[dict], completed_slugs: Iterable[str]):
    completed_set = set(completed_slugs)
    course_stats = []
    total_modules = 0
    total_completed = 0

    for course in courses:
        all_modules = list(course.get("advanced_modules") or [])
        basic_modules = list(course.get("basic_modules") or [])
        advanced_only_modules = list(course.get("advanced_only_modules") or [])

        total_count = len(all_modules)
        completed_count = sum(
            1 for module in all_modules if module.get("slug") in completed_set
        )

        basic_total = len(basic_modules)
        basic_completed = sum(
            1 for module in basic_modules if module.get("slug") in completed_set
        )

        advanced_total = len(advanced_only_modules)
        advanced_completed = sum(
            1
            for module in advanced_only_modules
            if module.get("slug") in completed_set
        )

        completion_percent = (
            int(round((completed_count / total_count) * 100)) if total_count else 0
        )

        course_stats.append(
            {
                "slug": course.get("slug", ""),
                "title": course.get("title", ""),
                "total_count": total_count,
                "completed_count": completed_count,
                "completion_percent": completion_percent,
                "total_label": format_module_count(total_count),
                "completed_label": format_module_count(completed_count),
                "basic_total_label": format_module_count(basic_total),
                "basic_completed_label": format_module_count(basic_completed),
                "advanced_total_label": format_module_count(advanced_total),
                "advanced_completed_label": format_module_count(advanced_completed),
            }
        )

        total_modules += total_count
        total_completed += completed_count

    completion_percent = (
        int(round((total_completed / total_modules) * 100)) if total_modules else 0
    )
    remaining_count = max(total_modules - total_completed, 0)

    summary = {
        "total_count": total_modules,
        "completed_count": total_completed,
        "remaining_count": remaining_count,
        "completion_percent": completion_percent,
        "total_label": format_module_count(total_modules),
        "completed_label": format_module_count(total_completed),
        "remaining_label": format_module_count(remaining_count),
    }

    return summary, course_stats
