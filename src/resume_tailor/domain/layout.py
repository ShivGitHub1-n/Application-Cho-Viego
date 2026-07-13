from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ObservedValue(BaseModel):
    value: Any = None
    provenance: Literal[
        "direct_paragraph_property",
        "direct_run_property",
        "named_style",
        "inherited_style",
        "document_default",
        "section_property",
        "numbering_definition",
        "relationship",
        "inferred_recurring_pattern",
        "not_present",
    ]


class PageLayout(BaseModel):
    width_twips: int
    height_twips: int
    top_margin_twips: int
    bottom_margin_twips: int
    left_margin_twips: int
    right_margin_twips: int
    header_distance_twips: int
    footer_distance_twips: int
    orientation: str
    column_count: int = 1
    column_spacing_twips: int | None = None
    column_equal_width: bool | None = None

    @property
    def usable_width_twips(self) -> int:
        return self.width_twips - self.left_margin_twips - self.right_margin_twips

    @property
    def usable_height_twips(self) -> int:
        return self.height_twips - self.top_margin_twips - self.bottom_margin_twips


class Typography(BaseModel):
    font_family: ObservedValue
    font_size_half_points: ObservedValue
    bold: ObservedValue
    italic: ObservedValue
    underline: ObservedValue
    color: ObservedValue
    character_spacing_twips: ObservedValue


class ParagraphLayout(BaseModel):
    alignment: ObservedValue
    space_before_twips: ObservedValue
    space_after_twips: ObservedValue
    before_auto_spacing: ObservedValue
    after_auto_spacing: ObservedValue
    contextual_spacing: ObservedValue
    line_spacing_twips: ObservedValue
    line_spacing_rule: ObservedValue
    left_indent_twips: ObservedValue
    right_indent_twips: ObservedValue
    first_line_indent_twips: ObservedValue
    hanging_indent_twips: ObservedValue
    keep_with_next: ObservedValue
    keep_together: ObservedValue
    widow_control: ObservedValue
    page_break_before: ObservedValue


class TabStop(BaseModel):
    position_twips: int
    alignment: str
    leader: str | None = None
    semantic_use: str | None = None
    provenance: str


class MetadataAnchorGroup(BaseModel):
    group_id: str
    observed_positions_twips: list[int]
    representative_position_twips: int
    role_groups: list[str] = Field(default_factory=list)
    tolerance_twips: int
    relative_tolerance: float
    provenance: list[str] = Field(default_factory=list)


class Border(BaseModel):
    position: str
    style: str
    thickness_eighth_points: int | None = None
    spacing_points: int | None = None
    color: str | None = None
    provenance: str


class BulletLayout(BaseModel):
    representation: str | None = None
    numbering_id: int | None = None
    numbering_level: int | None = None
    numbering_format: str | None = None
    marker_typography: Typography | None = None
    mechanism: Literal["numbering", "literal_marker"] = "literal_marker"
    provenance: str = "not_present"
    left_indent_twips: int | None = None
    hanging_indent_twips: int | None = None
    wrapped_line_alignment_twips: int | None = None
    space_before_twips: int | None = None
    space_after_twips: int | None = None


class HyperlinkLayout(BaseModel):
    present: bool = False
    external_relationship_count: int = 0
    internal_anchor_count: int = 0
    display_typography: Typography | None = None
    underline_behavior: str | None = None
    color_behavior: str | None = None
    compact_contact_line: bool = False
    relationship_handling: str = "relationship targets intentionally omitted"


class RunPattern(BaseModel):
    run_count: int
    bold_run_positions: list[int] = Field(default_factory=list)
    italic_run_positions: list[int] = Field(default_factory=list)
    hyperlink_run_positions: list[int] = Field(default_factory=list)
    typography_variants: list[Typography] = Field(default_factory=list)


class SemanticRoleLayout(BaseModel):
    role: str
    occurrence_count: int
    paragraph: ParagraphLayout
    primary_typography: Typography
    run_patterns: list[RunPattern] = Field(default_factory=list)
    tab_stops: list[TabStop] = Field(default_factory=list)
    borders: list[Border] = Field(default_factory=list)
    bullet: BulletLayout | None = None
    hyperlinks: HyperlinkLayout | None = None
    neighboring_roles: list[str] = Field(default_factory=list)
    inference_signals: list[str] = Field(default_factory=list)
    metadata_anchor_group_ids: list[str] = Field(default_factory=list)


class SectionPattern(BaseModel):
    ordinal: int
    role_sequence: list[str]
    transition_after_twips: int | None = None


class TransitionSpacing(BaseModel):
    source_role: str
    destination_role: str
    destination_section_first_role: str | None = None
    source_space_after_twips: ObservedValue
    destination_space_before_twips: ObservedValue
    resolved_source_space_after_twips: ObservedValue | None = None
    resolved_destination_space_before_twips: ObservedValue | None = None
    empty_paragraph_count: int = 0
    empty_space_before_twips: list[ObservedValue] = Field(default_factory=list)
    empty_space_after_twips: list[ObservedValue] = Field(default_factory=list)
    empty_line_spacing_twips: list[ObservedValue] = Field(default_factory=list)
    empty_line_spacing_rules: list[ObservedValue] = Field(default_factory=list)
    drawing_separator_present: bool = False
    provenance: list[str] = Field(default_factory=list)
    occurrence_count: int = 1


class LayoutProfile(BaseModel):
    schema_version: str = "1.0"
    page: PageLayout
    semantic_roles: dict[str, SemanticRoleLayout]
    metadata_anchor_groups: list[MetadataAnchorGroup] = Field(default_factory=list)
    section_patterns: list[SectionPattern] = Field(default_factory=list)
    transition_spacings: list[TransitionSpacing] = Field(default_factory=list)
    inspected_parts: list[str] = Field(default_factory=list)

    def to_json(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)
