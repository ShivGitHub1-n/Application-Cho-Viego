from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "manual-test" / "reference-resume.docx"
OUTPUT = ROOT / "src" / "resume_tailor" / "templates" / "template_v1.docx"
REFERENCE_SHA256 = "2b9dd1474b9e4a303a87b8a147f3511460988104efde7cfa053cad64294369cd"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
DCTERMS = "http://purl.org/dc/terms/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
VT = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"

NS = {"w": W, "r": R}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
CUSTOM_PROPERTIES_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
)
HYPERLINK_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
)


def _q(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"


def _reference_paragraphs(document_root: etree._Element) -> list[etree._Element]:
    return list(document_root.xpath("./w:body/w:p", namespaces=NS))


def _source_run(paragraph: etree._Element, index: int) -> etree._Element:
    runs = paragraph.xpath(".//w:r", namespaces=NS)
    return runs[index]


def _run_from(
    paragraph: etree._Element,
    index: int,
    *,
    text: str | None = None,
    tab: bool = False,
) -> etree._Element:
    source = _source_run(paragraph, index)
    run = etree.Element(_q(W, "r"))
    properties = source.find(_q(W, "rPr"))
    if properties is not None:
        run.append(deepcopy(properties))
    if tab:
        run.append(etree.Element(_q(W, "tab")))
    else:
        text_node = etree.Element(_q(W, "t"))
        if text is not None and (text.startswith(" ") or text.endswith(" ")):
            text_node.set(XML_SPACE, "preserve")
        text_node.text = text or ""
        run.append(text_node)
    return run


def _placeholder_paragraph(
    source: etree._Element,
    run_specs: list[tuple[int, str | None, bool]],
) -> etree._Element:
    paragraph = deepcopy(source)
    properties = paragraph.find(_q(W, "pPr"))
    for child in list(paragraph):
        if child is not properties:
            paragraph.remove(child)
    for run_index, text, is_tab in run_specs:
        paragraph.append(_run_from(source, run_index, text=text, tab=is_tab))
    return paragraph


def _safe_heading(source: etree._Element) -> etree._Element:
    paragraph = deepcopy(source)
    for bookmark in paragraph.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
        bookmark.getparent().remove(bookmark)
    return paragraph


def _set_right_metadata_tab(paragraph: etree._Element) -> None:
    properties = paragraph.find(_q(W, "pPr"))
    if properties is None:
        properties = etree.Element(_q(W, "pPr"))
        paragraph.insert(0, properties)
    tabs = properties.find(_q(W, "tabs"))
    if tabs is not None:
        properties.remove(tabs)
    tabs = etree.Element(_q(W, "tabs"))
    tab = etree.Element(_q(W, "tab"))
    tab.set(_q(W, "val"), "right")
    tab.set(_q(W, "pos"), "11160")
    tabs.append(tab)
    insert_at = 1 if properties.find(_q(W, "pStyle")) is not None else 0
    properties.insert(insert_at, tabs)


def _add_education_rule(paragraph: etree._Element) -> None:
    properties = paragraph.find(_q(W, "pPr"))
    if properties is None:
        raise ValueError("Education heading has no paragraph properties")
    borders = properties.find(_q(W, "pBdr"))
    if borders is not None:
        properties.remove(borders)
    borders = etree.Element(_q(W, "pBdr"))
    bottom = etree.Element(_q(W, "bottom"))
    bottom.set(_q(W, "val"), "single")
    bottom.set(_q(W, "sz"), "4")
    bottom.set(_q(W, "space"), "1")
    bottom.set(_q(W, "color"), "000000")
    borders.append(bottom)
    properties.append(borders)


def _add_block_bookmark(
    paragraphs: list[etree._Element],
    name: str,
    bookmark_id: int,
) -> None:
    first = paragraphs[0]
    last = paragraphs[-1]
    start = etree.Element(_q(W, "bookmarkStart"))
    start.set(_q(W, "id"), str(bookmark_id))
    start.set(_q(W, "name"), name)
    first.insert(1 if first.find(_q(W, "pPr")) is not None else 0, start)
    end = etree.Element(_q(W, "bookmarkEnd"))
    end.set(_q(W, "id"), str(bookmark_id))
    last.append(end)


def _strip_revision_session_ids(root: etree._Element) -> None:
    for element in root.iter():
        for attribute in list(element.attrib):
            namespace, _, local_name = attribute.rpartition("}")
            if namespace == f"{{{W}" and local_name.startswith("rsid"):
                del element.attrib[attribute]
    for rsids in root.xpath(".//w:rsids", namespaces=NS):
        rsids.getparent().remove(rsids)


def _build_document_xml(reference_xml: bytes) -> bytes:
    root = etree.fromstring(reference_xml)
    source = _reference_paragraphs(root)
    body = root.find(f".//{_q(W, 'body')}")
    if body is None:
        raise ValueError("Reference DOCX has no document body")
    section_properties = body.find(_q(W, "sectPr"))
    if section_properties is None:
        raise ValueError("Reference DOCX has no section properties")

    name = _placeholder_paragraph(source[0], [(0, "{{NAME}}", False)])
    contact = _placeholder_paragraph(source[1], [(0, "{{CONTACT_LINE}}", False)])

    education_heading = _safe_heading(source[2])
    _add_education_rule(education_heading)
    education = [
        _placeholder_paragraph(
            source[4],
            [
                (0, "{{EDUCATION_INSTITUTION}}", False),
                (5, None, True),
                (8, "{{EDUCATION_DATES}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[5],
            [
                (0, "{{EDUCATION_PROGRAM}}", False),
                (4, None, True),
                (7, "{{EDUCATION_LOCATION}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[6],
            [
                (0, "{{EDUCATION_AWARDS}}", False),
                (0, "{{EDUCATION_GPA}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[7],
            [(0, "{{EDUCATION_COURSEWORK}}", False)],
        ),
    ]
    _set_right_metadata_tab(education[0])
    _set_right_metadata_tab(education[1])

    skills_heading = _safe_heading(source[8])
    skill = _placeholder_paragraph(
        source[9],
        [
            (0, "{{SKILL_CATEGORY}}", False),
            (3, "{{SKILL_SEPARATOR}}", False),
            (4, "{{SKILL_VALUES}}", False),
        ],
    )

    experience_heading = _safe_heading(source[14])
    first_experience = [
        _placeholder_paragraph(
            source[15],
            [
                (0, "{{EXPERIENCE_TITLE}}", False),
                (1, "{{EXPERIENCE_SUBTITLE_SEPARATOR}}", False),
                (2, "{{EXPERIENCE_SUBTITLE}}", False),
                (3, None, True),
                (4, "{{EXPERIENCE_DATES}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[16],
            [
                (0, "{{EXPERIENCE_ORGANIZATION}}", False),
                (1, None, True),
                (2, "{{EXPERIENCE_LOCATION}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[17],
            [(0, "{{EXPERIENCE_BULLET}}", False)],
        ),
    ]
    repeated_experience = [
        _placeholder_paragraph(
            source[21],
            [
                (0, "{{EXPERIENCE_REPEAT_TITLE}}", False),
                (2, "{{EXPERIENCE_REPEAT_SUBTITLE_SEPARATOR}}", False),
                (4, "{{EXPERIENCE_REPEAT_SUBTITLE}}", False),
                (5, None, True),
                (6, "{{EXPERIENCE_REPEAT_DATES}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[22],
            [
                (0, "{{EXPERIENCE_REPEAT_ORGANIZATION}}", False),
                (1, None, True),
                (4, "{{EXPERIENCE_REPEAT_LOCATION}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[23],
            [(0, "{{EXPERIENCE_REPEAT_BULLET}}", False)],
        ),
    ]
    for paragraph in [*first_experience[:2], *repeated_experience[:2]]:
        _set_right_metadata_tab(paragraph)

    projects_heading = _safe_heading(source[33])
    project = [
        _placeholder_paragraph(
            source[34],
            [
                (0, "{{PROJECT_TITLE}}", False),
                (2, "{{PROJECT_TECHNOLOGY_SEPARATOR}}", False),
                (4, "{{PROJECT_TECHNOLOGIES}}", False),
                (1, None, True),
                (0, "{{PROJECT_DATES}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[16],
            [
                (0, "{{PROJECT_ORGANIZATION}}", False),
                (1, None, True),
                (2, "{{PROJECT_LOCATION}}", False),
            ],
        ),
        _placeholder_paragraph(
            source[35],
            [(0, "{{PROJECT_BULLET}}", False)],
        ),
    ]
    _set_right_metadata_tab(project[0])
    _set_right_metadata_tab(project[1])

    _add_block_bookmark(education, "TPL_EDUCATION_ENTRY", 10)
    _add_block_bookmark([skill], "TPL_SKILL_CATEGORY_ROW", 11)
    _add_block_bookmark(first_experience, "TPL_EXPERIENCE_ENTRY_FIRST", 12)
    _add_block_bookmark(repeated_experience, "TPL_EXPERIENCE_ENTRY_REPEAT", 13)
    _add_block_bookmark(project, "TPL_PROJECT_ENTRY", 14)

    body_children = [
        name,
        contact,
        education_heading,
        *education,
        skills_heading,
        skill,
        experience_heading,
        *first_experience,
        *repeated_experience,
        projects_heading,
        *project,
        deepcopy(section_properties),
    ]
    for child in list(body):
        body.remove(child)
    body.extend(body_children)
    _strip_revision_session_ids(root)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def _remove_relationship_type(xml: bytes, relationship_type: str) -> bytes:
    root = etree.fromstring(xml)
    for relationship in list(root):
        if relationship.get("Type") == relationship_type:
            root.remove(relationship)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def _remove_custom_properties_override(xml: bytes) -> bytes:
    root = etree.fromstring(xml)
    for override in list(root):
        if override.get("PartName") == "/docProps/custom.xml":
            root.remove(override)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def _neutral_core_properties(xml: bytes) -> bytes:
    root = etree.fromstring(xml)
    for tag, value in (
        (_q(DC, "title"), "Application Viego Template V1"),
        (_q(DC, "subject"), "Content-neutral resume template"),
        (_q(DC, "creator"), "Application Viego"),
        (_q(CP, "lastModifiedBy"), "Application Viego"),
        (_q(CP, "revision"), "1"),
    ):
        element = root.find(tag)
        if element is None:
            element = etree.SubElement(root, tag)
        element.text = value
    for tag in (_q(CP, "lastPrinted"), _q(DCTERMS, "created"), _q(DCTERMS, "modified")):
        element = root.find(tag)
        if element is not None:
            root.remove(element)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def _neutral_app_properties(xml: bytes) -> bytes:
    root = etree.fromstring(xml)
    values = {
        "Pages": "1",
        "Words": "0",
        "Characters": "0",
        "Lines": "0",
        "Paragraphs": "0",
        "CharactersWithSpaces": "0",
        "TotalTime": "0",
    }
    for local_name, value in values.items():
        element = root.find(_q(EP, local_name))
        if element is not None:
            element.text = value
    titles = root.find(_q(EP, "TitlesOfParts"))
    if titles is not None:
        root.remove(titles)
    heading_pairs = root.find(_q(EP, "HeadingPairs"))
    if heading_pairs is not None:
        root.remove(heading_pairs)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def _strip_rsids_from_xml(xml: bytes) -> bytes:
    root = etree.fromstring(xml)
    _strip_revision_session_ids(root)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def build_template(reference: Path = REFERENCE, output: Path = OUTPUT) -> Path:
    actual_sha256 = sha256(reference.read_bytes()).hexdigest()
    if actual_sha256 != REFERENCE_SHA256:
        raise ValueError(
            f"Reference SHA-256 mismatch: expected {REFERENCE_SHA256}, got {actual_sha256}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(reference) as source_package:
        parts = {name: source_package.read(name) for name in source_package.namelist()}

    parts["word/document.xml"] = _build_document_xml(parts["word/document.xml"])
    parts["word/_rels/document.xml.rels"] = _remove_relationship_type(
        parts["word/_rels/document.xml.rels"],
        HYPERLINK_RELATIONSHIP,
    )
    parts["_rels/.rels"] = _remove_relationship_type(
        parts["_rels/.rels"],
        CUSTOM_PROPERTIES_RELATIONSHIP,
    )
    parts["[Content_Types].xml"] = _remove_custom_properties_override(parts["[Content_Types].xml"])
    parts["docProps/core.xml"] = _neutral_core_properties(parts["docProps/core.xml"])
    parts["docProps/app.xml"] = _neutral_app_properties(parts["docProps/app.xml"])
    parts.pop("docProps/custom.xml", None)

    for name, content in list(parts.items()):
        if name.endswith(".xml") and name not in {
            "word/document.xml",
            "docProps/core.xml",
            "docProps/app.xml",
        }:
            parts[name] = _strip_rsids_from_xml(content)

    temporary_output = output.with_suffix(".tmp.docx")
    with ZipFile(temporary_output, "w", compression=ZIP_DEFLATED) as target_package:
        for name, content in parts.items():
            entry = ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            target_package.writestr(entry, content)
    temporary_output.replace(output)
    return output


if __name__ == "__main__":
    built = build_template()
    print(f"{built} {sha256(built.read_bytes()).hexdigest()}")
