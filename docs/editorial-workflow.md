# Editorial Workflow

This workflow lets editors correct Surau kitab data without directly mutating canonical JSONL, Markdown, Typst, or citation files.

## Principle

```text
canonical repo files stay authoritative
Firestore stores editorial work-in-progress
admin approval exports accepted revisions back to canonical files
```

Editors should never edit `passages.jsonl`, `clean/manuscript.md`, `semantic-reviewed.jsonl`, or translation JSONL directly from the app. They submit review tasks, comments, and revision proposals. Admin approval is the gate that applies changes to canonical files.

## Roles

### End User

- Reads reviewed/published kitab content in mobile/web reader.
- Uses search, citation, bookmark, progress, and RAG features.
- May submit lightweight issue reports later.
- Does not access editorial drafts.

### Editor

- Reads assigned or open review tasks.
- Claims a task.
- Reviews Arabic text, heading, semantic tags, ayah/hadith references, and translation warnings.
- Submits revision proposals.
- Comments on tasks/revisions.
- Cannot approve, publish, rebuild, or write canonical files.

### Admin

- Creates/imports review tasks.
- Assigns tasks to editors.
- Reviews submitted revisions.
- Approves/rejects revisions.
- Runs export/apply, QA, Typst rebuild, citation sync, search/RAG indexing, and publish.

## Lifecycle

```text
canonical data
  -> QA/semantic/translation reports
  -> reviewTasks in Firestore
  -> editor claims task
  -> editor submits revision
  -> admin approves
  -> export approved revisions
  -> apply to canonical files
  -> QA
  -> rebuild Typst/page-map/search/RAG
  -> commit/publish
```

## Task Sources

Seed review tasks from:

- `books/{work_id}/annotations/semantic-review-queue.jsonl`
- `reports/qa/{work_id}.json`
- `translations/{lang}/passages.jsonl` warnings
- suspicious cleaning samples
- long/short passage outliers
- TOC entries that do not match headings

## Statuses

### reviewTasks

```text
open
claimed
in_review
blocked
done
cancelled
```

### revisions

```text
draft
submitted
approved
rejected
applied
superseded
```

### comments

```text
active
resolved
hidden
```

## Revision Targets

Allowed `target` values:

```text
passage.text
passage.section_path
passage.review_status
semantic.kind
semantic.role
semantic.layout
semantic.segment.ref
translation.text
translation.notes
translation.warnings
heading.title
toc.entry
```

Do not allow editor proposals that change:

- `passage.id`
- `work_id`
- `sequence`
- public citation anchor
- edition page maps
- old PDF source audit coordinates

## Admin Apply Rules

When an admin approves a revision:

1. Verify the revision base still matches the current canonical row.
2. Apply the change in a local branch/worktree.
3. Run validation/QA.
4. Rebuild affected outputs if needed.
5. Commit with a message that references revision IDs.
6. Mark revision as `applied` only after commit succeeds.

If the base no longer matches, mark the revision `blocked` or `superseded` and ask the editor to rebase it.

## Firestore Is Not Canonical

Firestore is the collaboration workspace. It may contain:

- review queue items
- editor proposals
- comments
- audit logs
- assignment status

Canonical publication still flows through repo files and commits.

## First MVP

1. Generate local review tasks:

```bash
python3 scripts/seed_review_tasks.py \
  --book-dir books/afdhalush-shalawat
```

2. Inspect:

```text
reports/editorial-review-tasks/afdhalush-shalawat-review-tasks.jsonl
reports/editorial-review-tasks/afdhalush-shalawat-review-tasks.md
```

3. Upload later through Admin SDK, Go backend, Cloud Function, or Firebase Admin script.

Do not deploy rules or upload tasks until the schema has been reviewed.
