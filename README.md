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

# 部署方式：
## 项目需要准备Cloudflare账号、任意地域服务器（配置推荐2C2G）、任意ssh、ftp工具
## 1、前端环境准备：
登录cloudflare控制台-左上角搜索“pages”-进入后点击“创建应用程序”-点击“想要部署 Pages？开始使用”，根据自己的状况选择Git或拖放文件-起完名字后开始部署后端
## 2、后端环境准备
确保系统依赖包都是最新的，然后执行以下命令更新并安装 ExifTool 与 FFmpeg
sudo apt update && sudo apt install exiftool ffmpeg python3-pip -y
## 3、后端服务部署(实况部分举例）
## 进入目录并安装 Python 依赖
cd home/live
pip install -r requirements.txt
## 使用 Gunicorn 启动服务 (监听端口)
## -w 4 表示开启 4 个工作进程，确保并发处理能力
gunicorn -w 4 -b 0.0.0.0:5001 dt_app:app
## 4、 Nginx 反向代理配置
我这里使用宝塔面板的“反向代理”板块进行配置，域名填写“sp.8866520.xyz”，目标这一栏在Http://后填上127.0.0.1:5000，然后点击确定，配置SSL证书，接着配置下一个“dt.8866520.xyz”，目标127.0.0.1：5001，同样配置SSL
## 5、后端接口配置
我这里域名托管在了阿里云ESA边缘安全加速，创建一个新的DNS解析，代理加速不要开，源站地址填你的服务器ip
## 6、测试项目
访问cloudflare给的xxx.pages.dev进行测试
## 7、服务持久化 (Systemctl）
创建服务文件
使用 root 权限创建 `/etc/systemd/system/dt.service`：
[Unit]
Description=iOS Media Metadata Forge Service
After=network.target

[Service]
User=root
Group=www-data
# 这里的路径一定要改成你服务器上真实的 backend 目录
WorkingDirectory=/home/live/backend
ExecStart=/usr/local/bin/gunicorn -w 4 -b 0.0.0.0:5001 dt_app:app
Restart=always

[Install]
WantedBy=multi-user.target

# 部署注意事项
项目内代码的域名、接口等信息需替换为自己的，否则后端项目失效
