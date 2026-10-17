package com.hsj.converter.core

import ar.com.hjg.pngj.ImageInfo
import ar.com.hjg.pngj.PngWriter
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.FilterOutputStream
import java.io.OutputStream
import java.util.IdentityHashMap
import java.util.Locale
import java.util.zip.CRC32
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * Streaming ORA writer. mimetype is the first entry; layer PNGs are streamed as they
 * are decoded; stack.xml and mergedimage.png are appended at the end.
 */
class OraSink(
    private val output: File,
    private val width: Int,
    private val height: Int,
    private val roots: List<LayerInfo>,
    private val workDir: File,
) {
    private data class EntryInfo(val src: String, val x: Int, val y: Int)

    private val zip: ZipOutputStream
    private val entries = IdentityHashMap<LayerInfo, EntryInfo>()
    private var index = 0

    init {
        output.parentFile?.mkdirs()
        zip = ZipOutputStream(BufferedOutputStream(FileOutputStream(output), 256 * 1024))
        val data = "image/openraster".toByteArray(Charsets.US_ASCII)
        val crc = CRC32().apply { update(data) }.value
        val entry = ZipEntry("mimetype").apply {
            method = ZipEntry.STORED
            size = data.size.toLong()
            compressedSize = data.size.toLong()
            this.crc = crc
        }
        zip.putNextEntry(entry)
        zip.write(data)
        zip.closeEntry()
    }

    fun addLayer(
        layer: LayerInfo,
        surface: MappedRgbaSurface?,
        bounds: RgbaRect?,
        constant: IntArray? = null,
    ) {
        val crop = if (bounds != null && !bounds.isEmpty) bounds else RgbaRect(0, 0, 1, 1)
        val src = "data/layer${index++}.png"
        entries[layer] = EntryInfo(src, crop.left, crop.top)
        val entry = ZipEntry(src)
        zip.putNextEntry(entry)
        writePng(surface, crop, constant)
        zip.closeEntry()
    }

    private fun writePng(surface: MappedRgbaSurface?, crop: RgbaRect, constant: IntArray?) {
        val cols = crop.width
        val rows = crop.height
        val shield = CloseShieldOutputStream(zip)
        val writer = PngWriter(shield, ImageInfo(cols, rows, 8, true))
        writer.setCompLevel(6)
        val rgba = ByteArray(width * 4)
        val row = IntArray(cols * 4)
        try {
            for (y in 0 until rows) {
                when {
                    surface != null -> {
                        surface.readRow(crop.top + y, rgba)
                        var src = crop.left * 4
                        var dst = 0
                        for (x in 0 until cols) {
                            row[dst] = rgba[src].toInt() and 0xFF
                            row[dst + 1] = rgba[src + 1].toInt() and 0xFF
                            row[dst + 2] = rgba[src + 2].toInt() and 0xFF
                            row[dst + 3] = rgba[src + 3].toInt() and 0xFF
                            src += 4
                            dst += 4
                        }
                    }
                    constant != null -> {
                        var dst = 0
                        for (x in 0 until cols) {
                            row[dst] = constant[0]
                            row[dst + 1] = constant[1]
                            row[dst + 2] = constant[2]
                            row[dst + 3] = constant[3]
                            dst += 4
                        }
                    }
                    else -> java.util.Arrays.fill(row, 0)
                }
                writer.writeRowInt(row)
            }
        } finally {
            writer.end()
        }
    }

    fun finish(composite: MappedRgbaSurface) {
        val xml = buildString {
            append("<?xml version='1.0' encoding='UTF-8'?>\n")
            append("<image version=\"0.0.2\" w=\"$width\" h=\"$height\">\n")
            append("  <stack name=\"root\" visibility=\"visible\" opacity=\"1.0000\" ")
            append("composite-op=\"svg:normal\">\n")
            appendStack(roots, 2)
            append("  </stack>\n")
            append("</image>")
        }.toByteArray(Charsets.UTF_8)
        zip.putNextEntry(ZipEntry("stack.xml"))
        zip.write(xml)
        zip.closeEntry()

        zip.putNextEntry(ZipEntry("mergedimage.png"))
        writePng(composite, RgbaRect(0, 0, width, height), null)
        zip.closeEntry()
        zip.finish()
        zip.close()
    }

    private fun StringBuilder.appendStack(items: List<LayerInfo>, level: Int) {
        val indent = "  ".repeat(level)
        for (item in items) {
            val name = xmlAttr(item.name.ifBlank { "Layer" })
            val vis = if (item.visible) "visible" else "hidden"
            val opacity = String.format(
                Locale.US, "%.4f", item.opacity.coerceIn(0f, 1f))
            val blend = BlendModes.svgKey(item.blendMode)
            if (item.isGroup) {
                append("$indent<stack name=\"$name\" visibility=\"$vis\" ")
                append("opacity=\"$opacity\" composite-op=\"$blend\" isolation=\"isolate\">\n")
                appendStack(item.children, level + 1)
                append("$indent</stack>\n")
            } else {
                val info = entries[item] ?: EntryInfo("data/layer0.png", 0, 0)
                append("$indent<layer name=\"$name\" src=\"${info.src}\" ")
                append("x=\"${info.x}\" y=\"${info.y}\" visibility=\"$vis\" ")
                append("opacity=\"$opacity\" composite-op=\"$blend\"/>\n")
            }
        }
    }

    private fun xmlAttr(text: String): String {
        val clean = buildString(text.length) {
            for (ch in text) {
                append(if (ch.code >= 0x20 || ch == '\t' || ch == '\n' || ch == '\r') ch else ' ')
            }
        }
        return buildString(clean.length + 8) {
            for (ch in clean) {
                when (ch) {
                    '&' -> append("&amp;")
                    '<' -> append("&lt;")
                    '>' -> append("&gt;")
                    '"' -> append("&quot;")
                    '\'' -> append("&apos;")
                    else -> append(ch)
                }
            }
        }
    }

    fun abort() {
        runCatching { zip.close() }
        runCatching { output.delete() }
    }

    private class CloseShieldOutputStream(out: OutputStream) : FilterOutputStream(out) {
        override fun close() = Unit
        override fun write(b: ByteArray, off: Int, len: Int) = out.write(b, off, len)
    }
}
