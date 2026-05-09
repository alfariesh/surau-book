# Firestore Editorial Model

Status: `draft`

This model is for the Firebase project `surau-87160`, Firestore `(default)`, Standard edition, Native mode. It is a collaboration layer for editors and admins, not the canonical kitab source.

## Collections

```text
users_private/{uid}
users_public/{uid}
userRoles/{uid}
books/{workId}
reviewTasks/{taskId}
revisions/{revisionId}
comments/{commentId}
auditLogs/{logId}
```

## users_private

Owner-only profile and settings. Contains PII, so only the user and admins should read it.

```json
{
  "uid": "firebase-auth-uid",
  "email": "editor@example.com",
  "display_name": "Editor Name",
  "photo_url": null,
  "created_at": "server timestamp",
  "updated_at": "server timestamp"
}
```

## users_public

Small public/editorial display profile with no private email or sensitive fields.

```json
{
  "uid": "firebase-auth-uid",
  "display_name": "Editor Name",
  "photo_url": null
}
```

## userRoles

Admin-managed RBAC document. Clients must not write their own roles.

```json
{
  "uid": "firebase-auth-uid",
  "roles": {
    "end_user": true,
    "editor": true,
    "admin": false
  },
  "active": true,
  "created_at": "server timestamp",
  "updated_at": "server timestamp"
}
```

Rules should check this document with `get(/databases/$(database)/documents/userRoles/$(request.auth.uid))`.

## books

Editorial metadata mirror of repo `book.yml`. Do not store full book text here for the first MVP.

```json
{
  "work_id": "afdhalush-shalawat",
  "title_ar": "أفضل الصلوات على سيد السادات",
  "title_id": "Afdhalush Shalawat",
  "status": "draft_extraction",
  "default_edition": "surau-v0",
  "canonical_repo_path": "books/afdhalush-shalawat",
  "updated_at": "server timestamp"
}
```

## reviewTasks

One actionable editorial task.

```json
{
  "schema_version": "0.1",
  "task_id": "afdhalush-shalawat__semantic_reference_review__...",
  "work_id": "afdhalush-shalawat",
  "passage_id": "ASH-00033",
  "task_type": "semantic_reference_review",
  "priority": "high",
  "priority_rank": 20,
  "status": "open",
  "assigned_to": null,
  "title": "Verify missing hadith reference",
  "reason": "ayah/hadith segment has no visible reference.",
  "recommended_action": "Cari rujukan ayat/hadits yang tepat.",
  "section_path": ["القسم الأول", "الفصل الثاني"],
  "source_citation_label": "Afdhalush Shalawat, ed. surau-v0, hlm. 13, ASH-00033.",
  "text_preview": "وقال صلى الله عليه وسلم...",
  "source": {
    "kind": "semantic_review_queue",
    "path": "books/afdhalush-shalawat/annotations/semantic-review-queue.jsonl",
    "id": "ASH-00033:s1:scripture_segment_missing_ref"
  },
  "created_by": "system",
  "created_at": "server timestamp",
  "updated_at": "server timestamp"
}
```

Recommended task types:

```text
semantic_reference_review
cleaning_suspicious
toc_unmatched_heading
long_passage_review
short_passage_review
translation_warning
translation_qa
manual_review
```

## revisions

Editor proposal against one target field.

```json
{
  "schema_version": "0.1",
  "work_id": "afdhalush-shalawat",
  "passage_id": "ASH-00033",
  "task_id": "afdhalush-shalawat__semantic_reference_review__...",
  "target": "semantic.segment.ref",
  "base_version": "git:1d92167",
  "base_value": "",
  "proposed_value": "Muslim",
  "status": "submitted",
  "created_by": "editor_uid",
  "created_at": "server timestamp",
  "updated_at": "server timestamp",
  "submitted_at": "server timestamp",
  "reviewed_by": null,
  "reviewed_at": null,
  "admin_notes": ""
}
```

Large fields such as `base_value` and `proposed_value` should be exempt from indexing.

## comments

Comments attached to tasks or revisions.

```json
{
  "target_type": "reviewTask",
  "target_id": "task_id",
  "work_id": "afdhalush-shalawat",
  "passage_id": "ASH-00033",
  "body": "Please check printed source around page 13.",
  "status": "active",
  "created_by": "editor_uid",
  "created_at": "server timestamp",
  "updated_at": "server timestamp"
}
```

## auditLogs

Write from trusted backend only. Client writes should be denied by rules.

```json
{
  "actor_uid": "admin_uid",
  "action": "revision.approved",
  "target_type": "revision",
  "target_id": "revision_id",
  "work_id": "afdhalush-shalawat",
  "created_at": "server timestamp",
  "metadata": {
    "commit": "..."
  }
}
```

## Query Patterns

Editor task list:

```text
reviewTasks
where status in ["open", "claimed", "in_review"]
orderBy priority_rank ASC
orderBy updated_at DESC
```

Editor assigned tasks:

```text
reviewTasks
where assigned_to == uid
where status in ["claimed", "in_review", "blocked"]
orderBy priority_rank ASC
orderBy updated_at DESC
```

Admin revision queue:

```text
revisions
where status == "submitted"
orderBy updated_at DESC
```

Passage-specific editorial history:

```text
revisions
where work_id == workId
where passage_id == passageId
orderBy updated_at DESC
```

Task/revision comments:

```text
comments
where target_type == "reviewTask"
where target_id == taskId
orderBy created_at ASC
```

## Write Policy

Clients may:

- editor: claim a task
- editor: create/update own draft/submitted revision
- editor/admin: create comments
- admin: approve/reject revisions and assign tasks

Clients may not:

- write audit logs
- change roles
- publish canonical data
- apply revisions to repo files
- change citation anchors

Trusted backend/Admin SDK handles:

- importing generated review tasks
- approval side effects
- export/apply to canonical files
- QA/rebuild/publish

## Seed JSONL Timestamp Markers

`scripts/seed_review_tasks.py` writes local JSONL with this placeholder:

```text
__SERVER_TIMESTAMP__
```

Upload code must convert that marker to Firestore server timestamps. The JSONL is for review/import staging; it is not meant to be written by an untrusted client.
