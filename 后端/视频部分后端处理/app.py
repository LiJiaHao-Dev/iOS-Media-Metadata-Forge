"""
视频元数据修改后端 —— 商用精简版
架构：Flask + Gunicorn
流程：FFmpeg (-c copy 重封装) → ExifTool (全命名空间机型注入)
环境：Debian 12 + Python 3.11+ + ffmpeg + exiftool
"""

import os
import uuid
import subprocess
import threading
import time
import logging
from pathlib import Path

from flask import Flask, request, jsonify, send_file, after_this_request
from flask_cors import CORS
from werkzeug.utils import secure_filename

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE_DIR           = Path(__file__).parent
UPLOAD_DIR         = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "mov"}
MAX_UPLOAD_BYTES   = 4 * 1024 * 1024 * 1024   # 4 GB
CLEANUP_DELAY_SEC  = 300                        # 文件保留 300 秒后自动删除

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Flask
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

CORS(
    app,
    resources={r"/api/*": {"origins": "https://jz.8866520.xyz"}},
    supports_credentials=True,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def schedule_delete(*paths: str, delay: float = CLEANUP_DELAY_SEC) -> None:
    """
    后台守护线程：delay 秒后静默删除所有指定路径的临时文件。
    设计：daemon=True 确保主进程退出时线程不会阻塞。
    """
    def _worker():
        time.sleep(delay)
        for p in paths:
            try:
                os.remove(p)
                log.info("已清理：%s", p)
            except FileNotFoundError:
                pass
            except OSError as e:
                log.warning("清理失败 %s：%s", p, e)

    threading.Thread(target=_worker, daemon=True).start()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 步骤 A：FFmpeg 极速重封装
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def remux_to_mov(src: str, out: str) -> None:
    """
    将用户视频原样重封装进 MOV 容器，不做任何重编码。

    -c copy                   所有流原样复制，零质量损失，秒级完成
    -map 0                    保留输入的全部流（视频+音频+字幕）
    -ignore_unknown           遇到不认识的私有流静默跳过，不报错
    -movflags +faststart      moov 盒子前置，iOS 打开更流畅
              +use_metadata_tags  允许写入苹果私有键，为 ExifTool 铺垫
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", src,
        "-map", "0",
        "-c", "copy",
        "-ignore_unknown",
        "-movflags", "+faststart+use_metadata_tags",
        out,
    ]
    log.info("[FFmpeg] %s", " ".join(cmd))

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        err = (r.stderr or "")[-1000:]
        log.error("[FFmpeg] 失败：\n%s", err)
        raise RuntimeError(f"FFmpeg 重封装失败：{err[-300:]}")

    log.info("[FFmpeg] 完成 → %s（%.1f MB）",
             out, os.path.getsize(out) / 1024 / 1024)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 步骤 B：ExifTool 全命名空间元数据注入
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def inject_metadata(filepath: str, make: str, model: str, date: str) -> None:
    """
    对 MOV 文件执行"地毯式"元数据注入。

    iOS 相册读取机型信息时，会依次查找多个命名空间，
    命中任意一个即显示。全部写入确保万无一失：

      QuickTime:   moov/udta/meta/keys 盒子（iOS 首选读取路径）
      Keys:        moov/meta/keys 盒子（iOS 18 新增路径）
      UserData:    moov/udta 盒子（传统路径）
      ItemList:    moov/udta/meta/ilst（com.apple.quicktime.* 旧式路径）

    净身逻辑（先清空再写入）：
      FFmpeg 默认将 HandlerName 写为 "VideoHandler"，iOS 一眼识破。
      同一 exiftool 调用中参数从左到右顺序执行：
        "-HandlerName=" → 清空
        "-HandlerName=Core Media Video" → 写入正确值
      两步合并为一次调用，高效且原子。
    """
    cmd = [
        "exiftool",
        "-overwrite_original",   # 原地修改，不生成 _original 备份
        "-P",                    # 保留文件系统修改时间

        # ── 净身：清除 FFmpeg 编码器指纹 ──────────
        "-QuickTime:HandlerName=",
        "-QuickTime:VideoHandlerName=",
        "-QuickTime:AudioHandlerName=",
        "-QuickTime:Encoder=",

        # ── 换脸：写入苹果官方录制器身份 ──────────
        "-QuickTime:HandlerName=Core Media Video",
        "-QuickTime:VideoHandlerName=Core Media Video",
        "-QuickTime:AudioHandlerName=Core Media Audio",

        # ── 机型：四命名空间全覆盖 ─────────────────
        # 1. QuickTime Keys（iOS 相册首选）
        f"-QuickTime:Make={make}",
        f"-QuickTime:Model={model}",
        # 2. Keys 命名空间（iOS 18 新路径）
        f"-Keys:Make={make}",
        f"-Keys:Model={model}",
        # 3. UserData（传统路径）
        f"-UserData:Make={make}",
        f"-UserData:Model={model}",
        # 4. ItemList / com.apple.quicktime.*（旧式兜底）
        f"-com.apple.quicktime.make={make}",
        f"-com.apple.quicktime.model={model}",

        # ── 时间戳：iOS 相册时间轴权威字段 ─────────
        f"-QuickTime:CreationDate={date}",
        f"-com.apple.quicktime.creationdate={date}",
        f"-CreateDate={date}",
        f"-DateTimeOriginal={date}",
        f"-TrackCreateDate={date}",
        f"-MediaCreateDate={date}",

        filepath,
    ]

    log.info("[ExifTool] 注入 %d 个标签…", len(cmd) - 3)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if r.returncode != 0:
        log.error("[ExifTool] 失败：%s", r.stderr[-300:])
        raise RuntimeError(f"ExifTool 注入失败：{r.stderr[-200:]}")

    log.info("[ExifTool] 完成：%s", r.stdout.strip())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.route("/api/process-video", methods=["POST"])
def process_video():
    """
    POST /api/process-video

    必填 form-data
      file    视频文件（mp4 / mov）
      make    厂商，如 Apple
      model   机型，如 iPhone 17 Pro Max
      date    时间，如 2026:02:22 12:00:00+08:00

    成功  → video/quicktime 附件，文件名 processed_{uuid}.mov
    失败  → {"error": "…"}  +  4xx / 5xx
    """

    # ── 1. 校验文件 ──────────────────────────────
    if "file" not in request.files:
        return jsonify({"error": "缺少 file 字段"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "未选择文件"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "仅支持 mp4 / mov 格式"}), 400

    # ── 2. 校验参数 ──────────────────────────────
    make  = request.form.get("make",  "").strip()
    model = request.form.get("model", "").strip()
    date  = request.form.get("date",  "").strip()

    missing = [k for k, v in {"make": make, "model": model, "date": date}.items() if not v]
    if missing:
        return jsonify({"error": f"缺少必填参数：{', '.join(missing)}"}), 400

    # ── 3. 保存上传文件 ──────────────────────────
    uid     = uuid.uuid4().hex
    src_ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    src     = str(UPLOAD_DIR / f"src_{uid}.{src_ext}")
    out     = str(UPLOAD_DIR / f"out_{uid}.mov")

    try:
        file.save(src)
        log.info("已保存：%s（%.1f MB）",
                 src, os.path.getsize(src) / 1024 / 1024)
    except OSError as e:
        return jsonify({"error": f"文件保存失败：{e}"}), 500

    # ── 4. FFmpeg 重封装 ─────────────────────────
    try:
        remux_to_mov(src, out)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "FFmpeg 处理超时（>5 分钟）"}), 500
    finally:
        schedule_delete(src, delay=0)   # 源文件立即释放

    # ── 5. ExifTool 元数据注入 ────────────────────
    try:
        inject_metadata(out, make, model, date)
    except RuntimeError as e:
        schedule_delete(out, delay=0)
        return jsonify({"error": str(e)}), 500
    except subprocess.TimeoutExpired:
        schedule_delete(out, delay=0)
        return jsonify({"error": "ExifTool 处理超时"}), 500

    # ── 6. 300s 延迟清理 ─────────────────────────
    @after_this_request
    def _cleanup(response):
        schedule_delete(out, delay=CLEANUP_DELAY_SEC)
        return response

    # ── 7. 返回 ──────────────────────────────────
    return send_file(
        out,
        mimetype="video/quicktime",
        as_attachment=True,
        download_name=f"processed_{uid}.mov",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 全局错误处理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.errorhandler(413)
def err_too_large(_):
    return jsonify({"error": "文件超过 4 GB 限制"}), 413

@app.errorhandler(404)
def err_not_found(_):
    return jsonify({"error": "接口不存在"}), 404

@app.errorhandler(500)
def err_server(_):
    return jsonify({"error": "服务器内部错误"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
