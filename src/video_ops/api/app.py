"""FastAPI 组装层：同一条视频记录上的生产、发布、回流和裂变。"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from hashlib import sha256
from pathlib import Path
from typing import Annotated, BinaryIO
from uuid import uuid4

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from video_ops.adapters.mock_platform import MockPlatformAdapter
from video_ops.adapters.script_producers import default_script_producers
from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.adapters.youtube import YouTubePlatformAdapter
from video_ops.api.connectors import connectors_payload, resolve_active_script_producer
from video_ops.api.importer import (
    commit_import,
    export_interchange_csv,
    export_interchange_json,
    preview_import,
)
from video_ops.api.schemas import (
    ArrangePublicationsRequest,
    BranchVideoRequest,
    ConfirmPublicationAbsentRequest,
    CreateAccountGroupRequest,
    CreateAccountRequest,
    CreateBatchRequest,
    CreateProductRequest,
    CreateVideoRequest,
    ExecutePublicationRequest,
    GenerateArtifactsRequest,
    GenerateBatchRequest,
    ImportArtifactsRequest,
    ImportPublicationRequest,
    ReconcilePublicationRequest,
    RegenerateCandidateRequest,
    RegisterMediaRequest,
    SelectCandidatesRequest,
    UpdateCandidateRequest,
    UpdateScriptRequest,
    UpdateVideoTitleRequest,
    WorkspaceImportRequest,
)
from video_ops.api.worker import OperationsWorker
from video_ops.application.batch_generation import (
    edit_candidate,
    regenerate_candidate,
    select_candidates,
)
from video_ops.application.errors import ApplicationError
from video_ops.application.identifiers import new_id
from video_ops.application.seed import seed_demo
from video_ops.application.service import VideoOperationsService
from video_ops.config import Settings
from video_ops.domain.models import (
    Account,
    AccountGroup,
    ArtifactSource,
    ConnectionStatus,
    MediaArtifact,
    Product,
    VideoView,
    WorkspaceSnapshot,
)

LOGGER = logging.getLogger(__name__)
SAFE_UPLOAD_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
ERROR_STATUS = {
    "not_found": 404,
    "invalid_input": 422,
    "invalid_import": 422,
    "invalid_mapping": 422,
    "empty_import": 422,
    "invalid_account": 422,
    "invalid_group": 422,
    "invalid_connection": 422,
    "invalid_product": 422,
    "invalid_parent": 422,
    "invalid_batch": 422,
    "conflict": 409,
    "confirmation_required": 409,
    "missing_media": 409,
    "needs_reconciliation": 409,
    "not_published": 409,
    "connector_unavailable": 503,
    "auth_required": 401,
    "account_mismatch": 409,
    "external_id_conflict": 409,
    "duplicate": 409,
    "upload_too_large": 413,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    service = _build_service(settings)
    worker = OperationsWorker(
        service,
        poll_seconds=settings.worker_poll_seconds,
        metric_sync_seconds=settings.metric_sync_seconds,
    )
    app = FastAPI(
        title="AI 视频运营流水线",
        version="0.1.0",
        lifespan=_lifespan(worker, settings.worker_enabled),
    )
    app.state.service = service
    app.state.settings = settings
    app.state.active_script_producer = resolve_active_script_producer(settings)
    _configure_http(app, settings)
    _register_routes(app)
    _register_error_handlers(app)
    return app


def _build_service(settings: Settings) -> VideoOperationsService:
    repository = SQLiteRepository(settings.database_path)
    repository.initialize(mode=settings.mode)
    repository.set_mode(settings.mode)
    if settings.mode == "demo":
        seed_demo(repository, settings.sample_seed)
    adapters = {"mock-social": MockPlatformAdapter()}
    youtube = YouTubePlatformAdapter.from_environment(settings.app_root)
    if youtube:
        adapters["youtube"] = youtube
    service = VideoOperationsService(
        repository,
        platform_adapters=adapters,
        script_producer_factories=default_script_producers(),
    )
    service.recover_interrupted_publications()
    return service


def _lifespan(worker: OperationsWorker, enabled: bool):
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(worker.serve()) if enabled else None
        try:
            yield
        finally:
            if task:
                worker.stop()
                await task

    return lifespan


def _configure_http(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    settings.upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    app.mount("/files", StaticFiles(directory=settings.upload_dir), name="files")


def _register_routes(app: FastAPI) -> None:
    app.add_api_route("/api/health", _health, methods=["GET"])
    app.add_api_route("/api/workspace", _workspace, methods=["GET"])
    app.add_api_route("/api/connectors", _connectors, methods=["GET"])
    app.add_api_route("/api/account-groups", _create_group, methods=["POST"], status_code=201)
    app.add_api_route("/api/accounts", _create_account, methods=["POST"], status_code=201)
    app.add_api_route("/api/accounts/{account_id}/inspect", _inspect_account, methods=["POST"])
    app.add_api_route("/api/products", _create_product, methods=["POST"], status_code=201)
    app.add_api_route("/api/videos/{video_id}", _video_detail, methods=["GET"])
    app.add_api_route("/api/videos/{video_id}", _update_video, methods=["PATCH"])
    app.add_api_route("/api/videos", _create_video, methods=["POST"], status_code=201)
    _register_candidate_routes(app)
    app.add_api_route("/api/videos/{video_id}/generate", _generate, methods=["POST"])
    app.add_api_route("/api/videos/{video_id}/import", _import_artifacts, methods=["POST"])
    app.add_api_route("/api/videos/{video_id}/script", _update_script, methods=["POST"])
    app.add_api_route("/api/videos/{video_id}/media", _upload_media, methods=["POST"])
    app.add_api_route("/api/videos/{video_id}/media/register", _register_media, methods=["POST"])
    app.add_api_route("/api/media/{media_id}/content", _media_content, methods=["GET"])
    app.add_api_route("/api/videos/{video_id}/publications", _arrange, methods=["POST"])
    app.add_api_route(
        "/api/videos/{video_id}/publications/import",
        _import_publication,
        methods=["POST"],
    )
    app.add_api_route("/api/publications/{publication_id}/execute", _execute, methods=["POST"])
    app.add_api_route(
        "/api/publications/{publication_id}/reconcile",
        _reconcile,
        methods=["POST"],
    )
    app.add_api_route(
        "/api/publications/{publication_id}/confirm-absent",
        _confirm_absent,
        methods=["POST"],
    )
    app.add_api_route("/api/publications/{publication_id}/sync", _sync, methods=["POST"])
    app.add_api_route("/api/videos/{video_id}/branch", _branch, methods=["POST"], status_code=201)
    app.add_api_route("/api/videos/{video_id}/batch", _batch, methods=["POST"], status_code=201)
    app.add_api_route("/api/import/preview", _preview_workspace_import, methods=["POST"])
    app.add_api_route("/api/import/commit", _commit_workspace_import, methods=["POST"])
    app.add_api_route("/api/exports/workspace.json", _export_workspace_json, methods=["GET"])
    app.add_api_route("/api/exports/videos.json", _export_videos_json, methods=["GET"])
    app.add_api_route("/api/exports/videos.csv", _export_csv, methods=["GET"])


def _register_candidate_routes(app: FastAPI) -> None:
    app.add_api_route("/api/batches/generate", _generate_batch, methods=["POST"], status_code=201)
    app.add_api_route(
        "/api/batches/{batch_id}/candidates/{candidate_id}",
        _update_candidate,
        methods=["PATCH"],
    )
    app.add_api_route(
        "/api/batches/{batch_id}/candidates/{candidate_id}/regenerate",
        _regenerate_candidate,
        methods=["POST"],
    )
    app.add_api_route("/api/batches/{batch_id}/select", _select_candidates, methods=["POST"])


def _register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationError, _application_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unknown_error)


def _service(request: Request) -> VideoOperationsService:
    return request.app.state.service


async def _health(request: Request) -> dict:
    service = _service(request)
    return {
        "ok": True,
        "mode": service.snapshot().mode,
        "worker_enabled": request.app.state.settings.worker_enabled,
        "platforms": sorted(service.platform_adapters),
    }


async def _workspace(request: Request):
    snapshot = _service(request).snapshot().model_dump(mode="json")
    snapshot["active_script_producer"] = request.app.state.active_script_producer
    return snapshot


async def _connectors(request: Request):
    service = _service(request)
    return connectors_payload(
        request.app.state.settings,
        request.app.state.active_script_producer,
        set(service.platform_adapters),
    )


def _validate_producer(service: VideoOperationsService, producer: str) -> None:
    if producer not in service.script_producer_factories:
        raise ApplicationError(
            "unsupported",
            f"没有「{producer}」这个写脚本引擎，请刷新页面重新选择。",
        )


async def _create_group(body: CreateAccountGroupRequest, request: Request):
    service = _service(request)
    if body.name.strip() in {item.name for item in service.snapshot().account_groups}:
        raise ApplicationError("duplicate", "已有同名账号分组。")
    return service.create_group(
        AccountGroup(id=new_id("group"), name=body.name.strip(), sort_order=body.sort_order)
    )


async def _create_account(body: CreateAccountRequest, request: Request):
    service = _service(request)
    _validate_account(body, service)
    return service.create_account(
        Account(
            id=new_id("account"),
            group_id=body.group_id,
            name=body.name.strip(),
            handle=body.handle.strip(),
            platform=body.platform,
            connection_status=body.connection_status,
            context=body.context.strip(),
            connector_ref=body.connector_ref.strip() if body.connector_ref else None,
        )
    )


def _validate_account(body: CreateAccountRequest, service: VideoOperationsService) -> None:
    snapshot = service.snapshot()
    if body.group_id not in {item.id for item in snapshot.account_groups}:
        raise ApplicationError("invalid_group", "选择的账号分组不存在。")
    duplicate = any(
        item.platform == body.platform and item.handle == body.handle.strip()
        for item in snapshot.accounts
    )
    if duplicate:
        raise ApplicationError("duplicate", "该平台下已有同名账号。")
    if body.connection_status == ConnectionStatus.MOCK and body.platform != "mock-social":
        raise ApplicationError("invalid_connection", "只有样例平台可标记为 mock。")
    connected_without_adapter = (
        body.connection_status == ConnectionStatus.CONNECTED
        and body.platform not in service.platform_adapters
    )
    if connected_without_adapter:
        raise ApplicationError("invalid_connection", "该平台连接器未加载，不能标记为已连接。")


async def _inspect_account(account_id: str, request: Request):
    service = _service(request)
    result = service.inspect_account(account_id)
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    account = next(item for item in service.snapshot().accounts if item.id == account_id)
    adapter = service.platform_adapters[account.platform]
    result.update(
        {
            "account_id": account.id,
            "platform": account.platform,
            "connection_status": account.connection_status,
            "capabilities": adapter.capabilities(),
        }
    )
    return _sanitized_inspection(result)


def _sanitized_inspection(result: dict) -> dict:
    allowed = {
        "account_id",
        "platform",
        "connection_status",
        "platform_account_id",
        "display_name",
        "handle",
        "capabilities",
        "message",
    }
    return {key: value for key, value in result.items() if key in allowed}


async def _create_product(body: CreateProductRequest, request: Request):
    return _service(request).create_product(
        Product(
            id=new_id("product"),
            title=body.title.strip(),
            description=body.description.strip(),
            selling_points=[item.strip() for item in body.selling_points if item.strip()],
            url=body.url,
            image_url=body.image_url,
        )
    )


async def _video_detail(video_id: str, request: Request) -> VideoView:
    return _find_view(_service(request).snapshot(), video_id)


async def _update_video(video_id: str, body: UpdateVideoTitleRequest, request: Request):
    return _service(request).update_video_title(video_id, body.title)


async def _create_video(body: CreateVideoRequest, request: Request):
    return _service(request).create_video(
        title=body.title,
        goal=body.goal,
        account_ids=body.account_ids,
        product_id=body.product_id,
        brief=body.brief,
        sources=[item.model_dump() for item in body.sources],
        parent_video_id=body.parent_video_id,
        variation_note=body.variation_note,
        batch_id=body.batch_id,
    )


async def _generate_batch(body: GenerateBatchRequest, request: Request):
    _validate_producer(_service(request), body.producer)
    batch, candidates = await asyncio.to_thread(
        _service(request).generate_batch,
        product_id=body.product_id,
        brief=body.brief,
        reference_url=body.reference_url,
        count=body.count,
        producer=body.producer,
        script_settings=(
            body.script_settings.model_dump() if body.script_settings is not None else None
        ),
    )
    return {"batch": batch, "candidates": candidates}


async def _update_candidate(
    batch_id: str,
    candidate_id: str,
    body: UpdateCandidateRequest,
    request: Request,
):
    return edit_candidate(
        _service(request),
        batch_id,
        candidate_id,
        title=body.title,
        script=body.script,
        shots=body.shots,
    )


async def _regenerate_candidate(
    batch_id: str,
    candidate_id: str,
    body: RegenerateCandidateRequest,
    request: Request,
):
    _validate_producer(_service(request), body.producer)
    return await asyncio.to_thread(
        regenerate_candidate,
        _service(request),
        batch_id,
        candidate_id,
        producer=body.producer,
    )


async def _select_candidates(
    batch_id: str,
    body: SelectCandidatesRequest,
    request: Request,
):
    videos = select_candidates(_service(request), batch_id, body.candidate_ids)
    return {"videos": videos}


async def _generate(video_id: str, body: GenerateArtifactsRequest, request: Request):
    _validate_producer(_service(request), body.producer)
    return await asyncio.to_thread(
        _service(request).generate_artifacts,
        video_id,
        instruction=body.instruction,
        producer=body.producer,
    )


async def _import_artifacts(video_id: str, body: ImportArtifactsRequest, request: Request):
    shots = [item.model_dump() for item in body.shots] if body.shots else None
    return _service(request).import_artifacts(
        video_id,
        script=body.script,
        shots=shots,
        note=body.note,
    )


async def _update_script(video_id: str, body: UpdateScriptRequest, request: Request):
    service = _service(request)
    shots = [item.model_dump() for item in body.shots] if body.shots is not None else None
    return service.update_artifacts(video_id, content=body.content, shots=shots, note=body.note)


async def _upload_media(
    video_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
):
    settings: Settings = request.app.state.settings
    service = _service(request)
    _find_view(service.snapshot(), video_id)
    stored = await _store_upload(file, video_id, settings)
    try:
        return service.register_media(video_id, **stored)
    except Exception:
        _discard_upload(stored["storage_path"])
        raise


async def _register_media(video_id: str, body: RegisterMediaRequest, request: Request):
    settings: Settings = request.app.state.settings
    return _service(request).register_media(
        video_id,
        file_name=body.file_name,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        checksum=body.checksum,
        storage_path=_registered_media_path(body.storage_path, settings.upload_dir),
        source=ArtifactSource(body.source),
    )


async def _media_content(media_id: str, request: Request) -> FileResponse:
    media = _find_media(_service(request).snapshot(), media_id)
    path = _readable_media_path(media.storage_path, request.app.state.settings.upload_dir)
    return FileResponse(
        path,
        media_type=media.mime_type,
        filename=media.file_name,
        content_disposition_type="inline",
    )


async def _store_upload(file: UploadFile, video_id: str, settings: Settings) -> dict:
    file_name = Path(file.filename or "video.bin").name
    target_dir = _upload_directory(settings.upload_dir, video_id)
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    target_dir.chmod(0o700)
    target = target_dir / f"{uuid4().hex[:12]}-{file_name}"
    try:
        target.touch(mode=0o600, exist_ok=False)
        size, checksum = await _run_upload_copy(
            file.file,
            target,
            settings.max_upload_bytes,
        )
        await file.close()
    except BaseException:
        _discard_upload(str(target))
        with suppress(BaseException):
            await file.close()
        raise
    if size == 0:
        _discard_upload(str(target))
        raise ApplicationError("invalid_input", "成片文件为空，请重新选择。")
    return {
        "file_name": file_name,
        "mime_type": file.content_type or "application/octet-stream",
        "size_bytes": size,
        "checksum": checksum,
        "storage_path": str(target.resolve()),
    }


async def _run_upload_copy(
    source: BinaryIO,
    target: Path,
    max_bytes: int,
) -> tuple[int, str]:
    task = asyncio.create_task(asyncio.to_thread(_copy_upload, source, target, max_bytes))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await _wait_for_upload_copy(task)
        raise


async def _wait_for_upload_copy(task: asyncio.Task) -> None:
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except Exception:
            return
    if not task.cancelled():
        with suppress(Exception):
            task.result()


def _upload_directory(root: Path, video_id: str) -> Path:
    if not SAFE_UPLOAD_SEGMENT.fullmatch(video_id):
        raise ApplicationError("invalid_input", "视频编号不合法，无法保存成片。")
    resolved_root = root.expanduser().resolve()
    target = (resolved_root / video_id).resolve()
    if not target.is_relative_to(resolved_root):
        raise ApplicationError("invalid_input", "视频编号超出成片存储范围。")
    return target


def _registered_media_path(raw: str, root: Path) -> str:
    try:
        candidate = Path(raw).expanduser().resolve(strict=True)
    except OSError as error:
        raise ApplicationError("invalid_input", "登记的成片文件不存在。") from error
    if not candidate.is_file() or not candidate.is_relative_to(root.expanduser().resolve()):
        raise ApplicationError("invalid_input", "只能登记成片存储目录内的文件。")
    return str(candidate)


def _readable_media_path(raw: str, root: Path) -> Path:
    try:
        candidate = Path(raw).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ApplicationError("not_found", "成片文件不可读取，请重新上传。") from error
    resolved_root = root.expanduser().resolve()
    if not candidate.is_file() or not candidate.is_relative_to(resolved_root):
        raise ApplicationError("not_found", "成片文件不可读取，请重新上传。")
    return candidate


def _discard_upload(raw: str) -> None:
    path = Path(raw)
    with suppress(OSError):
        path.unlink(missing_ok=True)
    with suppress(OSError):
        path.parent.rmdir()


def _copy_upload(source: BinaryIO, target: Path, max_bytes: int) -> tuple[int, str]:
    digest = sha256()
    size = 0
    source.seek(0)
    with target.open("wb") as destination:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ApplicationError("upload_too_large", "成片文件超过当前上传上限。")
            digest.update(chunk)
            destination.write(chunk)
    return size, digest.hexdigest()


async def _arrange(video_id: str, body: ArrangePublicationsRequest, request: Request):
    return _service(request).arrange_publications(
        video_id,
        account_ids=body.account_ids,
        scheduled_at=body.scheduled_at,
        auto_execute_mock=body.auto_execute_mock,
    )


async def _import_publication(video_id: str, body: ImportPublicationRequest, request: Request):
    return _service(request).import_publication(
        video_id,
        account_id=body.account_id,
        external_id=body.external_id,
        url=body.url,
        published_at=body.published_at,
    )


async def _execute(publication_id: str, body: ExecutePublicationRequest, request: Request):
    return await asyncio.to_thread(
        _service(request).execute_publication,
        publication_id,
        confirmed=body.confirmed,
    )


async def _reconcile(
    publication_id: str,
    body: ReconcilePublicationRequest,
    request: Request,
):
    return _service(request).reconcile_publication(
        publication_id,
        external_id=body.external_id,
        url=body.url,
        published_at=body.published_at,
    )


async def _confirm_absent(
    publication_id: str,
    body: ConfirmPublicationAbsentRequest,
    request: Request,
):
    return _service(request).confirm_publication_absent(publication_id, note=body.note)


async def _sync(publication_id: str, request: Request):
    return await asyncio.to_thread(_service(request).sync_publication, publication_id)


async def _branch(video_id: str, body: BranchVideoRequest, request: Request):
    return _service(request).branch_video(
        video_id,
        variation=body.variation,
        comment_ids=body.comment_ids,
    )


async def _batch(video_id: str, body: CreateBatchRequest, request: Request):
    return _service(request).create_batch(video_id, name=body.name, variations=body.variations)


async def _preview_workspace_import(body: WorkspaceImportRequest, request: Request):
    return preview_import(
        _service(request).snapshot(),
        data_format=body.format,
        payload=body.payload,
        mapping=body.mapping,
    )


async def _commit_workspace_import(body: WorkspaceImportRequest, request: Request):
    service = _service(request)
    preview = preview_import(
        service.snapshot(),
        data_format=body.format,
        payload=body.payload,
        mapping=body.mapping,
    )
    return commit_import(service, preview)


async def _export_workspace_json(request: Request) -> Response:
    content = _service(request).snapshot().model_dump_json(indent=2)
    headers = {"Content-Disposition": 'attachment; filename="workspace-backup.json"'}
    return Response(content=content, media_type="application/json", headers=headers)


async def _export_videos_json(request: Request) -> Response:
    content = export_interchange_json(_service(request).snapshot())
    headers = {"Content-Disposition": 'attachment; filename="videos-importable.json"'}
    return Response(content=content, media_type="application/json", headers=headers)


async def _export_csv(request: Request) -> Response:
    content = export_interchange_csv(_service(request).snapshot())
    headers = {"Content-Disposition": 'attachment; filename="videos-export.csv"'}
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


def _find_view(snapshot: WorkspaceSnapshot, video_id: str) -> VideoView:
    view = next((item for item in snapshot.videos if item.video.id == video_id), None)
    if view is None:
        raise ApplicationError("not_found", "没有找到这条视频。")
    return view


def _find_media(snapshot: WorkspaceSnapshot, media_id: str) -> MediaArtifact:
    for view in snapshot.videos:
        media = next((item for item in view.video.media if item.id == media_id), None)
        if media is not None:
            return media
    raise ApplicationError("not_found", "没有找到这份成片。")


def _error_response(status_code: int, code: str, message: str, retryable: bool = False):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "retryable": retryable}},
    )


async def _application_error(_request: Request, exc: ApplicationError):
    return _error_response(ERROR_STATUS.get(exc.code, 400), exc.code, exc.message, exc.retryable)


async def _validation_error(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(item) for item in first.get("loc", []) if item != "body")
    detail = first.get("msg", "请检查输入。")
    message = f"{location}：{detail}" if location else detail
    return _error_response(422, "validation_error", message)


async def _http_error(_request: Request, exc: StarletteHTTPException):
    return _error_response(exc.status_code, "http_error", str(exc.detail))


async def _unknown_error(request: Request, exc: Exception):
    LOGGER.exception("未处理的 API 错误: %s %s", request.method, request.url.path, exc_info=exc)
    return _error_response(500, "internal_error", "服务暂时无法完成这个操作。", True)
