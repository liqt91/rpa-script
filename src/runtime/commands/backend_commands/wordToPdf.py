"""
Word转PDF — wordToPdf (backend)

将 Word(.doc/.docx) 文档转换为 PDF。支持两种引擎：
  - word      : 本机 Microsoft Word 的 COM 接口（Windows，保真度高，需安装 Word）
  - libreoffice: LibreOffice headless 转换（跨平台，需安装 LibreOffice 且 soffice 在 PATH）

转换在后台线程执行，避免阻塞事件循环；输出 PDF 绝对路径写入输出变量。
"""
import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import resolve_vars, clean_var_ref

_WD_FORMAT_PDF = 17  # Word 的 wdFormatPDF 常量


@register_handler(
    cmd="wordToPdf", label="Word转PDF",
    category="文件处理", runtime="backend",
    icon="fa-file-pdf", icon_color="text-red-500", bg_color="bg-red-50",
    category_order=47, command_order=10,
    description="将 Word(.doc/.docx) 文档转换为 PDF 文件，输出路径可写入变量。支持 Word COM / LibreOffice 两种引擎。",
    summary_tpl="{filePath} → PDF")
class WordToPdfHandler:
    params = [
        Param("filePath", "Word文件路径", "string", required=True,
              placeholder="如 C:\\data\\report.docx，支持 {{变量}}"),
        Param("outputDir", "输出目录", "string", placeholder="留空则与输入文件同目录"),
        Param("engine", "转换引擎", "select", default="word",
              options=[{"label": "Word (COM)", "value": "word"},
                       {"label": "LibreOffice", "value": "libreoffice"}]),
        Param("fileName", "输出文件名(不含扩展名)", "string",
              placeholder="留空使用输入文件名", group="advanced"),
        Param("outputVar", "保存PDF路径到变量", "str-var",
              default="pdfPath", group="output",
              description="转换后生成的 PDF 绝对路径存入该变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})

        file_path = resolve_vars(str(extra.get("filePath") or ""), runner.vars).strip()
        if not file_path:
            raise ValueError("wordToPdf: Word 文件路径（filePath）不能为空")
        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"wordToPdf: Word 文件不存在: {file_path}")
        if src.suffix.lower() not in (".doc", ".docx"):
            raise ValueError(f"wordToPdf: 仅支持 .doc/.docx，收到: {src.suffix}")

        output_dir_raw = resolve_vars(str(extra.get("outputDir") or ""), runner.vars).strip()
        output_dir = Path(output_dir_raw) if output_dir_raw else src.parent

        engine = str(extra.get("engine") or "word").lower()
        file_name = str(extra.get("fileName") or "").strip()
        if file_name:
            if file_name.lower().endswith(".pdf"):
                file_name = file_name[:-4]
            out_path = output_dir / f"{file_name}.pdf"
        else:
            out_path = output_dir / f"{src.stem}.pdf"

        output_var = clean_var_ref(str(extra.get("outputVar") or "pdfPath"))

        # 转换是阻塞式长耗时操作，放进后台线程避免阻塞事件循环
        if engine == "word":
            await asyncio.to_thread(WordToPdfHandler._convert_via_word, src, out_path)
        elif engine == "libreoffice":
            await asyncio.to_thread(WordToPdfHandler._convert_via_libreoffice, src, out_path)
        else:
            raise ValueError(f"wordToPdf: 未知引擎: {engine}（可选 word / libreoffice）")

        if not out_path.exists():
            raise RuntimeError(f"wordToPdf: 转换完成但未找到输出文件: {out_path}")

        result = {
            "cmd": "wordToPdf",
            "source": str(src),
            "output": str(out_path),
            "engine": engine,
        }
        runner.completed += 1
        if output_var:
            runner.vars[output_var] = str(out_path)
        runner.results.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "status": "success",
            "result": result,
        })
        await runner._emit({
            "type": "stepComplete",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "result": result,
        })
        return True

    # ── Word COM 引擎 ────────────────────────────────────────────
    @staticmethod
    def _convert_via_word(src: Path, out_path: Path):
        """用本机 Microsoft Word 的 COM 接口转换（Windows）。

        优先使用 pywin32（win32com），其次 comtypes；两者都未安装则明确报错。
        """
        out_path.parent.mkdir(parents=True, exist_ok=True)
        src_abs = str(src.resolve())
        out_abs = str(out_path.resolve())

        try:
            import win32com.client  # noqa: F401
            try:
                WordToPdfHandler._word_com_convert(
                    lambda: win32com.client.Dispatch("Word.Application"),
                    src_abs, out_abs)
            except Exception as com_err:
                raise RuntimeError(
                    f"Word COM 转换失败（请确认已安装 Microsoft Word 且能打开该文档）: {com_err}"
                ) from com_err
            return
        except ImportError:
            pass

        try:
            import comtypes.client  # noqa: F401
            try:
                WordToPdfHandler._word_com_convert(
                    lambda: comtypes.client.CreateObject("Word.Application"),
                    src_abs, out_abs)
            except Exception as com_err:
                raise RuntimeError(
                    f"Word COM 转换失败（请确认已安装 Microsoft Word 且能打开该文档）: {com_err}"
                ) from com_err
            return
        except ImportError as e:
            raise RuntimeError(
                "使用 Word 引擎需要安装 pywin32（推荐）或 comtypes：pip install pywin32") from e

    @staticmethod
    def _word_com_convert(make_app, src_abs: str, out_abs: str):
        """调用 Word COM：打开文档并以 PDF 格式保存。"""
        word = make_app()
        try:
            try:
                word.Visible = False
                word.DisplayAlerts = False
            except Exception:
                # 个别版本/绑定方案会因缺少这些属性而报错，忽略即可
                pass
            doc = word.Documents.Open(src_abs)
            try:
                # FileFormat=17 (wdFormatPDF)，用位置参数第 2 位传值兼容动态绑定
                doc.SaveAs(out_abs, _WD_FORMAT_PDF)
            finally:
                doc.Close(False)
        finally:
            try:
                word.Quit()
            except Exception:
                pass

    # ── LibreOffice 引擎 ──────────────────────────────────────────
    @staticmethod
    def _convert_via_libreoffice(src: Path, out_path: Path):
        """用 LibreOffice headless 转换（跨平台，需 soffice 在 PATH）。"""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        soffice = shutil.which("soffice")
        if not soffice:
            raise RuntimeError(
                "使用 LibreOffice 引擎需要安装 LibreOffice，且保证 soffice 在 PATH 中")

        outdir = out_path.parent
        cmd = [soffice, "--headless", "--convert-to", "pdf",
               "--outdir", str(outdir), str(src.resolve())]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            raise RuntimeError("wordToPdf: LibreOffice 转换超时（600s）") from None
        if proc.returncode != 0:
            raise RuntimeError(
                f"wordToPdf: LibreOffice 转换失败: {proc.stderr.strip() or proc.stdout.strip()}")

        # LibreOffice 输出文件名固定为源文件名(去掉扩展名)+.pdf
        produced = out_path.parent / f"{src.stem}.pdf"
        if not produced.exists():
            raise RuntimeError(f"wordToPdf: LibreOffice 未生成输出文件: {produced}")
        if produced.resolve() != out_path.resolve():
            os.replace(produced, out_path)
