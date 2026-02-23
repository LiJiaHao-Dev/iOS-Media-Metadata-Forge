"""
实况照片元数据后端 —— dt 独立服务
架构：Flask + Gunicorn
端口：5001（与 sp 服务 5000 端口物理隔离）
职责：接收图片 + 视频，注入相同 ContentIdentifier，返回 ZIP 包

注入策略（地毯式覆盖，兼容全版本 iOS）：
  视频：FFmpeg (-c copy 重封装) → ExifTool 单次调用写入：
        Make/Model/Date
        Keys:ContentIdentifier          ← 现代路径（iOS 15+）
        com.apple.quicktime.content.identifier  ← 旧版兼容路径
        ContentIdentifier               ← 顶层通用字段
        Keys:StillImageTime=0           ← 静止帧锚点，部分视频源必需
  图片：ExifTool 单次调用写入：
        Make/Model/Date + 拍摄参数
        Apple:ContentIdentifier         ← MakerNote 主字段
        XMP-apple-fi:ContentIdentifier  ← XMP apple-fi 冗余备份
        XMP:ContentIdentifier           ← 通用 XMP 空间兜底
        CustomRendered=6                ← iOS 实况渲染标记

  所有注入均在单次 exiftool 调用中完成，避免多次 IO 损坏文件。
  打包：zipfile 将处理完的 IMG_LIVE.JPG + IMG_LIVE.MOV 打入同一 ZIP 返回

环境：Debian 12 + Python 3.11+ + ffmpeg + exiftool
"""

import os
import uuid
import shutil
import zipfile
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
BASE_DIR          = Path(__file__).parent
UPLOAD_DIR        = BASE_DIR / "uploads_dt"   # 与 sp 服务目录完全隔离
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_VIDEO_EXT = {"mp4", "mov"}
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "heic", "heif", "webp"}
MAX_UPLOAD_BYTES  = 4 * 1024 * 1024 * 1024    # 4 GB
CLEANUP_DELAY_SEC = 300                        # 临时文件保留 300 秒后自动删除

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Flask 初始化
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
def allowed_video(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_VIDEO_EXT


def allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


def schedule_delete(*paths: str, delay: float = CLEANUP_DELAY_SEC) -> None:
    """
    后台守护线程：delay 秒后静默删除所有指定路径的临时文件。
    daemon=True 确保主进程退出时线程不会阻塞。
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
# 步骤 A：FFmpeg 极速重封装（视频 → MOV）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def remux_to_mov(src: str, out: str) -> None:
    """
    将视频原样重封装进 MOV 容器，不做任何重编码。

    -c copy                   所有流原样复制，零质量损失
    -map 0                    保留全部流（视频+音频）
    -ignore_unknown           遇到私有流静默跳过
    -movflags +faststart      moov 盒子前置，iOS 打开更流畅
              +use_metadata_tags  允许写入苹果私有 Keys 盒子，
                                  为 ExifTool 写入 ContentIdentifier 铺垫
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
    log.info("[FFmpeg] 完成 → %s（%.1f MB）", out, os.path.getsize(out) / 1024 / 1024)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 步骤 B：ExifTool — 视频元数据注入（地毯式）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def inject_video_metadata(filepath: str, make: str, model: str,
                           date: str, asset_id: str) -> None:
    """
    视频侧实况配对标识：四路径全覆盖 + 静止帧锚点。
    所有标签在单次 exiftool 调用中完成写入，避免多次 IO 损坏文件。

    配对锚点写入策略：
      ① ContentIdentifier（顶层通用）
            写入文件顶层，部分第三方播放器和 iOS 系统组件会优先读此字段。
      ② Keys:ContentIdentifier（moov/meta/keys，iOS 15+ 首选）
            苹果官方现代路径，iOS 15 以上版本的相册主要读取位置。
      ③ com.apple.quicktime.content.identifier（moov/udta UserData）
            旧版 iOS 和部分第三方工具的兼容读取路径。
      ④ Keys:StillImageTime=0（静止帧锚点）
            标记视频的第 0 帧为实况照片的静止展示帧。
            部分 MOV 源文件缺少此字段时，iOS 相册无法正确合体，
            写入后可解决"视频单独存在但不触发实况"的问题。
    """
    cmd = [
        "exiftool",
        "-overwrite_original",
        "-P",

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
        f"-QuickTime:Make={make}",
        f"-QuickTime:Model={model}",
        f"-Keys:Make={make}",
        f"-Keys:Model={model}",
        f"-UserData:Make={make}",
        f"-UserData:Model={model}",
        f"-com.apple.quicktime.make={make}",
        f"-com.apple.quicktime.model={model}",

        # ── 时间戳 ─────────────────────────────────
        f"-QuickTime:CreationDate={date}",
        f"-com.apple.quicktime.creationdate={date}",
        f"-CreateDate={date}",
        f"-DateTimeOriginal={date}",
        f"-TrackCreateDate={date}",
        f"-MediaCreateDate={date}",

        # ── 实况照片配对锚点：四路径全覆盖 ─────────
        # ① 顶层通用字段（新增）
        f"-ContentIdentifier={asset_id}",
        # ② Keys 盒子，iOS 15+ 首选现代路径
        f"-Keys:ContentIdentifier={asset_id}",
        # ③ QuickTime UserData 显式路径，旧版 iOS 兼容
        f"-com.apple.quicktime.content.identifier={asset_id}",
        # ④ 静止帧锚点：标记第 0 帧为实况静止展示帧（新增）
        "-Keys:StillImageTime=0",

        filepath,
    ]
    log.info("[ExifTool-Video] 注入 %d 个标签，asset_id=%s", len(cmd) - 3, asset_id)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        log.error("[ExifTool-Video] 失败：%s", r.stderr[-300:])
        raise RuntimeError(f"ExifTool 视频注入失败：{r.stderr[-200:]}")
    log.info("[ExifTool-Video] 完成：%s", r.stdout.strip())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 步骤 C：ExifTool — 图片元数据注入（地毯式）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def inject_image_metadata(filepath: str, make: str, model: str,
                           date: str, asset_id: str,
                           aperture: str, focal: str, focal35: str,
                           iso: str, lens: str,
                           width: str, height: str) -> None:
    """
    图片侧实况配对标识：三命名空间全覆盖 + 实况渲染标记。
    所有标签在单次 exiftool 调用中完成写入，避免多次 IO 损坏文件。

    为何不在前端用 piexif.js 处理？
      piexif.js 只能操作标准 EXIF IFD（0th / Exif / GPS）。
      Apple:ContentIdentifier 存储在苹果私有 MakerNote 二进制结构内，
      XMP 字段存储在 XMP 元数据块内，piexif.js 均无法构造。
      exiftool 是唯一跨平台可靠写入途径。

    配对锚点写入策略：
      ① Apple:ContentIdentifier（MakerNote）
            iOS 相册最优先读取的字段，存于苹果私有 MakerNote 区块。
      ② XMP-apple-fi:ContentIdentifier（XMP apple-fi 命名空间）
            冗余备份，兼容图片经第三方工具转存后 MakerNote 被剥离的场景。
      ③ XMP:ContentIdentifier（通用 XMP 空间，新增）
            兜底字段，部分 iOS 系统组件和第三方工具优先扫描 XMP 区块，
            确保在任何处理流程后配对信息不丢失。

    实况渲染标记：
      ④ CustomRendered=6
            EXIF CustomRendered 字段值 6 是苹果为实况照片定义的专属标记。
            iOS 相册读取此字段辅助判断文件是否应激活实况动画渲染，
            缺失时部分 iOS 版本不会触发合体逻辑。
    """
    cmd = [
        "exiftool",
        "-overwrite_original",
        "-P",

        # ── 机型与时间 ─────────────────────────────
        f"-Make={make}",
        f"-Model={model}",
        f"-DateTime={date}",
        f"-DateTimeOriginal={date}",
        f"-CreateDate={date}",

        # ── 拍摄参数 ───────────────────────────────
        f"-LensModel={lens}",
        f"-FNumber={aperture}",
        f"-FocalLength={focal}",
        f"-FocalLengthIn35mmFormat={focal35}",
        f"-ISO={iso}",
        f"-ExifImageWidth={width}",
        f"-ExifImageHeight={height}",

        # ── 实况渲染标记（新增）────────────────────
        # EXIF CustomRendered=6 是苹果为 Live Photo 定义的专属值，
        # iOS 相册依此辅助判断是否激活实况动画渲染逻辑。
        "-CustomRendered=6",

        # ── 实况照片配对锚点：三命名空间全覆盖 ──────
        # ① Apple MakerNote（iOS 相册最优先读取字段）
        f"-Apple:ContentIdentifier={asset_id}",
        # ② XMP apple-fi 命名空间（MakerNote 冗余备份）
        f"-XMP-apple-fi:ContentIdentifier={asset_id}",
        # ③ 通用 XMP 空间兜底（新增）
        f"-XMP:ContentIdentifier={asset_id}",

        filepath,
    ]
    log.info("[ExifTool-Image] 注入 %d 个标签，asset_id=%s", len(cmd) - 3, asset_id)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        log.error("[ExifTool-Image] 失败：%s", r.stderr[-300:])
        raise RuntimeError(f"ExifTool 图片注入失败：{r.stderr[-200:]}")
    log.info("[ExifTool-Image] 完成：%s", r.stdout.strip())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主接口：/api/process-live
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.route("/api/process-live", methods=["POST"])
def process_live():
    """
    POST /api/process-live

    必填 form-data
      photo     图片文件（jpg / jpeg / png / heic / heif / webp）
      video     视频文件（mp4 / mov）
      make      厂商，如 Apple
      model     机型，如 iPhone 17 Pro Max
      date      时间，如 2026:02:22 12:00:00
      asset_id  前端生成的 UUID（接收后自动 strip + upper）

    可选 form-data（图片 EXIF 参数，不传则使用默认值）
      aperture  光圈值，默认 1.78
      focal     焦距 mm，默认 24
      focal35   35mm 等效焦距，默认 24
      iso       ISO 感光度，默认 100
      lens      镜头描述字符串
      width     像素宽度，默认 4032
      height    像素高度，默认 3024

    成功  → application/zip 附件，内含 IMG_LIVE.JPG + IMG_LIVE.MOV
    失败  → {"error": "…"}  +  4xx / 5xx
    """

    # ── 1. 校验文件字段 ──────────────────────────
    if "photo" not in request.files or "video" not in request.files:
        return jsonify({"error": "需要同时上传 photo 和 video 字段"}), 400

    photo_file = request.files["photo"]
    video_file = request.files["video"]

    if not photo_file.filename or not video_file.filename:
        return jsonify({"error": "文件名不能为空"}), 400
    if not allowed_image(photo_file.filename):
        return jsonify({"error": "图片仅支持 jpg/jpeg/png/heic/heif/webp"}), 400
    if not allowed_video(video_file.filename):
        return jsonify({"error": "视频仅支持 mp4/mov"}), 400

    # ── 2. 读取并校验必填参数 ────────────────────
    make  = request.form.get("make",  "").strip()
    model = request.form.get("model", "").strip()
    date  = request.form.get("date",  "").strip()

    # ★ asset_id 强制 strip().upper()，与苹果原生 UUID 全大写格式严格一致
    asset_id = request.form.get("asset_id", "").strip().upper()

    missing = [k for k, v in {
        "make": make, "model": model,
        "date": date, "asset_id": asset_id,
    }.items() if not v]
    if missing:
        return jsonify({"error": f"缺少必填参数：{', '.join(missing)}"}), 400

    log.info("process-live | make=%s  model=%s  asset_id=%s", make, model, asset_id)

    # 可选图片 EXIF 参数（带安全默认值）
    aperture = request.form.get("aperture", "1.78").strip()
    focal    = request.form.get("focal",    "24").strip()
    focal35  = request.form.get("focal35",  "24").strip()
    iso      = request.form.get("iso",      "100").strip()
    lens     = request.form.get("lens",     f"{model} 后置摄像头").strip()
    width    = request.form.get("width",    "4032").strip()
    height   = request.form.get("height",   "3024").strip()

    # ── 3. 生成本次请求的工作路径 ────────────────
    uid = uuid.uuid4().hex

    photo_ext = secure_filename(photo_file.filename).rsplit(".", 1)[1].lower()
    video_ext = secure_filename(video_file.filename).rsplit(".", 1)[1].lower()

    src_photo = str(UPLOAD_DIR / f"src_photo_{uid}.{photo_ext}")
    src_video = str(UPLOAD_DIR / f"src_video_{uid}.{video_ext}")
    out_photo = str(UPLOAD_DIR / f"out_photo_{uid}.jpg")
    out_video = str(UPLOAD_DIR / f"out_video_{uid}.mov")
    out_zip   = str(UPLOAD_DIR / f"live_{uid}.zip")

    tmp_files = [src_photo, src_video, out_photo, out_video, out_zip]

    def cleanup_all(delay=0):
        schedule_delete(*[f for f in tmp_files if os.path.exists(f)], delay=delay)

    # ── 4. 保存上传文件 ──────────────────────────
    try:
        photo_file.save(src_photo)
        video_file.save(src_video)
        log.info("已保存：photo=%.2f MB  video=%.2f MB",
                 os.path.getsize(src_photo) / 1024 / 1024,
                 os.path.getsize(src_video) / 1024 / 1024)
    except OSError as e:
        cleanup_all(delay=0)
        return jsonify({"error": f"文件保存失败：{e}"}), 500

    # ── 5. 图片预处理：非 JPEG 先用 FFmpeg 转换 ──
    current_photo = src_photo
    try:
        if photo_ext not in {"jpg", "jpeg"}:
            converted = str(UPLOAD_DIR / f"conv_photo_{uid}.jpg")
            tmp_files.append(converted)
            conv_cmd = ["ffmpeg", "-y", "-i", src_photo, "-q:v", "1", converted]
            r = subprocess.run(conv_cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                raise RuntimeError(f"图片格式转换失败：{r.stderr[-200:]}")
            schedule_delete(src_photo, delay=0)
            current_photo = converted

        shutil.copy2(current_photo, out_photo)
    except RuntimeError as e:
        cleanup_all(delay=0)
        return jsonify({"error": str(e)}), 500
    finally:
        if current_photo != out_photo and os.path.exists(current_photo):
            schedule_delete(current_photo, delay=0)

    # ── 6. 视频重封装（FFmpeg）───────────────────
    try:
        remux_to_mov(src_video, out_video)
    except RuntimeError as e:
        cleanup_all(delay=0)
        return jsonify({"error": str(e)}), 500
    except subprocess.TimeoutExpired:
        cleanup_all(delay=0)
        return jsonify({"error": "FFmpeg 处理超时（>5 分钟）"}), 500
    finally:
        schedule_delete(src_video, delay=0)

    # ── 7. 图片元数据注入（ExifTool，单次调用）───
    try:
        inject_image_metadata(
            out_photo, make, model, date, asset_id,
            aperture, focal, focal35, iso, lens, width, height,
        )
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        cleanup_all(delay=0)
        return jsonify({"error": f"图片处理失败：{e}"}), 500

    # ── 8. 视频元数据注入（ExifTool，单次调用）───
    try:
        inject_video_metadata(out_video, make, model, date, asset_id)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        cleanup_all(delay=0)
        return jsonify({"error": f"视频处理失败：{e}"}), 500

    # ── 9. 打包 ZIP ───────────────────────────────
    # ★ 文件名严格固定为 IMG_LIVE.JPG / IMG_LIVE.MOV
    try:
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_STORED) as zf:
            zf.write(out_photo, arcname="IMG_LIVE.JPG")
            zf.write(out_video, arcname="IMG_LIVE.MOV")
        log.info("ZIP 打包完成：%s（%.2f MB）",
                 out_zip, os.path.getsize(out_zip) / 1024 / 1024)
    except OSError as e:
        cleanup_all(delay=0)
        return jsonify({"error": f"ZIP 打包失败：{e}"}), 500

    # ── 10. 延迟清理策略（300s）─────────────────
    @after_this_request
    def _cleanup(response):
        schedule_delete(out_photo, out_video, delay=0)    # 中间产物立即释放
        schedule_delete(out_zip, delay=CLEANUP_DELAY_SEC) # ZIP 保留 300s
        return response

    # ── 11. 返回 ZIP ─────────────────────────────
    return send_file(
        out_zip,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"LivePhoto_{uid[:8]}.zip",
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
    # 独立运行在 5001 端口，不占用 sp 服务的 5000 端口
    app.run(host="0.0.0.0", port=5001, debug=False)
