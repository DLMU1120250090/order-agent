# -*- coding: utf-8 -*-
"""
sitecustomize.py —— 项目级自动启动脚本（VS Code 便捷运行）

原理：
    当通过 VS Code 打开本项目【任意】.py 文件并点击右上角「运行」按钮
    （等价于执行 `python <文件>`）时，Python 解释器在启动阶段会自动导入
    sitecustomize 模块（前提：PYTHONPATH 包含本项目根目录，配置见
    .vscode/settings.json 的 python.terminal.env）。

    本脚本据此在后台线程中自动启动 FastAPI 服务（http://127.0.0.1:8080），
    因此：
      - 无需在 main.py 中编写 __main__ 入口；
      - 打开项目里任意 .py 文件直接点「运行」即可启动服务。

注意事项：
    - 若被运行的脚本本身是 uvicorn / pytest 等工具（如 run_app.bat、
      launch.json 中的 uvicorn 配置），会自动跳过，避免重复启动/端口冲突。
    - 自动启动使用 reload=False；修改代码后需重新点击运行。
    - 停止服务：在运行终端按 Ctrl+C，或直接关闭该终端。
    - 如需临时关闭自动启动：设置环境变量 DIET_AGENT_AUTOSTART=0。
"""
import os
import sys
import threading

_should_autostart = os.environ.get("DIET_AGENT_AUTOSTART", "1") != "0"


def _auto_start_fastapi():
    if not _should_autostart:
        return

    # 1) 工具类进程（uvicorn / pytest 等）不自动启动
    argv0 = (sys.argv[0] if sys.argv else "").replace("\\", "/").lower()
    if "uvicorn" in argv0 or "pytest" in argv0:
        return

    # 2) 8080 端口已被占用说明服务已在运行，不重复启动
    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 8080))
        port_free = True
    except OSError:
        port_free = False
    finally:
        probe.close()
    if not port_free:
        return

    # 3) 保证 app 包可从项目根目录导入
    project_root = os.path.dirname(os.path.abspath(__file__))
    try:
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        os.chdir(project_root)
    except Exception:
        return

    # 4) 使用「非守护线程」启动 uvicorn：
    #    即使被运行的脚本很快执行完毕并退出，该线程也会让进程保持存活，
    #    从而持续对外提供服务。
    def _serve():
        try:
            import uvicorn
            uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=False)
        except Exception as exc:  # noqa: BLE001
            print(f"[auto-start] Diet Agent 服务启动失败: {exc}")

    threading.Thread(target=_serve, name="diet-agent-autostart", daemon=False).start()
    print("[auto-start] 已自动启动 Diet Agent 服务 -> http://127.0.0.1:8080")


_auto_start_fastapi()
