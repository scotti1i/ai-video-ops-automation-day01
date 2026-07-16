"""SQLite 持久化。写入方法保持窄接口，读取统一组装快照。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from video_ops.domain.models import (
    Account,
    AccountGroup,
    Batch,
    CommentSnapshot,
    ContextSnapshot,
    MediaArtifact,
    MetricSnapshot,
    Product,
    Publication,
    ScriptArtifact,
    ScriptCandidate,
    StoryboardArtifact,
    Video,
    WorkspaceSnapshot,
)
from video_ops.domain.ports import CandidateVersionConflict

from .read_model import build_snapshot
from .schema import SCHEMA_STATEMENTS


class SQLiteRepository:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.path, timeout=30)
        self.path.chmod(0o600)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        self.path.chmod(0o600)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(
        self,
        workspace_id: str = "workspace-main",
        name: str = "视频增长工作台",
        mode: str = "demo",
    ) -> None:
        with self.transaction() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            self._migrate(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO workspace
                (id, name, mode, traffic_threshold, order_threshold)
                VALUES (?, ?, ?, 100000, 20)
                """,
                (workspace_id, name, mode),
            )

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self.initialize()

    def snapshot(self) -> WorkspaceSnapshot:
        with self._read() as connection:
            return build_snapshot(connection)

    def set_mode(self, mode: str) -> None:
        with self.transaction() as connection:
            connection.execute("UPDATE workspace SET mode = ?", (mode,))

    def seed_version(self) -> int | None:
        """库内记录的种子版本；旧库没有记录时返回 None。"""
        with self._read() as connection:
            row = connection.execute("SELECT seed_version FROM workspace LIMIT 1").fetchone()
            return row["seed_version"] if row else None

    def set_seed_version(self, version: int) -> None:
        with self.transaction() as connection:
            connection.execute("UPDATE workspace SET seed_version = ?", (version,))

    def configure_workspace(
        self,
        *,
        workspace_id: str,
        name: str,
        mode: str,
        traffic_threshold: int,
        order_threshold: int,
    ) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM workspace")
            connection.execute(
                """
                INSERT INTO workspace
                (id, name, mode, traffic_threshold, order_threshold)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workspace_id, name, mode, traffic_threshold, order_threshold),
            )

    def add_group(self, group: AccountGroup) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO account_groups (id, name, sort_order) VALUES (?, ?, ?)",
                (group.id, group.name, group.sort_order),
            )

    def add_account(self, account: Account) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO accounts
                (id, group_id, name, handle, platform, connection_status, context, connector_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account.id,
                    account.group_id,
                    account.name,
                    account.handle,
                    account.platform,
                    account.connection_status,
                    account.context,
                    account.connector_ref,
                ),
            )

    def update_account_connection(
        self,
        account_id: str,
        status: str,
        connector_ref: str | None,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE accounts SET connection_status = ?, connector_ref = ? WHERE id = ?",
                (status, connector_ref, account_id),
            )

    def add_product(self, product: Product) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO products
                (id, title, description, selling_points_json, url, image_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    product.id,
                    product.title,
                    product.description,
                    json.dumps(product.selling_points, ensure_ascii=False),
                    product.url,
                    product.image_url,
                ),
            )

    def add_batch(self, batch: Batch) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO batches
                (id, name, product_id, brief, reference_url, script_settings_json,
                 note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.id,
                    batch.name,
                    batch.product_id,
                    batch.brief,
                    batch.reference_url,
                    (
                        self._json(batch.script_settings.model_dump())
                        if batch.script_settings
                        else None
                    ),
                    batch.note,
                    batch.created_at,
                ),
            )

    def add_candidate(self, candidate: ScriptCandidate) -> None:
        with self.transaction() as connection:
            self._insert_candidate(connection, candidate)

    def update_candidate(self, candidate: ScriptCandidate) -> bool:
        with self.transaction() as connection:
            changed = connection.execute(
                """
                UPDATE script_candidates SET title = ?, script = ?, shots_json = ?,
                provider = ?, claims_used_json = ?, claims_needing_evidence_json = ?,
                quality_json = ?, updated_at = ?
                WHERE id = ? AND batch_id = ? AND selected_video_id IS NULL
                """,
                (
                    candidate.title,
                    candidate.script,
                    self._shots_json(candidate.shots),
                    candidate.provider,
                    self._json(candidate.claims_used),
                    self._json(candidate.claims_needing_evidence),
                    self._json(candidate.quality.model_dump()),
                    candidate.updated_at,
                    candidate.id,
                    candidate.batch_id,
                ),
            ).rowcount
            return changed == 1

    def select_candidate(
        self,
        candidate_id: str,
        expected_updated_at: str,
        video: Video,
        context: ContextSnapshot,
        script: ScriptArtifact,
        storyboard: StoryboardArtifact,
    ) -> str:
        """原子地把候选转成正式视频；重复选择返回同一个视频。"""
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT selected_video_id, updated_at FROM script_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise ValueError("脚本候选不存在")
            if row["selected_video_id"]:
                return row["selected_video_id"]
            if row["updated_at"] != expected_updated_at:
                raise CandidateVersionConflict("候选刚被修改")
            stored = video.model_copy(update={"code": self._next_code(connection)})
            self._insert_video(connection, stored)
            self._insert_context(connection, context)
            self._insert_script(connection, script)
            self._insert_storyboard(connection, storyboard)
            changed = connection.execute(
                """
                UPDATE script_candidates SET selected_video_id = ?, updated_at = ?
                WHERE id = ? AND selected_video_id IS NULL AND updated_at = ?
                """,
                (stored.id, stored.updated_at, candidate_id, expected_updated_at),
            ).rowcount
            if changed != 1:
                raise CandidateVersionConflict("候选状态已变化")
            return stored.id

    def add_video(self, video: Video) -> None:
        with self.transaction() as connection:
            self._insert_video(connection, video)

    def add_video_with_context(
        self,
        video: Video,
        context: ContextSnapshot,
    ) -> Video:
        with self.transaction() as connection:
            stored = video.model_copy(update={"code": self._next_code(connection)})
            self._insert_video(connection, stored)
            self._insert_context(connection, context)
        return stored

    def update_video_title(self, video_id: str, title: str, updated_at: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE videos SET title = ?, updated_at = ? WHERE id = ?",
                (title, updated_at, video_id),
            )

    def add_context(self, context: ContextSnapshot) -> None:
        with self.transaction() as connection:
            self._insert_context(connection, context)
            self._touch(connection, context.video_id, context.created_at)

    def add_script(self, script: ScriptArtifact) -> None:
        with self.transaction() as connection:
            self._insert_script(connection, script)
            self._touch(connection, script.video_id, script.created_at)

    def add_storyboard(self, storyboard: StoryboardArtifact) -> None:
        with self.transaction() as connection:
            self._insert_storyboard(connection, storyboard)
            self._touch(connection, storyboard.video_id, storyboard.created_at)

    def add_artifact_pair(
        self,
        script: ScriptArtifact,
        storyboard: StoryboardArtifact,
    ) -> None:
        if script.video_id != storyboard.video_id:
            raise ValueError("脚本和分镜必须属于同一条视频")
        with self.transaction() as connection:
            self._insert_script(connection, script)
            self._insert_storyboard(connection, storyboard)
            self._touch(connection, script.video_id, script.created_at)

    def add_media(self, media: MediaArtifact) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO media
                (id, video_id, file_name, mime_type, size_bytes, checksum, storage_path,
                 source, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    media.id,
                    media.video_id,
                    media.file_name,
                    media.mime_type,
                    media.size_bytes,
                    media.checksum,
                    media.storage_path,
                    media.source,
                    media.status,
                    media.created_at,
                ),
            )
            self._touch(connection, media.video_id, media.created_at)

    def add_publication(self, publication: Publication) -> None:
        with self.transaction() as connection:
            self._insert_publication(connection, publication)
            self._touch(connection, publication.video_id, publication.updated_at)

    def add_publication_with_account_link(self, publication: Publication) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO video_accounts (video_id, account_id) VALUES (?, ?)",
                (publication.video_id, publication.account_id),
            )
            self._insert_publication(connection, publication)
            self._touch(connection, publication.video_id, publication.updated_at)

    def update_publication(self, publication: Publication) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE publications SET status = ?, scheduled_at = ?, published_at = ?,
                external_id = ?, url = ?, error = ?, warnings_json = ?, raw_ref = ?,
                claim_token = ?, lease_expires_at = ?, updated_at = ? WHERE id = ?
                """,
                (
                    publication.status,
                    publication.scheduled_at,
                    publication.published_at,
                    publication.external_id,
                    publication.url,
                    publication.error,
                    json.dumps(publication.warnings, ensure_ascii=False),
                    publication.raw_ref,
                    publication.claim_token,
                    publication.lease_expires_at,
                    publication.updated_at,
                    publication.id,
                ),
            )
            self._touch(connection, publication.video_id, publication.updated_at)

    def claim_publication(self, publication: Publication, claimed: Publication) -> bool:
        """原子抢占一次发布执行权。

        同时比较状态和更新时间，避免失败后恢复同一状态时被旧请求再次抢占。
        """
        with self.transaction() as connection:
            changed = connection.execute(
                """
                UPDATE publications SET status = 'publishing', error = NULL,
                claim_token = ?, lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND status = ? AND updated_at = ? AND claim_token IS ?
                """,
                (
                    claimed.claim_token,
                    claimed.lease_expires_at,
                    claimed.updated_at,
                    publication.id,
                    publication.status,
                    publication.updated_at,
                    publication.claim_token,
                ),
            ).rowcount
            if changed:
                self._touch(connection, publication.video_id, claimed.updated_at)
        return changed == 1

    def finish_publication(
        self,
        publication: Publication,
        expected_claim_token: str | None,
    ) -> bool:
        """只允许当前租约持有者完成发布，过期进程不得覆盖新状态。"""
        with self.transaction() as connection:
            changed = connection.execute(
                """
                UPDATE publications SET status = ?, scheduled_at = ?, published_at = ?,
                external_id = ?, url = ?, error = ?, warnings_json = ?, raw_ref = ?,
                claim_token = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'publishing' AND claim_token IS ?
                """,
                (
                    publication.status,
                    publication.scheduled_at,
                    publication.published_at,
                    publication.external_id,
                    publication.url,
                    publication.error,
                    json.dumps(publication.warnings, ensure_ascii=False),
                    publication.raw_ref,
                    publication.updated_at,
                    publication.id,
                    expected_claim_token,
                ),
            ).rowcount
            if changed:
                self._touch(connection, publication.video_id, publication.updated_at)
        return changed == 1

    def add_metric(self, metric: MetricSnapshot) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO metrics
                (id, publication_id, captured_at, views, likes, comments, shares,
                 orders, revenue, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metric.id,
                    metric.publication_id,
                    metric.captured_at,
                    metric.views,
                    metric.likes,
                    metric.comments,
                    metric.shares,
                    metric.orders,
                    metric.revenue,
                    json.dumps(metric.raw, ensure_ascii=False),
                ),
            )

    def upsert_comment(self, comment: CommentSnapshot) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO comments
                (id, publication_id, external_id, author, content, likes,
                 commented_at, captured_at, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(publication_id, external_id) DO UPDATE SET
                author = excluded.author, content = excluded.content, likes = excluded.likes,
                captured_at = excluded.captured_at, raw_json = excluded.raw_json
                """,
                (
                    comment.id,
                    comment.publication_id,
                    comment.external_id,
                    comment.author,
                    comment.content,
                    comment.likes,
                    comment.commented_at,
                    comment.captured_at,
                    json.dumps(comment.raw, ensure_ascii=False),
                ),
            )

    def replace_video_accounts(self, video_id: str, account_ids: list[str]) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM video_accounts WHERE video_id = ?", (video_id,))
            connection.executemany(
                "INSERT INTO video_accounts (video_id, account_id) VALUES (?, ?)",
                [(video_id, account_id) for account_id in account_ids],
            )

    def next_video_code(self) -> str:
        with self._read() as connection:
            return self._next_code(connection)

    @staticmethod
    def _next_code(connection: sqlite3.Connection) -> str:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(CAST(SUBSTR(code, 5) AS INTEGER)), 0) + 1 AS next
            FROM videos WHERE code GLOB 'VID-[0-9]*'
            """
        ).fetchone()
        return f"VID-{row['next']:03d}"

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        publication_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(publications)").fetchall()
        }
        if "origin" not in publication_columns:
            connection.execute(
                "ALTER TABLE publications ADD COLUMN origin TEXT NOT NULL DEFAULT 'system'"
            )
        for column in ("claim_token", "lease_expires_at"):
            if column not in publication_columns:
                connection.execute(f"ALTER TABLE publications ADD COLUMN {column} TEXT")
        video_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(videos)").fetchall()
        }
        if "external_video_id" not in video_columns:
            connection.execute("ALTER TABLE videos ADD COLUMN external_video_id TEXT")
        batch_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(batches)").fetchall()
        }
        for column, declaration in (
            ("product_id", "TEXT"),
            ("brief", "TEXT NOT NULL DEFAULT ''"),
            ("reference_url", "TEXT"),
            ("script_settings_json", "TEXT"),
            ("note", "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in batch_columns:
                connection.execute(f"ALTER TABLE batches ADD COLUMN {column} {declaration}")
        workspace_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(workspace)").fetchall()
        }
        if "seed_version" not in workspace_columns:
            connection.execute("ALTER TABLE workspace ADD COLUMN seed_version INTEGER")
        script_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(scripts)").fetchall()
        }
        if "quality_json" not in script_columns:
            connection.execute("ALTER TABLE scripts ADD COLUMN quality_json TEXT")
        for column in ("claims_used_json", "claims_needing_evidence_json"):
            if column not in script_columns:
                connection.execute(
                    f"ALTER TABLE scripts ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]'"
                )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS videos_external_id_idx "
            "ON videos(external_video_id) WHERE external_video_id IS NOT NULL"
        )

    @staticmethod
    def _insert_video(connection: sqlite3.Connection, video: Video) -> None:
        connection.execute(
            """
            INSERT INTO videos
            (id, code, external_video_id, title, goal, product_id, parent_video_id,
             variation_note, batch_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video.id,
                video.code,
                video.external_video_id,
                video.title,
                video.goal,
                video.product_id,
                video.parent_video_id,
                video.variation_note,
                video.batch_id,
                video.created_at,
                video.updated_at,
            ),
        )
        connection.executemany(
            "INSERT INTO video_accounts (video_id, account_id) VALUES (?, ?)",
            [(video.id, account_id) for account_id in video.account_ids],
        )

    @staticmethod
    def _insert_context(connection: sqlite3.Connection, context: ContextSnapshot) -> None:
        sources = json.dumps(
            [item.model_dump() for item in context.sources],
            ensure_ascii=False,
        )
        connection.execute(
            """
            INSERT INTO contexts (id, video_id, version, brief, sources_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                context.id,
                context.video_id,
                context.version,
                context.brief,
                sources,
                context.created_at,
            ),
        )

    @staticmethod
    def _insert_script(connection: sqlite3.Connection, script: ScriptArtifact) -> None:
        connection.execute(
            """
            INSERT INTO scripts
            (id, video_id, version, source, content, note, quality_json,
             claims_used_json, claims_needing_evidence_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                script.id,
                script.video_id,
                script.version,
                script.source,
                script.content,
                script.note,
                (
                    json.dumps(script.quality.model_dump(), ensure_ascii=False)
                    if script.quality
                    else None
                ),
                SQLiteRepository._json(script.claims_used),
                SQLiteRepository._json(script.claims_needing_evidence),
                script.created_at,
            ),
        )

    @staticmethod
    def _insert_candidate(
        connection: sqlite3.Connection,
        candidate: ScriptCandidate,
    ) -> None:
        connection.execute(
            """
            INSERT INTO script_candidates
            (id, batch_id, position, title, angle, hypothesis, script, shots_json,
             provider, claims_used_json, claims_needing_evidence_json, quality_json,
             selected_video_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.id,
                candidate.batch_id,
                candidate.position,
                candidate.title,
                candidate.angle,
                candidate.hypothesis,
                candidate.script,
                SQLiteRepository._shots_json(candidate.shots),
                candidate.provider,
                SQLiteRepository._json(candidate.claims_used),
                SQLiteRepository._json(candidate.claims_needing_evidence),
                SQLiteRepository._json(candidate.quality.model_dump()),
                candidate.selected_video_id,
                candidate.created_at,
                candidate.updated_at,
            ),
        )

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _shots_json(shots: list) -> str:
        return SQLiteRepository._json([item.model_dump() for item in shots])

    @staticmethod
    def _insert_storyboard(
        connection: sqlite3.Connection,
        storyboard: StoryboardArtifact,
    ) -> None:
        shots = json.dumps(
            [item.model_dump() for item in storyboard.shots],
            ensure_ascii=False,
        )
        connection.execute(
            """
            INSERT INTO storyboards
            (id, video_id, version, source, shots_json, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                storyboard.id,
                storyboard.video_id,
                storyboard.version,
                storyboard.source,
                shots,
                storyboard.note,
                storyboard.created_at,
            ),
        )

    @staticmethod
    def _insert_publication(
        connection: sqlite3.Connection,
        publication: Publication,
    ) -> None:
        connection.execute(
            """
            INSERT INTO publications
            (id, video_id, account_id, status, origin, scheduled_at, published_at,
             external_id, url, error, warnings_json, raw_ref, claim_token,
             lease_expires_at, idempotency_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                publication.id,
                publication.video_id,
                publication.account_id,
                publication.status,
                publication.origin,
                publication.scheduled_at,
                publication.published_at,
                publication.external_id,
                publication.url,
                publication.error,
                json.dumps(publication.warnings, ensure_ascii=False),
                publication.raw_ref,
                publication.claim_token,
                publication.lease_expires_at,
                publication.idempotency_key,
                publication.created_at,
                publication.updated_at,
            ),
        )

    @staticmethod
    def _touch(connection: sqlite3.Connection, video_id: str, updated_at: str) -> None:
        connection.execute(
            "UPDATE videos SET updated_at = ? WHERE id = ?",
            (updated_at, video_id),
        )
