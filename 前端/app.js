document.addEventListener('DOMContentLoaded', () => {

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 1. 状态变量
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    let base64Image   = null;   // 照片模式：canvas 转出的 JPEG base64
    let rawVideoFile  = null;   // 视频模式：原始 File 对象
    let livePhotoFile = null;   // 实况模式：图片 File 对象
    let liveVideoFile = null;   // 实况模式：视频 File 对象
    let currentMode   = 'photo';

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 2. 常用 DOM 引用
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const tabPhoto      = document.getElementById('tabPhoto');
    const tabLive       = document.getElementById('tabLive');
    const tabVideo      = document.getElementById('tabVideo');
    const uploadTitle   = document.getElementById('uploadTitle');
    const uploadSub     = document.getElementById('uploadSub');
    const fileInput     = document.getElementById('fileInput');
    const livePhotoInput = document.getElementById('livePhotoInput');
    const liveVideoInput = document.getElementById('liveVideoInput');
    const widthInput    = document.getElementById('editWidth');

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 3. 初始化时间（本地时区）
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('editTime').value = now.toISOString().slice(0, 16);

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 4. 设备预设网格（iPhone XR → 17 全系列）
    //    三种模式均共享此网格
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const iphones = [
        // ── iPhone 17 系列 ──────────────────────
        { model: 'iPhone 17 Pro Max',  aperture: 1.78, focal: 24 },
        { model: 'iPhone 17 Pro',      aperture: 1.78, focal: 24 },
        { model: 'iPhone 17 Plus',     aperture: 1.78, focal: 26 },
        { model: 'iPhone 17',          aperture: 1.78, focal: 26 },
        // ── iPhone 16 系列 ──────────────────────
        { model: 'iPhone 16 Pro Max',  aperture: 1.78, focal: 24 },
        { model: 'iPhone 16 Pro',      aperture: 1.78, focal: 24 },
        { model: 'iPhone 16 Plus',     aperture: 1.78, focal: 26 },
        { model: 'iPhone 16',          aperture: 1.78, focal: 26 },
        // ── iPhone 15 系列 ──────────────────────
        { model: 'iPhone 15 Pro Max',  aperture: 1.78, focal: 24 },
        { model: 'iPhone 15 Pro',      aperture: 1.78, focal: 24 },
        { model: 'iPhone 15 Plus',     aperture: 1.78, focal: 26 },
        { model: 'iPhone 15',          aperture: 1.78, focal: 26 },
        // ── iPhone 14 系列 ──────────────────────
        { model: 'iPhone 14 Pro Max',  aperture: 1.78, focal: 24 },
        { model: 'iPhone 14 Pro',      aperture: 1.78, focal: 24 },
        { model: 'iPhone 14 Plus',     aperture: 1.90, focal: 26 },
        { model: 'iPhone 14',          aperture: 1.90, focal: 26 },
        // ── iPhone 13 系列 ──────────────────────
        { model: 'iPhone 13 Pro Max',  aperture: 1.50, focal: 26 },
        { model: 'iPhone 13 Pro',      aperture: 1.50, focal: 26 },
        { model: 'iPhone 13',          aperture: 1.60, focal: 26 },
        { model: 'iPhone 13 mini',     aperture: 1.60, focal: 26 },
        // ── iPhone 12 系列 ──────────────────────
        { model: 'iPhone 12 Pro Max',  aperture: 1.60, focal: 26 },
        { model: 'iPhone 12 Pro',      aperture: 2.00, focal: 26 },
        { model: 'iPhone 12',          aperture: 1.60, focal: 26 },
        { model: 'iPhone 12 mini',     aperture: 1.60, focal: 26 },
        // ── iPhone 11 系列 ──────────────────────
        { model: 'iPhone 11 Pro Max',  aperture: 2.00, focal: 26 },
        { model: 'iPhone 11 Pro',      aperture: 2.00, focal: 26 },
        { model: 'iPhone 11',          aperture: 1.80, focal: 26 },
        // ── iPhone XS / XR 系列 ─────────────────
        { model: 'iPhone XS Max',      aperture: 1.80, focal: 26 },
        { model: 'iPhone XS',          aperture: 1.80, focal: 26 },
        { model: 'iPhone XR',          aperture: 1.80, focal: 26 },
    ];

    const deviceGrid = document.getElementById('deviceGrid');
    iphones.forEach((device, index) => {
        const btn = document.createElement('button');
        btn.className = `btn-grid ${index === 0 ? 'active' : ''}`;
        btn.innerText = device.model;
        btn.onclick = () => {
            document.querySelectorAll('#deviceGrid .btn-grid').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('editModel').value    = device.model;
            document.getElementById('editAperture').value = device.aperture;
            document.getElementById('editFocal').value    = device.focal;
            updateLensString();
        };
        deviceGrid.appendChild(btn);
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 5. 面板折叠逻辑
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    document.querySelectorAll('.accordion-header').forEach(header => {
        header.addEventListener('click', () => {
            const targetId = header.getAttribute('data-target');
            document.getElementById(targetId).classList.toggle('active');
        });
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 6. 三模式切换
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const CLS_ACTIVE   = "flex-1 py-2.5 text-xs font-bold rounded-lg bg-pink-50 text-pink-500 transition-all";
    const CLS_INACTIVE = "flex-1 py-2.5 text-xs font-bold rounded-lg text-gray-400 transition-all";

    function resetAllUploadUI() {
        // 重置所有状态
        base64Image   = null;
        rawVideoFile  = null;
        livePhotoFile = null;
        liveVideoFile = null;
        fileInput.value        = '';
        livePhotoInput.value   = '';
        liveVideoInput.value   = '';

        // 重置实况缩略图
        const tImg = document.getElementById('liveThumbnailImg');
        const tVid = document.getElementById('liveThumbnailVid');
        tImg.classList.add('hidden');
        tVid.classList.add('hidden');
        document.getElementById('livePlaceholderImg').classList.remove('hidden');
        document.getElementById('livePlaceholderVid').classList.remove('hidden');
        document.getElementById('liveAssetIdDisplay').innerText = '导出时自动生成';
        document.getElementById('liveSelectedLabel').innerText  = '等待选择文件…';

        // 隐藏所有上传区
        document.getElementById('uploadArea').classList.add('hidden');
        document.getElementById('selectedArea').classList.add('hidden');
        document.getElementById('liveUploadArea').classList.add('hidden');
        document.getElementById('liveSelectedArea').classList.add('hidden');
    }

    function switchMode(mode) {
        currentMode = mode;
        resetAllUploadUI();

        // 更新标签样式
        tabPhoto.className = CLS_INACTIVE;
        tabLive.className  = CLS_INACTIVE;
        tabVideo.className = CLS_INACTIVE;

        if (mode === 'photo') {
            tabPhoto.className = CLS_ACTIVE;
            uploadTitle.innerText = "点击上传图片或截屏";
            uploadSub.innerText   = "支持 JPG / PNG 等所有格式，强制原图重组";
            fileInput.accept      = "image/*";
            document.getElementById('uploadArea').classList.remove('hidden');

        } else if (mode === 'live') {
            tabLive.className = CLS_ACTIVE;
            document.getElementById('liveUploadArea').classList.remove('hidden');
            document.getElementById('liveSelectedArea').classList.remove('hidden');
            updateLiveSelectedLabel();

        } else { // video
            tabVideo.className = CLS_ACTIVE;
            uploadTitle.innerText = "点击上传原相机视频";
            uploadSub.innerText   = "支持 MP4 / MOV 格式，将交由云端服务器处理";
            fileInput.accept      = "video/mp4,video/quicktime,video/x-m4v";
            document.getElementById('uploadArea').classList.remove('hidden');
        }
    }

    tabPhoto.onclick = () => switchMode('photo');
    tabLive.onclick  = () => switchMode('live');
    tabVideo.onclick = () => switchMode('video');

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 7. 照片 / 视频模式：文件读取
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    document.getElementById('uploadArea').onclick = () => fileInput.click();
    document.getElementById('reselectBtn').onclick = () => fileInput.click();
    document.getElementById('clearBtn').onclick = () => location.reload();

    fileInput.addEventListener('change', function (e) {
        const file = e.target.files[0];
        if (!file) return;
        const realThumbnail = document.getElementById('realThumbnail');

        if (currentMode === 'video') {
            rawVideoFile = file;
            realThumbnail.src = "https://img.icons8.com/ios-filled/100/ffb6c1/video-file.png";
            document.getElementById('uploadArea').classList.add('hidden');
            document.getElementById('selectedArea').classList.remove('hidden');
        } else {
            // 照片模式：用 canvas 合并白底，消除透明通道
            const reader = new FileReader();
            reader.onload = function (event) {
                const img = new Image();
                img.onload = function () {
                    const canvas = document.createElement('canvas');
                    canvas.width  = img.width;
                    canvas.height = img.height;
                    const ctx = canvas.getContext('2d');
                    ctx.fillStyle = '#FFFFFF';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    ctx.drawImage(img, 0, 0);
                    base64Image = canvas.toDataURL('image/jpeg', 1.0);
                    realThumbnail.src = base64Image;
                    document.getElementById('uploadArea').classList.add('hidden');
                    document.getElementById('selectedArea').classList.remove('hidden');
                };
                img.src = event.target.result;
            };
            reader.readAsDataURL(file);
        }
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 8. 实况模式：双文件选择
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function updateLiveSelectedLabel() {
        const hasImg = !!livePhotoFile;
        const hasVid = !!liveVideoFile;
        const label  = document.getElementById('liveSelectedLabel');

        if (hasImg && hasVid) {
            label.innerText = '图片 + 视频 均已就绪 ✓';
            label.className = 'font-bold text-sm text-green-600';
        } else if (hasImg) {
            label.innerText = '图片已选，等待视频…';
            label.className = 'font-bold text-sm text-amber-500';
        } else if (hasVid) {
            label.innerText = '视频已选，等待图片…';
            label.className = 'font-bold text-sm text-amber-500';
        } else {
            label.innerText = '等待选择文件…';
            label.className = 'font-bold text-sm text-gray-700';
        }
    }

    // 图片区点击
    document.getElementById('livePhotoZone').onclick = () => livePhotoInput.click();

    livePhotoInput.addEventListener('change', function (e) {
        const file = e.target.files[0];
        if (!file) return;
        livePhotoFile = file;

        // 显示缩略图
        const reader = new FileReader();
        reader.onload = function (ev) {
            const tImg = document.getElementById('liveThumbnailImg');
            tImg.src = ev.target.result;
            tImg.classList.remove('hidden');
            document.getElementById('livePlaceholderImg').classList.add('hidden');
        };
        reader.readAsDataURL(file);

        // 更新图片选择区提示
        const zone = document.getElementById('livePhotoZone');
        zone.querySelector('p.font-bold').innerText = `✓ ${file.name}`;
        zone.querySelector('p.text-\\[10px\\]').innerText = `${(file.size / 1024 / 1024).toFixed(2)} MB`;

        updateLiveSelectedLabel();
    });

    // 视频区点击
    document.getElementById('liveVideoZone').onclick = () => liveVideoInput.click();

    liveVideoInput.addEventListener('change', function (e) {
        const file = e.target.files[0];
        if (!file) return;
        liveVideoFile = file;

        // 视频无法预览缩略图，显示图标
        document.getElementById('liveThumbnailVid').classList.add('hidden');
        document.getElementById('livePlaceholderVid').classList.remove('hidden');
        document.getElementById('livePlaceholderVid').innerText = '🎬';

        // 更新视频选择区提示
        const zone = document.getElementById('liveVideoZone');
        zone.querySelector('p.font-bold').innerText = `✓ ${file.name}`;
        zone.querySelector('p.text-\\[10px\\]').innerText = `${(file.size / 1024 / 1024).toFixed(2)} MB`;

        updateLiveSelectedLabel();
    });

    // 重选按钮：回到双文件选择状态
    document.getElementById('liveReselectBtn').onclick = () => {
        livePhotoFile = null;
        liveVideoFile = null;
        livePhotoInput.value = '';
        liveVideoInput.value = '';

        // 恢复缩略图
        document.getElementById('liveThumbnailImg').classList.add('hidden');
        document.getElementById('liveThumbnailVid').classList.add('hidden');
        document.getElementById('livePlaceholderImg').classList.remove('hidden');
        document.getElementById('livePlaceholderVid').classList.remove('hidden');
        document.getElementById('livePlaceholderImg').innerText = '🖼️';
        document.getElementById('livePlaceholderVid').innerText = '🎞️';
        document.getElementById('liveAssetIdDisplay').innerText = '导出时自动生成';

        // 恢复选择区文案
        const pz = document.getElementById('livePhotoZone');
        pz.querySelector('p.font-bold').innerText    = '① 点击选择实况图片';
        pz.querySelector('p.text-\\[10px\\]').innerText = '支持 JPG / PNG / HEIC';

        const vz = document.getElementById('liveVideoZone');
        vz.querySelector('p.font-bold').innerText    = '② 点击选择实况视频';
        vz.querySelector('p.text-\\[10px\\]').innerText = '支持 MOV / MP4';

        updateLiveSelectedLabel();
    };

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 9. 分辨率选择
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const resButtons = document.querySelectorAll('#resolutionGrid .btn-grid');
    resButtons.forEach(btn => {
        btn.onclick = () => {
            resButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            widthInput.value    = btn.getAttribute('data-w');
            widthInput.dataset.h = btn.getAttribute('data-h');
        };
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 10. 镜头字符串自动生成
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function updateLensString() {
        const model    = document.getElementById('editModel').value;
        const focal    = document.getElementById('editFocal').value;
        const aperture = document.getElementById('editAperture').value;
        document.getElementById('editLens').value = `${model} 后置摄像头 — ${focal}mm f/${aperture}`;
    }
    document.getElementById('editModel').addEventListener('input', updateLensString);
    document.getElementById('editFocal').addEventListener('input', updateLensString);
    document.getElementById('editAperture').addEventListener('input', updateLensString);
    updateLensString();

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 11. UUID v4 生成器（RFC 4122 标准）
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function generateUUID() {
        // 优先使用 crypto.randomUUID（现代浏览器支持）
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        // 降级方案：手动构造 RFC 4122 v4 UUID
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            const r = (Math.random() * 16) | 0;
            return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
        });
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 12. 加载遮罩控制
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function showLoading(title = '正在处理中…', subtitle = '受文件大小影响，请耐心等待勿关闭页面') {
        document.getElementById('loadingTitle').innerText    = title;
        document.getElementById('loadingSubtitle').innerText = subtitle;
        const overlay = document.getElementById('loadingOverlay');
        overlay.classList.remove('hidden');
        overlay.classList.add('flex');
    }

    function hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        overlay.classList.remove('flex');
        overlay.classList.add('hidden');
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 13. 下载 Blob 辅助函数
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function triggerDownload(blob, filename) {
        const url = window.URL.createObjectURL(blob);
        const a   = document.createElement('a');
        a.href     = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 14. 导出总入口
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    document.getElementById('exportBtn').onclick = async () => {

        // ── 校验 ─────────────────────────────────
        if (currentMode === 'photo' && !base64Image) {
            return alert('还没选照片呢！');
        }
        if (currentMode === 'video' && !rawVideoFile) {
            return alert('还没选视频呢！');
        }
        if (currentMode === 'live') {
            if (!livePhotoFile && !liveVideoFile) return alert('请先选择图片和视频！');
            if (!livePhotoFile) return alert('还没选实况图片呢！');
            if (!liveVideoFile) return alert('还没选实况视频呢！');
        }

        // ── 读取公共参数 ─────────────────────────
        const make    = document.getElementById('editMake').value.trim();
        const model   = document.getElementById('editModel').value.trim();
        const dateRaw = document.getElementById('editTime').value;
        // datetime-local 格式转为 ExifTool 接受的 "YYYY:MM:DD HH:MM:SS"
        const dateStr = dateRaw.replace('T', ' ').replace(/-/g, ':') + ':00';

        // ════════════════════════════════════════
        // 模式 A：视频（云端 sp 服务）
        // ════════════════════════════════════════
        if (currentMode === 'video') {
            showLoading('视频正在跨海洗白中…', '受文件大小影响，请耐心等待勿关闭页面');
            try {
                const formData = new FormData();
                formData.append('file',  rawVideoFile);
                formData.append('make',  make);
                formData.append('model', model);
                formData.append('date',  dateStr);

                const response = await fetch('https://sp.8866520.xyz/api/process-video', {
                    method: 'POST',
                    body: formData,
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const blob = await response.blob();
                triggerDownload(blob, `Vid_Edited_${Date.now()}.mov`);
                alert('视频洗白完成！如果 iOS 没有直接弹窗，请到 Safari「下载项」中查看并保存。');
            } catch (err) {
                console.error(err);
                alert('服务器似乎被挤爆了，或者视频太大了，请稍后再试！');
            } finally {
                hideLoading();
            }
            return;
        }

        // ════════════════════════════════════════
        // 模式 B：照片（本地 piexif 处理）
        // ════════════════════════════════════════
        if (currentMode === 'photo') {
            try {
                const fNumber  = parseFloat(document.getElementById('editAperture').value);
                const focal    = parseFloat(document.getElementById('editFocal').value);
                const focal35  = parseInt(document.getElementById('editFocal35').value);
                const iso      = parseInt(document.getElementById('editISO').value);
                const lensStr  = document.getElementById('editLens').value;
                const imgWidth = parseInt(widthInput.value);
                const imgHeight = parseInt(widthInput.dataset.h || Math.round(imgWidth * 0.75));
                const exifDate = dateStr;

                const zeroth = {};
                zeroth[piexif.ImageIFD.Make]     = make;
                zeroth[piexif.ImageIFD.Model]    = model;
                zeroth[piexif.ImageIFD.DateTime] = exifDate;

                const exif = {};
                exif[piexif.ExifIFD.DateTimeOriginal]    = exifDate;
                exif[piexif.ExifIFD.LensModel]           = unescape(encodeURIComponent(lensStr));
                exif[piexif.ExifIFD.FNumber]             = [Math.round(fNumber * 100), 100];
                exif[piexif.ExifIFD.FocalLength]         = [Math.round(focal * 100), 100];
                exif[piexif.ExifIFD.FocalLengthIn35mmFilm] = focal35;
                exif[piexif.ExifIFD.ISOSpeedRatings]     = iso;
                exif[piexif.ExifIFD.PixelXDimension]     = imgWidth;
                exif[piexif.ExifIFD.PixelYDimension]     = imgHeight;

                const exifStr = piexif.dump({ "0th": zeroth, "Exif": exif });
                const result  = piexif.insert(exifStr, base64Image);

                const modal = document.getElementById('resultModal');
                document.getElementById('finalImage').src = result;
                modal.classList.remove('hidden');
                modal.classList.add('flex');
                setTimeout(() => modal.classList.remove('opacity-0'), 10);

                document.getElementById('closeModalBtn').onclick = () => {
                    modal.classList.add('opacity-0');
                    setTimeout(() => {
                        modal.classList.add('hidden');
                        modal.classList.remove('flex');
                    }, 300);
                };
            } catch (e) {
                console.error(e);
                alert('图片处理出错啦，换张图试试！');
            }
            return;
        }

        // ════════════════════════════════════════
        // 模式 C：实况照片（云端 dt 服务）
        // ════════════════════════════════════════
        if (currentMode === 'live') {
            // 1. 生成本次专属 UUID（图片和视频共享同一个）
            const assetId = generateUUID();
            document.getElementById('liveAssetIdDisplay').innerText = assetId;

            showLoading(
                '实况照片生成中…',
                '正在将图片与视频绑定相同 Asset ID，请耐心等待'
            );

            try {
                const aperture = document.getElementById('editAperture').value;
                const focal    = document.getElementById('editFocal').value;
                const focal35  = document.getElementById('editFocal35').value;
                const iso      = document.getElementById('editISO').value;
                const lens     = document.getElementById('editLens').value;
                const width    = widthInput.value;
                const height   = widthInput.dataset.h || String(Math.round(parseInt(width) * 0.75));

                const formData = new FormData();
                formData.append('photo',    livePhotoFile);
                formData.append('video',    liveVideoFile);
                formData.append('make',     make);
                formData.append('model',    model);
                formData.append('date',     dateStr);
                formData.append('asset_id', assetId);
                formData.append('aperture', aperture);
                formData.append('focal',    focal);
                formData.append('focal35',  focal35);
                formData.append('iso',      iso);
                formData.append('lens',     lens);
                formData.append('width',    width);
                formData.append('height',   height);

                const response = await fetch('https://dt.8866520.xyz/api/process-live', {
                    method: 'POST',
                    body: formData,
                });

                if (!response.ok) {
                    // 尝试解析错误信息
                    let errMsg = `HTTP ${response.status}`;
                    try {
                        const errJson = await response.json();
                        errMsg = errJson.error || errMsg;
                    } catch (_) {}
                    throw new Error(errMsg);
                }

                // 2. 下载返回的 ZIP 文件
                const blob = await response.blob();
                triggerDownload(blob, `LivePhoto_${assetId.slice(0, 8)}.zip`);

                alert(
                    '实况照片生成完成！✅\n\n' +
                    '已下载 ZIP 包，内含：\n' +
                    '  • IMG_LIVE.JPG（图片）\n' +
                    '  • IMG_LIVE.MOV（视频）\n\n' +
                    '两个文件的 ContentIdentifier 完全一致，\n' +
                    '将两者一同导入 iOS 相册即可识别为实况照片。'
                );
            } catch (err) {
                console.error(err);
                alert(`实况照片处理失败：${err.message}\n\n请检查网络或稍后再试！`);
            } finally {
                hideLoading();
            }
        }
    };

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 15. 初始状态：进入照片模式
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    switchMode('photo');
});
