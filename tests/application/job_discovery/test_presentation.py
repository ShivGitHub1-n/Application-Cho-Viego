from resume_tailor.application.job_discovery.presentation import (
    normalize_job_description_for_display,
)


def test_greenhouse_html_is_presented_as_safe_readable_text():
    description = (
        '<div><p>Build &amp; test <span style="color:red">robotics</span>.</p>'
        '<ul><li>Use &lt;C++&gt;</li><li>Never <strong>run</strong> unsafe code</li></ul>'
        '<script>alert("x")</script><style>.x{display:none}</style></div>'
    )

    rendered = normalize_job_description_for_display(description)

    assert "Build & test robotics." in rendered
    assert "Use <C++>" in rendered
    assert "Never run unsafe code" in rendered
    assert "<div>" not in rendered
    assert "style=" not in rendered
    assert "alert" not in rendered
    assert "display:none" not in rendered


def test_headings_breaks_and_lists_keep_meaningful_plain_text_separation():
    rendered = normalize_job_description_for_display(
        "<h2>Qualifications</h2>Python<br>ROS<br/>"
        "<ul><li>Build systems</li><li>Test systems</li></ul>"
        "<ol><li>Review code</li><li>Ship safely</li></ol>"
    )

    assert rendered == (
        "Qualifications\nPython\nROS\n"
        "- Build systems\n- Test systems\n"
        "- Review code\n- Ship safely"
    )


def test_plain_text_and_nested_unsafe_content_are_handled_deterministically():
    assert normalize_job_description_for_display("Already plain text.") == "Already plain text."
    rendered = normalize_job_description_for_display(
        "<div>Safe <span>text &amp; entity</span>"
        "<script><style>nested bad</style>alert('bad')</script>"
        "<style>.unsafe { color: red; }</style></div>"
    )

    assert rendered == "Safe text & entity"
    assert "nested" not in rendered
    assert "unsafe" not in rendered


def test_entity_escaped_and_double_escaped_html_is_parsed_before_display():
    escaped = (
        "&lt;h2&gt;Qualifications&lt;/h2&gt;&lt;p&gt;Python &amp; ROS&nbsp;2&lt;/p&gt;"
        "&lt;ul&gt;&lt;li&gt;Build systems&lt;/li&gt;&lt;/ul&gt;"
    )
    double_escaped = (
        "&amp;lt;div&amp;gt;&amp;lt;p&amp;gt;Double escaped content&amp;lt;/p&amp;gt;"
        "&amp;lt;script&amp;gt;alert('bad')&amp;lt;/script&amp;gt;&amp;lt;/div&amp;gt;"
    )

    escaped_rendered = normalize_job_description_for_display(escaped)
    double_rendered = normalize_job_description_for_display(double_escaped)

    assert escaped_rendered == "Qualifications\nPython & ROS 2\n- Build systems"
    assert double_rendered == "Double escaped content"
    for rendered in (escaped_rendered, double_rendered):
        assert "&amp;" not in rendered
        assert "&nbsp;" not in rendered
        assert "<div>" not in rendered
        assert "<p>" not in rendered
        assert "<script>" not in rendered
        assert "alert" not in rendered


def test_escaped_angle_bracket_text_is_not_treated_as_markup():
    rendered = normalize_job_description_for_display("Use &lt;C++&gt; and 3 &lt; 5")

    assert rendered == "Use <C++> and 3 < 5"


def test_escaped_tags_with_attributes_and_self_closing_tags_are_decoded():
    rendered = normalize_job_description_for_display(
        '&lt;div class=&quot;content&quot;&gt;Text&lt;br/&gt;Next'
        '&lt;/div&gt;'
    )

    assert rendered == "Text\nNext"
    assert "content" not in rendered
    assert "<br" not in rendered


def test_escaped_unsafe_tags_are_removed_after_tag_decoding():
    rendered = normalize_job_description_for_display(
        "&lt;script&gt;alert('bad')&lt;/script&gt;"
        "&lt;style&gt;.bad { color: red; }&lt;/style&gt;"
        "&lt;template&gt;hidden&lt;/template&gt;Visible"
    )

    assert rendered == "Visible"
    assert "alert" not in rendered
    assert "color: red" not in rendered
    assert "hidden" not in rendered
