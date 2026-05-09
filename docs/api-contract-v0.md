# Surau API Contract v0

Version: `0.1`

This contract defines a read-only API over Surau canonical book data. It is meant for internal clients, prototype web/mobile apps, RAG ingestion, and layout QA tools. It does not claim that every exposed text is editorially final.

## Core Guarantees

- The canonical source anchor is always the Arabic passage row in `books/{work_id}/passages.jsonl`.
- Public citation comes from `book.yml.default_edition` through the passage `citation` field.
- Translations, commentary, summaries, and bilingual editions point back to `source_passage_id`.
- Old PDF pages remain source-audit metadata only. They are not public citation anchors.
- API responses are normalized. Do not expose JSONL rows directly as public API responses.
- Every response carries enough status metadata for clients to distinguish draft, reviewed, and published material.

## Base URL

```text
/api/v0
```

## Response Envelope

Single resource:

```json
{
  "data": {},
  "meta": {
    "api_version": "0.1"
  }
}
```

List resource:

```json
{
  "data": [],
  "page": {
    "limit": 50,
    "next_cursor": null
  },
  "meta": {
    "api_version": "0.1"
  }
}
```

Error:

```json
{
  "error": {
    "code": "not_found",
    "message": "Passage not found.",
    "details": {}
  }
}
```

## Shared Query Parameters

| Name | Type | Meaning |
| --- | --- | --- |
| `lang` | string | Requested display language. `ar` returns canonical Arabic. |
| `edition` | string | Citation/viewer edition. Defaults to `book.yml.default_edition`. |
| `include` | csv | Optional expansions: `text`, `translation`, `semantic`, `edition_refs`, `source_audit`. |
| `status` | csv | Filter by status such as `draft_extraction`, `machine_draft`, `reviewed`, `published`. |
| `limit` | integer | Page size, default `50`, max `200`. |
| `cursor` | string | Opaque cursor from previous response. |

`source_audit` should only be used in internal tools because it exposes old PDF extraction coordinates.

## Resources

### Book

```json
{
  "id": "afdhalush-shalawat",
  "title": {
    "ar": "أفضل الصلوات على سيد السادات",
    "id": "Afdhalush Shalawat"
  },
  "author": {
    "ar": "يوسف بن إسماعيل النبهاني",
    "display": "Yusuf bin Ismail an-Nabhani"
  },
  "canonical_lang": "ar",
  "status": "draft_extraction",
  "default_edition": "surau-v0",
  "working_edition": "surau-v2-enriched",
  "source_policy": "source_pdf_used_as_raw_material_only",
  "counts": {
    "passages": 1768,
    "translations": {
      "id": 3,
      "en": 1
    }
  }
}
```

### Passage

```json
{
  "id": "ASH-00033",
  "work_id": "afdhalush-shalawat",
  "sequence": 33,
  "lang": "ar",
  "section_path": [
    "القسم الأول",
    "الفصل الثاني: في الأحاديث التي ورد فيها الترغيب في الصلاة عليه صلى الله عليه وسلم"
  ],
  "text": "قال رسول الله...",
  "status": {
    "text": "draft_extraction",
    "semantic": "machine_validated"
  },
  "semantic": {
    "kind": "hadith",
    "role": "quote",
    "layout": "quote_block",
    "confidence": 0.95,
    "segment_count": 12,
    "review_required": true
  },
  "citation": {
    "label": "Afdhalush Shalawat, ed. surau-v0, hlm. 13, ASH-00033.",
    "edition_id": "surau-v0",
    "anchor_id": "ASH-00033",
    "locator": {
      "type": "page",
      "label": "13",
      "page": 13
    }
  },
  "viewer": {
    "edition_id": "surau-v0",
    "pdf_page": 13
  }
}
```

### Translation

```json
{
  "id": "ASH-00033.id",
  "work_id": "afdhalush-shalawat",
  "lang": "id",
  "source_lang": "ar",
  "source_passage_id": "ASH-00033",
  "status": "machine_draft",
  "type": "meaning",
  "translator": "Surau LLM Draft",
  "model": "deepseek-v4-pro",
  "text": "Rasulullah shallallahu alaihi wa sallam bersabda...",
  "notes": [],
  "warnings": [],
  "source_citation": {
    "label": "Afdhalush Shalawat, ed. surau-v0, hlm. 13, ASH-00033.",
    "edition_id": "surau-v0",
    "anchor_id": "ASH-00033"
  }
}
```

### Section

```json
{
  "id": "section:afdhalush-shalawat:القسم-الأول",
  "work_id": "afdhalush-shalawat",
  "title": "القسم الأول",
  "level": 1,
  "path": ["القسم الأول"],
  "first_passage_id": "ASH-00023",
  "passage_count": 132
}
```

## Endpoints

### List Books

```text
GET /api/v0/books
```

Response:

```json
{
  "data": [
    {
      "id": "afdhalush-shalawat",
      "title": {
        "ar": "أفضل الصلوات على سيد السادات",
        "id": "Afdhalush Shalawat"
      },
      "canonical_lang": "ar",
      "status": "draft_extraction",
      "default_edition": "surau-v0"
    }
  ],
  "page": {
    "limit": 50,
    "next_cursor": null
  },
  "meta": {
    "api_version": "0.1"
  }
}
```

### Get Book

```text
GET /api/v0/books/{work_id}
```

### List Sections

```text
GET /api/v0/books/{work_id}/sections
```

Optional filters:

```text
?level=1
?prefix=القسم الأول
```

### List Passages

```text
GET /api/v0/books/{work_id}/passages
```

Optional filters:

```text
?section=القسم الأول
?kind=hadith
?role=quote
?status=draft_extraction,reviewed
?include=semantic,translation
?lang=id
?limit=50
?cursor=...
```

Response item is a `Passage`. If `lang` is non-Arabic and `include=translation`, each item may include:

```json
{
  "translation": {
    "lang": "id",
    "status": "machine_draft",
    "text": "..."
  }
}
```

### Get Passage

```text
GET /api/v0/books/{work_id}/passages/{passage_id}
```

Recommended default expansion:

```text
?include=text,semantic
```

For a reader view:

```text
?lang=id&include=text,semantic,translation
```

### Get Passage Citation

```text
GET /api/v0/books/{work_id}/passages/{passage_id}/citation
```

Optional:

```text
?edition=surau-v2-enriched
```

Response:

```json
{
  "data": {
    "passage_id": "ASH-00033",
    "work_id": "afdhalush-shalawat",
    "citation": {
      "label": "Afdhalush Shalawat, ed. surau-v0, hlm. 13, ASH-00033.",
      "edition_id": "surau-v0",
      "anchor_id": "ASH-00033",
      "locator": {
        "type": "page",
        "label": "13",
        "page": 13
      }
    }
  },
  "meta": {
    "api_version": "0.1"
  }
}
```

### List Translations

```text
GET /api/v0/books/{work_id}/translations/{lang}/passages
```

Optional filters:

```text
?status=machine_draft
?source_passage_id=ASH-00033
?limit=50
```

### Get Translation By Source Passage

```text
GET /api/v0/books/{work_id}/translations/{lang}/passages/{passage_id}
```

`passage_id` is always the Arabic source passage ID, for example `ASH-00033`, not `ASH-00033.id`.

### List Editions

```text
GET /api/v0/books/{work_id}/editions
```

Response item:

```json
{
  "id": "surau-v2-enriched",
  "work_id": "afdhalush-shalawat",
  "status": "draft",
  "pdf_url": "/books/afdhalush-shalawat/editions/surau-v2-enriched/output.pdf",
  "page_map_url": "/books/afdhalush-shalawat/editions/surau-v2-enriched/page-map.json"
}
```

### Get Edition Page

```text
GET /api/v0/books/{work_id}/editions/{edition_id}/pages/{page}
```

Returns passages that start on the requested edition page.

### Search

```text
GET /api/v0/search
```

Optional filters:

```text
?q=الصلاة
?work_id=afdhalush-shalawat
?lang=ar
?kind=hadith
?limit=20
```

Search v0 can be lexical only. Vector/RAG search should use a separate internal index, but return the same `passage_id` and `citation` shape.

## Status Semantics

Text status values:

```text
raw_extraction
draft_extraction
draft
reviewed
published
```

Semantic status values:

```text
machine_draft
machine_validated
reviewed
published
```

Translation status values:

```text
machine_draft
reviewed
published
rejected
```

Clients should show visible warnings when using anything below `reviewed` in public-facing contexts.

## Include Policy

Default passage response should include:

```text
id, work_id, sequence, lang, section_path, status, citation, viewer
```

`text` may be included by default in reader APIs, but data-heavy API calls can require `include=text`.

Optional expansions:

| Include | Adds |
| --- | --- |
| `text` | Canonical Arabic text |
| `semantic` | Semantic kind/role/layout and segment summary |
| `translation` | Translation for requested `lang` |
| `edition_refs` | All known edition locators |
| `source_audit` | Old PDF `source_blocks` with bbox |

## RAG Contract

RAG chunks should store:

```json
{
  "chunk_id": "ASH-00033:ar",
  "work_id": "afdhalush-shalawat",
  "passage_id": "ASH-00033",
  "lang": "ar",
  "text": "...",
  "semantic_kind": "hadith",
  "section_path": ["القسم الأول", "الفصل الثاني"],
  "citation": {
    "label": "Afdhalush Shalawat, ed. surau-v0, hlm. 13, ASH-00033.",
    "anchor_id": "ASH-00033"
  }
}
```

Translation chunks may be indexed for retrieval, but answers must still cite the Arabic `source_passage_id`.

## Versioning

- Breaking response changes require `/api/v1`.
- New fields may be added to v0 responses if existing fields keep their meaning.
- Clients must ignore unknown fields.
- Cursor format is opaque and may change.

## Implementation Notes

The first implementation can be file-backed:

```text
book.yml -> Book
passages.jsonl -> Passage
annotations/semantic-reviewed.jsonl -> Passage.semantic
translations/{lang}/passages.jsonl -> Translation
editions/{edition_id}/page-map.json -> Edition page lookup
```

Load JSONL into memory at startup for v0. Add SQLite/Postgres later when search, auth, publishing workflows, or high traffic require it.
