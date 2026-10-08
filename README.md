# 轻转 · LightFlip

Windows / macOS 本地文件转换与处理工具，也可以在主窗口拖入文件批量转换。

这是 0.4.0 跨平台测试版。Windows 版支持 Windows 10 / 11 的 64 位 Intel 或 AMD 电脑；Mac 版支持 Apple Silicon 与 Intel。交互参考 FileFlip 的拖放轮盘思路，轻转独立开发，并非 FileFlip 或 FileFlipper 官方产品。

macOS 版提供 Apple Silicon 和 Intel 两种原生打包流程，保留文段与独立图片编辑能力。Mac 上使用 Command＋1 / Command＋2 打开轮盘，关闭窗口退出，Office 渲染使用 LibreOffice；详见 [Mac 使用说明](macos/使用说明.md)。原生构建的自动检查通过后才会生成应用 ZIP。

## 下载与安装

目前已经公开程序源码；完整离线安装包保存在 **Releases 草稿**中，暂未公开下载。补齐随包第三方组件的对应源码及构建材料后，再发布安装包。以下是离线包的安装方法。

1. 将整个 ZIP 解压到普通文件夹。
2. 双击 `安装轻转.cmd`，在窗口中点击“安装轻转”。
3. 以后通过桌面或开始菜单中的“轻转测试版”启动。

也可以双击 `启动轻转.cmd` 直接运行，保留整个解压文件夹即可。离线包已包含 Python、音视频转换组件和 OCR 模型，不需要另装 Python。源码安装与首次准备模型需要联网。

## 功能

- 图片格式互转、图片转 PDF，支持常见图片格式及部分动画转换。
- PDF 按页转图片、拆分、合并与压缩。
- PDF 转 Word / PowerPoint：保留页面外观、重建可编辑布局或提取文字。
- Word、PowerPoint、Excel、PDF、HTML 等转 Markdown / 文本。
- 常见音视频转换、视频压缩、静音、提取音频与截帧。
- 图片裁剪、压缩、缩小、旋转、镜像、黑白、清除 EXIF / GPS 等元数据。
- 图片、扫描 PDF 中英文 OCR，输出带页码的文本或 Markdown。
- 图片 / 扫描 PDF 转 Word、PowerPoint 时自动识别文字，重建可编辑文段（同段多行共用一个文本框）；分离可识别的照片、小图和简单形状，并清理底图中的对应内容。

输出保存在原文件旁边，已有同名文件会自动加序号，原文件不被覆盖。文件转换和 OCR 在本机进行，程序的处理流程不上传所选文件。

## 使用方式与限制

- 拖动文件并按住 **Shift**：打开格式轮盘；松手到格式按钮开始转换，在轮盘中间或外部松手取消。
- 拖动文件并按住 **Shift + Alt**：打开工具轮盘。
- 主窗口支持同类文件批量操作。PDF / 图片合并可以调整顺序。
- 关闭主窗口后仍在托盘运行。在右下角托盘菜单选择“退出”才会完全关闭；程序不自动设置开机启动。
- Word / PowerPoint / Excel 输入转 PDF 或图片需要对应 Microsoft Office；没有安装时相应选项不显示。PDF 转 Word / PowerPoint 的输出本身不要求安装 Office。
- “保留布局并编辑”在图片页上自动启用 OCR，包括带有原生页脚的扫描页；“识别图片文字并编辑（OCR）”可以强制识别每页，包括混合 PDF 中较小的图片文字。两者适用于 Word 和 PowerPoint，也适用于图片输入。
- “提取可编辑文字”、直接转 TXT / Markdown 和“文件工具 → OCR 提取文字”共用识别流程；原生 PDF 文字直接提取，图片页做本地 OCR。只有图片的 Office 文档可在安装对应 Microsoft Office 时先渲染再识别。
- “保留布局并编辑”和“识别图片文字并编辑（OCR）”共用图片分离能力。独立图片可在 Word / PowerPoint 中移动、缩放、裁剪和替换；图片移开后，底图中的原图片会被清理。照片内部的书名、招牌等文字保留在照片中，避免破坏照片。
- 复杂版式、段落边界、字体替换、图形叠加与 OCR 阅读顺序可能有偏差，输出请校对。图片分区和背景恢复依赖可辨认的边界及周围颜色；不能可靠分离的复杂装饰仍保留在背景。照片和图表的像素内容不会变成可编辑的矢量图或数据图表；手写字和低清图片可能漏识别。
- 图片嵌入 Word / PowerPoint、保留页面外观模式中的文字不可单独编辑。
- 自动抠图目前未提供。
- 测试版尚未签名。

## 从源码运行

发布包的主环境是 Python 3.14，OCR 使用独立 Python 3.12 环境。请安装这两个版本的 64 位 Python，在仓库根目录运行：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
py -3.12 -m venv tools-venv
.\tools-venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\tools-venv\Scripts\python.exe tools\cache_ocr_models.py
.\.venv\Scripts\python.exe app.py
```

OCR 模型准备工具初始化 RapidOCR 并将其默认模型缓存到 OCR 环境；首次执行需要联网。主程序会优先使用仓库旁的 `tools-venv`，离线包则使用 `ocr-runtime`。`requirements.txt` 固定主要依赖的已测版本，传递依赖由安装器解析，未承诺字节一致的构建。

## 打包离线版

先按上述步骤准备独立环境和 OCR 模型，再运行：

```powershell
.\.venv\Scripts\python.exe tools\build_offline.py --main-python .venv\Scripts\python.exe --ocr-python tools-venv\Scripts\python.exe
```

打包工具只复制明确列出的轻转程序文件，以及指定 Python 环境中的运行组件；输出到 `dist/`。它不会打包工作目录中的照片、文档、测试素材或 Git 凭据。代码使用命令行参数发现运行环境，没有固定个人电脑路径。

依赖环境应专门为本项目创建，勿将包含私人文件或额外闭源组件的通用环境用于公开打包。发布者应核对包内各第三方许可证，并随二进制分发提供相应组件所要求的源码和构建信息；源码与构建信息的整理方式见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 源码结构

| 文件 | 用途 |
| --- | --- |
| `app.py` / `tool_dialogs.py` | 窗口、拖放轮盘、托盘与操作选项 |
| `core.py` | 格式选择和转换流程 |
| `file_tools.py` | 图片、PDF、视频工具 |
| `office_export.py` / `pdf_layout.py` / `pdf_ocr.py` | Word / PowerPoint 输出、布局重建和共用文字提取 |
| `ocr_layout.py` / `image_layout.py` / `paragraph_layout.py` | OCR 坐标、字体匹配、图片分区、背景修复和通用段落分析 |
| `ai_worker.py` | 独立 OCR 工作进程 |
| `launcher.py` / `offline_installer.py` | 离线包启动与当前用户安装 |
| `tools/` | 模型准备与离线打包 |

## 卸载离线测试版

先从托盘退出，删除当前用户的 `%LOCALAPPDATA%\Programs\LightFlipPreview` 文件夹，以及桌面和开始菜单中的“轻转测试版”快捷方式。勿删除自己的转换结果。

## 反馈与许可证

欢迎在 Issues 提交复现步骤、输入格式、期望结果和实际结果。请用可公开的示例文件，不要上传私人作业、照片或个人资料。

轻转源码采用 **GNU Affero General Public License v3.0 or later（AGPL-3.0-or-later）**，见 [LICENSE](LICENSE)。第三方组件保留各自的许可证，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
