from progress_metrics import build_personal_account_progress, format_module_count


def test_format_module_count_pluralization():
    assert format_module_count(1) == "1 модуль"
    assert format_module_count(2) == "2 модуля"
    assert format_module_count(5) == "5 модулей"
    assert format_module_count(11) == "11 модулей"
    assert format_module_count(22) == "22 модуля"


def test_build_personal_account_progress_summary_and_courses():
    courses = [
        {
            "slug": "c1",
            "title": "Курс 1",
            "advanced_modules": [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}],
            "basic_modules": [{"slug": "a"}, {"slug": "b"}],
            "advanced_only_modules": [{"slug": "c"}],
        },
        {
            "slug": "c2",
            "title": "Курс 2",
            "advanced_modules": [{"slug": "d"}, {"slug": "e"}],
            "basic_modules": [{"slug": "d"}],
            "advanced_only_modules": [{"slug": "e"}],
        },
    ]

    summary, course_stats = build_personal_account_progress(courses, {"a", "d", "e"})

    assert summary["total_count"] == 5
    assert summary["completed_count"] == 3
    assert summary["remaining_count"] == 2
    assert summary["completion_percent"] == 60
    assert summary["completed_label"] == "3 модуля"

    assert len(course_stats) == 2

    first = course_stats[0]
    assert first["slug"] == "c1"
    assert first["completed_count"] == 1
    assert first["completion_percent"] == 33
    assert first["basic_completed_label"] == "1 модуль"
    assert first["advanced_completed_label"] == "0 модулей"

    second = course_stats[1]
    assert second["slug"] == "c2"
    assert second["completed_count"] == 2
    assert second["completion_percent"] == 100
    assert second["basic_completed_label"] == "1 модуль"
    assert second["advanced_completed_label"] == "1 модуль"


def test_build_personal_account_progress_handles_empty_courses():
    summary, course_stats = build_personal_account_progress([], set())

    assert summary["total_count"] == 0
    assert summary["completed_count"] == 0
    assert summary["remaining_count"] == 0
    assert summary["completion_percent"] == 0
    assert course_stats == []
