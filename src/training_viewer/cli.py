"""Training Viewer 命令行入口。

`training-viewer open <目录>` 启动本机服务并打开浏览器；若同一数据目录已有实例，
会复用该实例并只添加新目录，不会启动第二个重复服务。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import APP_DISPLAY_NAME, __version__
from .api.app import create_application
from .application_paths import ApplicationDataDirectoryError, ApplicationPaths
from .log_validation import validate_run_directory
from .service import TrainingViewerService


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _configure_console_encoding() -> None:
    """Windows 管道/重定向时默认编码可能无法输出中文，显式改用 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _request_json(method: str, url: str, payload: dict | None = None, timeout: float = 2.0):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _read_instance(paths: ApplicationPaths) -> dict | None:
    try:
        payload = json.loads(paths.instance_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or "url" not in payload:
        return None
    return payload


def _healthy_instance(paths: ApplicationPaths) -> dict | None:
    instance = _read_instance(paths)
    if instance is None:
        return None
    url = str(instance.get("url", "")).rstrip("/")
    if not url.startswith("http://127.0.0.1:") and not url.startswith("http://localhost:"):
        return None
    try:
        health = _request_json("GET", f"{url}/api/v1/health", timeout=1.5)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if health.get("application") != "training-viewer":
        return None
    instance["url"] = url
    return instance


def _add_roots_to_instance(url: str, paths: list[str]) -> None:
    for path in paths:
        try:
            _request_json("POST", f"{url}/api/v1/roots", {"path": str(Path(path).expanduser().resolve())})
            print(f"已添加扫描目录：{path}")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            print(f"添加目录失败 {path}：{error}", file=sys.stderr)


def _find_available_port(host: str, preferred: int, attempts: int = 25) -> int:
    for offset in range(attempts):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            # Windows 的 SO_REUSEADDR 会允许绑定到已监听端口，不能用于探测；
            # POSIX 上它可避免 TIME_WAIT 阻止重新使用端口。
            if os.name != "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
        return port
    raise RuntimeError(f"在 {preferred}–{preferred + attempts - 1} 范围内找不到空闲端口")


def _open_browser_later(url: str, delay_seconds: float = 1.2) -> None:
    timer = threading.Timer(delay_seconds, lambda: webbrowser.open(url))
    timer.daemon = True
    timer.start()


def _write_instance(paths: ApplicationPaths, url: str, port: int) -> None:
    payload = {
        "url": url,
        "port": port,
        "pid": os.getpid(),
        "data_dir": str(paths.data_dir),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    temporary = paths.instance_file.with_name(paths.instance_file.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(paths.instance_file)


def _clear_instance(paths: ApplicationPaths) -> None:
    try:
        payload = json.loads(paths.instance_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if payload.get("pid") == os.getpid():
        try:
            paths.instance_file.unlink()
        except OSError:
            pass


def _run_server(
    paths: ApplicationPaths,
    host: str,
    port: int,
    open_browser: bool,
    interval: float,
) -> int:
    import uvicorn

    service = TrainingViewerService(paths, scan_interval_seconds=interval)
    app = create_application(paths, service, start_background_sync=True)
    url = f"http://{host}:{port}/"
    _write_instance(paths, url, port)
    if not (paths.web_dir / "index.html").is_file():
        print(
            "提示：当前安装缺少前端静态资源。请在源码的 frontend/ 目录执行 "
            "npm install && npm run build 后重新安装。API 仍可访问。",
            file=sys.stderr,
        )
    print(f"{APP_DISPLAY_NAME} 已启动：{url}")
    print(f"数据目录：{paths.data_dir}（只保存索引与界面数据）")
    print("按 Ctrl+C 停止服务；训练任务不会受影响。")
    if open_browser:
        _open_browser_later(url)
    try:
        uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)
    finally:
        _clear_instance(paths)
    return 0


def _wait_for_health(host: str, port: int, timeout_seconds: float = 25.0) -> dict | None:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://{host}:{port}/api/v1/health"
    while time.monotonic() < deadline:
        try:
            health = _request_json("GET", url, timeout=1.5)
            if health.get("application") == "training-viewer":
                return health
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        time.sleep(0.4)
    return None


def _start_detached_server(
    paths: ApplicationPaths,
    host: str,
    port: int,
    interval: float,
) -> tuple[subprocess.Popen, Path]:
    """把 serve 作为后台进程启动，供训练 Agent 在结束会话后继续可视化。"""
    log_path = paths.data_dir / "server.log"
    command = [
        sys.executable,
        "-m",
        "training_viewer",
        "serve",
        "--host",
        host,
        "--port",
        str(port),
        "--no-browser",
        "--data-dir",
        str(paths.data_dir),
        "--interval",
        str(interval),
    ]
    creationflags = 0
    start_new_session = os.name != "nt"
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    log_file = log_path.open("ab")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            start_new_session=start_new_session,
            close_fds=True,
        )
    finally:
        log_file.close()
    return process, log_path


def _post_root(base_url: str, root: str) -> dict:
    return _request_json("POST", f"{base_url.rstrip('/')}/api/v1/roots", {"path": root})


def _run_count(base_url: str) -> int | None:
    try:
        return int(_request_json("GET", f"{base_url.rstrip('/')}/api/v1/runs?limit=1").get("total", 0))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
        return None


def _attach_command(args: argparse.Namespace) -> int:
    paths = ApplicationPaths.resolve(args.data_dir)
    roots = []
    for path in args.paths:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            print(f"目录不存在或不是目录：{resolved}", file=sys.stderr)
            return 2
        roots.append(str(resolved))

    existing = _healthy_instance(paths)
    started = False
    started_pid = None
    log_path: Path | None = None
    if existing is not None:
        url = existing["url"].rstrip("/")
    else:
        if args.no_start:
            print("没有找到已运行的 Training Viewer，且指定了 --no-start。", file=sys.stderr)
            return 2
        port = _find_available_port(args.host, args.port)
        if port != args.port:
            print(f"端口 {args.port} 已被占用，后台服务改用 {port}。", file=sys.stderr)
        process, log_path = _start_detached_server(paths, args.host, port, args.interval)
        health = _wait_for_health(args.host, port)
        if health is None:
            print("后台服务启动失败。最近的服务日志：", file=sys.stderr)
            if log_path.exists():
                for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]:
                    print(line, file=sys.stderr)
            return 2
        url = f"http://{args.host}:{port}"
        started = True
        started_pid = process.pid
    if not started:
        started_pid = None

    added_roots = []
    for root in roots:
        try:
            added_roots.append(_post_root(url, root))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            print(f"添加目录失败 {root}：{error}", file=sys.stderr)
            return 2

    instance = _read_instance(paths) or {}
    payload = {
        "status": "ok",
        "url": f"{url}/",
        "started": started,
        "roots": added_roots,
        "data_dir": str(paths.data_dir),
        "pid": instance.get("pid") or started_pid,
        "run_total": _run_count(url),
        "server_log": str(log_path) if log_path is not None else None,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Training Viewer 已接入：{payload['url']}")
        for root in added_roots:
            print(f"已添加扫描目录：{root.get('path', '')}")
        print(f"数据目录：{paths.data_dir}")
        if started:
            print(f"后台服务已启动，日志：{payload['server_log']}")
        if payload["run_total"] is not None:
            print(f"当前已索引运行数：{payload['run_total']}")
        if not args.no_browser:
            webbrowser.open(payload["url"])
    return 0


def _status_command(args: argparse.Namespace) -> int:
    paths = ApplicationPaths.resolve(args.data_dir)
    instance = _healthy_instance(paths)
    if instance is None:
        if args.json:
            print(json.dumps({"status": "stopped", "data_dir": str(paths.data_dir)}, ensure_ascii=False))
        else:
            print("Training Viewer 未运行。")
        return 1
    url = instance["url"].rstrip("/")
    health = _request_json("GET", f"{url}/api/v1/health")
    run_total = _run_count(url)
    payload = {
        "status": "running",
        "url": f"{url}/",
        "pid": instance.get("pid"),
        "data_dir": str(paths.data_dir),
        "index_version": health.get("version"),
        "last_sync_at": health.get("last_sync_at"),
        "run_total": run_total,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Training Viewer 正在运行：{payload['url']}")
        print(f"进程号：{payload['pid']}  索引版本：{payload['index_version']}  运行数：{run_total}")
        print(f"最后同步：{payload['last_sync_at']}")
        print(f"数据目录：{paths.data_dir}")
    return 0


def _stop_command(args: argparse.Namespace) -> int:
    paths = ApplicationPaths.resolve(args.data_dir)
    instance = _healthy_instance(paths)
    if instance is None:
        if args.json:
            print(json.dumps({"status": "stopped", "data_dir": str(paths.data_dir)}, ensure_ascii=False))
        else:
            print("Training Viewer 未运行。")
        return 1
    pid = instance.get("pid")
    if not isinstance(pid, int):
        print("实例文件缺少有效的进程号，无法停止。", file=sys.stderr)
        return 2
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as error:
        print(f"停止进程 {pid} 失败：{error}", file=sys.stderr)
        return 2
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _healthy_instance(paths) is None:
            break
        time.sleep(0.2)
    _clear_instance(paths)
    payload = {"status": "stopped", "pid": pid, "data_dir": str(paths.data_dir)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"已停止 Training Viewer（进程号 {pid}）。")
    return 0


def _open_command(args: argparse.Namespace) -> int:
    paths = ApplicationPaths.resolve(args.data_dir)
    existing = _healthy_instance(paths)
    if existing is not None:
        url = existing["url"]
        print(f"复用已运行的实例：{url}")
        _add_roots_to_instance(url, args.paths)
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    roots = [str(Path(path).expanduser().resolve()) for path in args.paths]
    for root in roots:
        if not Path(root).is_dir():
            print(f"目录不存在或不是目录：{root}", file=sys.stderr)
            return 2
    port = _find_available_port(args.host, args.port)
    if port != args.port:
        print(f"端口 {args.port} 已被占用，改用 {port}。")
    service = TrainingViewerService(paths, scan_interval_seconds=args.interval)
    if not roots:
        restored = service.list_roots()
        if restored:
            print(f"恢复上次工作区：{len(restored)} 个日志根目录。")
    for root in roots:
        try:
            service.add_root(root)
            print(f"已添加扫描目录：{root}")
        except ValueError as error:
            print(f"添加目录失败：{error}", file=sys.stderr)
            return 2
    app = create_application(paths, service, start_background_sync=True)
    url = f"http://{args.host}:{port}/"
    _write_instance(paths, url, port)
    if not (paths.web_dir / "index.html").is_file():
        print(
            "提示：当前安装缺少前端静态资源。请在源码的 frontend/ 目录执行 "
            "npm install && npm run build 后重新安装。API 仍可访问。",
            file=sys.stderr,
        )
    print(f"{APP_DISPLAY_NAME} 已启动：{url}")
    print(f"数据目录：{paths.data_dir}（只保存索引与界面数据）")
    print("按 Ctrl+C 停止服务；训练任务不会受影响。")
    if not args.no_browser:
        _open_browser_later(url)
    import uvicorn

    try:
        uvicorn.run(app, host=args.host, port=port, log_level="info", access_log=False)
    finally:
        _clear_instance(paths)
    return 0


def _serve_command(args: argparse.Namespace) -> int:
    paths = ApplicationPaths.resolve(args.data_dir)
    port = _find_available_port(args.host, args.port)
    return _run_server(paths, args.host, port, not args.no_browser, args.interval)


def _validate_command(args: argparse.Namespace) -> int:
    paths = ApplicationPaths.resolve(args.data_dir)
    schema_dir = paths.schema_dir
    if not schema_dir.is_dir():
        repository_schemas = Path(__file__).resolve().parents[2] / "schemas"
        if repository_schemas.is_dir():
            schema_dir = repository_schemas
    report = validate_run_directory(Path(args.path).expanduser().resolve(), schema_dir)
    if args.json:
        print(
            json.dumps(
                {
                    "run_directory": str(report.run_directory),
                    "checked_records": report.checked_records,
                    "error_count": report.error_count,
                    "warning_count": report.warning_count,
                    "messages": [message.__dict__ for message in report.messages],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"运行目录：{report.run_directory}")
        print(f"检查记录：{report.checked_records}")
        for message in report.messages:
            location = message.file_name or "目录"
            if message.line_number:
                location += f":{message.line_number}"
            print(f"[{message.level.upper()}] {location}  {message.message}")
        print(
            f"校验完成：错误 {report.error_count} 条，警告 {report.warning_count} 条。"
            + ("协议校验通过。" if report.error_count == 0 else "")
        )
    return 1 if report.error_count else 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="training-viewer",
        description="本机深度学习训练实验查看器：读取 TVLP 1.0 日志、显示曲线、对比实验与预测结果。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser(
        "open", help="启动查看器并打开一个或多个训练日志根目录"
    )
    open_parser.add_argument("paths", nargs="*", help="要扫描的本机目录（可多个）")
    open_parser.add_argument("--port", type=int, default=8765, help="首选端口，默认 8765")
    open_parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机 127.0.0.1")
    open_parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    open_parser.add_argument("--data-dir", default=None, help="应用数据目录（索引与界面数据）")
    open_parser.add_argument("--interval", type=float, default=2.0, help="轮询扫描间隔秒数，默认 2")
    open_parser.set_defaults(handler=_open_command)

    serve_parser = subparsers.add_parser("serve", help="只启动服务，不自动添加目录")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--no-browser", action="store_true")
    serve_parser.add_argument("--data-dir", default=None)
    serve_parser.add_argument("--interval", type=float, default=2.0)
    serve_parser.set_defaults(handler=_serve_command)

    validate_parser = subparsers.add_parser("validate", help="按 TVLP 1.0 校验一个 Run 目录")
    validate_parser.add_argument("path", help="包含 run.json 的运行目录")
    validate_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    validate_parser.add_argument("--data-dir", default=None)
    validate_parser.set_defaults(handler=_validate_command)

    attach_parser = subparsers.add_parser(
        "attach",
        help="把一个或多个训练日志目录接入后台查看器；训练 Agent 用这一条命令",
    )
    attach_parser.add_argument("paths", nargs="+", help="训练日志根目录（可多个）")
    attach_parser.add_argument("--port", type=int, default=8765)
    attach_parser.add_argument("--host", default="127.0.0.1")
    attach_parser.add_argument("--data-dir", default=None, help="应用数据目录")
    attach_parser.add_argument("--interval", type=float, default=2.0)
    attach_parser.add_argument("--no-start", action="store_true", help="只连接已运行实例，不启动新服务")
    attach_parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    attach_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（不打开浏览器）")
    attach_parser.set_defaults(handler=_attach_command)

    status_parser = subparsers.add_parser("status", help="查看后台查看器是否运行")
    status_parser.add_argument("--data-dir", default=None)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(handler=_status_command)

    stop_parser = subparsers.add_parser("stop", help="停止通过 attach/serve 启动的本机实例")
    stop_parser.add_argument("--data-dir", default=None)
    stop_parser.add_argument("--json", action="store_true")
    stop_parser.set_defaults(handler=_stop_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    _configure_logging()
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except ApplicationDataDirectoryError as error:
        print(str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已停止。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
