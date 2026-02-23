# 项目简介：
针对iOS设备显示图片、视频这种媒体时识别的参数进行修改。通过底层重构 EXIF 和 QuickTime 标签，支持将普通媒体文件伪装成 iOS 旗舰设备拍摄的原片效果，并尝试通过“元数据契约”逻辑实现实况照片（Live Photo）的合体。

# 项目能力：
全参数指纹伪装：支持将任意图片/视频伪装成指定旗舰机型（如 iPhone 17 Pro Max），同步修改 Make、Model、Lens 以及 ISO、Aperture 等拍摄参数。
43 标签深度注入：针对实况照片（Live Photo）合体，实现了视频侧 26 个标签与图片侧 17 个标签的全空间覆盖，包含关键的 StillImageTime 锚点和 CustomRendered 标记。
指纹净化：强制清除 FFmpeg 编码器痕迹，重构媒体处理器（Handler）名称，让文件在 iOS 索引系统眼里“血统纯正”。
并发：采用 Gunicorn + Flask 架构，配合 Nginx 反代处理 4GB 级别的大文件上传，内置 300s 临时文件清理线程

# 测试环境：
操作系统：Debian 12.13 (Stable) + Windows10测试
运行环境：Python 3.11 + Gunicorn 25.1.0
媒体引擎：ExifTool 12.76+ / FFmpeg 6.0+
前端网关：Nginx (已调优 client_max_body_size 与反代缓冲)

# 注意事项：
此项目图片处理依靠前端js处理，不消耗服务器算力，视频处理部分需要配置好后端接口，由服务器进行处理然后前端返回，
实况照片局限性：目前实况照片（Live Photo）合成部分仅能实现合体，无法正常处理其机型参数伪装（受 iOS 内部校验逻辑限制）；普通图片与视频的参数伪装功能正常。
