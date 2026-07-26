"""
全局日志系统
- 控制台彩色输出（开发友好）
- 文件持久化（logs/app.log，按天轮转）
- 每个请求分配唯一 rid，全链路追踪
"""
import logging
import logging.handlers
import os
import sys
import time
import uuid
from datetime import datetime
from functools import wraps
from flask import request, g, has_request_context

# ---- 日志目录 ----
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ---- 格式 ----
CONSOLE_FMT = (
    "\033[2m%(asctime)s\033[0m "
    "%(levelname_color)s%(levelname)-8s\033[0m "
    "\033[36m%(name)s\033[0m "
    "%(rid)s"
    "%(message)s"
)
FILE_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(rid)s | %(message)s"


class ColoredFormatter(logging.Formatter):
    """控制台彩色日志"""

    LEVEL_COLORS = {
        "DEBUG": "\033[90m",     # 灰色
        "INFO": "\033[92m",      # 绿色
        "WARNING": "\033[93m",   # 黄色
        "ERROR": "\033[91m",     # 红色
        "CRITICAL": "\033[1;91m",  # 加粗红色
    }

    def format(self, record):
        record.rid = getattr(record, "rid", "")
        level = record.levelname
        record.levelname_color = self.LEVEL_COLORS.get(level, "")
        return super().format(record)


class RequestFilter(logging.Filter):
    """注入请求上下文 rid"""

    def filter(self, record):
        if not hasattr(record, "rid") or not record.rid:
            if has_request_context():
                record.rid = f"[{g.get('rid', '--------')}] "
            else:
                record.rid = "[--------] "
        else:
            record.rid = f"[{record.rid[:8]}] "
        return True


# ---- 构建 logger 实例 ----
def _build_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    rid_filter = RequestFilter()

    # 控制台 handler
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(ColoredFormatter(CONSOLE_FMT, datefmt="%H:%M:%S"))
        ch.addFilter(rid_filter)
        logger.addHandler(ch)

    # 文件 handler（所有日志写到一个文件）
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers):
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(LOG_DIR, "app.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=7,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(FILE_FMT, datefmt="%Y-%m-%d %H:%M:%S"))
        fh.addFilter(rid_filter)
        logger.addHandler(fh)

    return logger


# 为了支持不同模块独立 logger，这里用一个工厂缓存
_loggers: dict[str, logging.Logger] = {}


def get_logger(name="app"):
    """获取模块级 logger"""
    if name not in _loggers:
        _loggers[name] = _build_logger(name)
    return _loggers[name]


# ---- Flask 中间件：请求全生命周期日志 ----
def init_app_logging(app):
    """注册到 Flask app 的请求日志钩子"""

    log = get_logger("request")

    @app.before_request
    def _before():
        g.rid = uuid.uuid4().hex[:12]
        g.start_time = time.time()

        # 请求基本信息
        parts = [f"\033[1m{request.method}\033[0m {request.path}"]
        if request.args:
            parts.append(f"  \033[2mquery:\033[0m {dict(request.args)}")
        if request.form:
            safe_form = {k: v[:100] if len(v) > 100 else v for k, v in request.form.items()}
            parts.append(f"  \033[2mform:\033[0m {safe_form}")
        if request.files:
            parts.append(f"  \033[2mfiles:\033[0m {list(request.files.keys())}")
        if request.is_json and request.get_data():
            body = request.get_data(as_text=True)[:500]
            parts.append(f"  \033[2mbody:\033[0m {body}")

        log.info(" → " + " | ".join(parts))

    @app.after_request
    def _after(response):
        elapsed = (time.time() - g.get("start_time", time.time())) * 1000
        status = response.status_code

        # 根据状态码选颜色
        if status < 300:
            color = "\033[92m"
        elif status < 400:
            color = "\033[93m"
        else:
            color = "\033[91m"

        log.info(
            f" ← {color}{status}\033[0m "
            f"{response.content_length or '-'}B "
            f"\033[2m{elapsed:.1f}ms\033[0m"
        )
        return response

    @app.teardown_request
    def _teardown(exc):
        if exc:
            log.error(
                f" 💥 请求异常: {type(exc).__name__}: {exc}",
                exc_info=True,
            )


# ---- 装饰器：函数级日志 ----
def log_call(name=None):
    """记录函数调用、参数、返回值、耗时"""
    def deco(fn):
        fn_name = name or fn.__name__
        log = get_logger(f"func.{fn_name}")

        @wraps(fn)
        def wrapper(*args, **kwargs):
            # 精简参数
            args_repr = [repr(a)[:60] for a in args[:3]]
            if len(args) > 3:
                args_repr.append(f"...+{len(args) - 3}")
            kw_repr = {k: repr(v)[:80] for k, v in list(kwargs.items())[:5]}
            log.debug(f"▶ {fn_name}({', '.join(args_repr)}, **{{{', '.join(f'{k}=...' for k in kw_repr)}}})")
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
                elapsed = (time.time() - t0) * 1000
                result_repr = repr(result)[:120] if result is not None else "None"
                log.debug(f"■ {fn_name} → {result_repr}  \033[2m{elapsed:.1f}ms\033[0m")
                return result
            except Exception as e:
                elapsed = (time.time() - t0) * 1000
                log.error(f"☠ {fn_name} {type(e).__name__}: {e}  \033[2m{elapsed:.1f}ms\033[0m", exc_info=True)
                raise

        return wrapper
    return deco
