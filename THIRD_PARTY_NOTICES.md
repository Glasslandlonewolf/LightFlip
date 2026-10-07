# 第三方组件说明

轻转源码使用 AGPL-3.0-or-later。以下第三方项目继续适用各自的许可证，本文不替代组件随附的许可证全文。

| 组件 | 用途 | 项目与许可 |
| --- | --- | --- |
| Python | 主程序与 OCR 运行环境 | [Python](https://www.python.org/)，PSF；运行环境保留 `LICENSE.txt` |
| Pillow | 图像处理 | [Pillow](https://github.com/python-pillow/Pillow)，MIT-CMU |
| TkinterDnD2 / tkdnd | 拖放 | [TkinterDnD2](https://github.com/Eliav2/tkinterdnd2)，保留包内许可及 tkdnd 许可 |
| pystray | 托盘 | [pystray](https://github.com/moses-palmer/pystray)，LGPL-3.0；包内包含 Python 源码 |
| pywin32 | Windows / Office 集成 | [pywin32](https://github.com/mhammond/pywin32)，保留包内许可 |
| imageio-ffmpeg | FFmpeg 调用和可执行文件定位 | [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)，BSD-2-Clause；FFmpeg 二进制另适用自身许可 |
| FFmpeg 7.1 essentials（Gyan） | 独立进程执行音视频转换 | [FFmpeg](https://ffmpeg.org/) / [Gyan builds](https://www.gyan.dev/ffmpeg/builds/)，当前包使用含 GPL 编码器的构建，GPL-3.0-or-later |
| MarkItDown | 文档提取 | [MarkItDown](https://github.com/microsoft/markitdown)，MIT |
| PyMuPDF / MuPDF | PDF 处理和布局 | [PyMuPDF](https://github.com/pymupdf/PyMuPDF) / [MuPDF](https://mupdf.com/)，本项目使用 AGPL 开源版本 |
| pypdfium2 / PDFium | PDF 渲染 | [pypdfium2](https://github.com/pypdfium2-team/pypdfium2)，保留 BSD-3-Clause、Apache-2.0 与 PDFium 第三方许可 |
| python-docx / python-pptx | Office 文件生成 | [python-docx](https://github.com/python-openxml/python-docx) / [python-pptx](https://github.com/scanny/python-pptx)，MIT |
| lxml | XML 操作 | [lxml](https://github.com/lxml/lxml)，保留 BSD 及相关第三方许可 |
| RapidOCR / 模型 | 本地中英文 OCR | [RapidOCR](https://github.com/RapidAI/RapidOCR)，Apache-2.0；保留模型及相关上游声明 |
| ONNX Runtime | OCR 模型推理 | [ONNX Runtime](https://github.com/microsoft/onnxruntime)，MIT，保留第三方声明 |

其余传递依赖的许可保留在相应包或 `*.dist-info` 目录。离线打包工具保留这些目录，不将全部依赖重新许可为轻转的许可证。

## 二进制包的源码与构建信息

- 轻转程序源文件直接随离线 ZIP 提供，并在本仓库公开。
- Python 与各 Python 包的版本、来源和许可应以包内 metadata 为准。
- FFmpeg 是独立进程。发布者应保存随包 FFmpeg 的 `-version` / `-buildconf` / `-L` 输出，并提供与实际二进制一致的 FFmpeg 及 GPL/LGPL 依赖的对应源码和必要构建信息。仅链接一个不同版本的源码或许可摘要不能替代这些材料。
- 上游源码入口：<https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz>、<https://www.gyan.dev/ffmpeg/builds/>。这些链接用于查找对应材料；不声称单个 FFmpeg 源码压缩包涵盖全部编码器与构建依赖。
- 打包工具只组装给定环境，不从源码重建所有第三方二进制。公开分发完整离线包前，需核对这些组件的分发材料是否齐备。

## 交互来源

拖放轮盘的交互思路参考 FileFlip。轻转是独立的 Windows 实现，不使用其官方身份，不宣称与 FileFlip / FileFlipper 有官方关联。
