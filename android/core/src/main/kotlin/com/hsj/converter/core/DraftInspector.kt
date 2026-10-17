package com.hsj.converter.core

import java.io.File

object DraftInspector {
    fun inspect(input: File, workDir: File): DraftInfo {
        workDir.mkdirs()
        val warnings = ArrayList<String>()
        HsjArchive.open(input, workDir).use { archive ->
            var paintName: String? = null
            var draw: DrawData? = null
            for (name in listOf("paint_as.dat", "paint.dat")) {
                val blob = archive.readFile(name) ?: continue
                try {
                    val parsed = MetadataParser.parseDrawData(blob)
                    if (draw == null || parsed.layers.size > draw!!.layers.size) {
                        draw = parsed
                        paintName = name
                    }
                } catch (e: HsjException) {
                    warnings += "$name 解析失败：${e.message}"
                }
            }
            val data = draw ?: DrawData()
            var roots = LayerTree.build(data.layers)
            if (roots.isEmpty()) {
                val ids = archive.layerIds()
                if (ids.isEmpty()) throw HsjException("草稿中既没有图层元数据，也没有图层文件")
                roots = ids.mapIndexed { index, id ->
                    LayerInfo(id = id, name = "图层 ${index + 1}", opacity = 1f, visible = true)
                }
                warnings += "未找到图层元数据，按文件名顺序重建 ${ids.size} 个图层"
            }
            var leaves = LayerTree.flattenForPsd(roots)
            if (leaves.isEmpty()) throw HsjException("草稿中没有可转换的图层")

            var width = data.canvasWidth
            var height = data.canvasHeight
            if (width <= 0 || height <= 0) {
                for (leaf in leaves) {
                    val range = archive.layerRange(leaf.layer.id) ?: continue
                    val size = readLayerSize(archive, range) ?: continue
                    width = size.first
                    height = size.second
                    break
                }
            }
            if (width <= 0 || height <= 0) throw HsjException("无法确定画布尺寸")
            if (width > 30000 || height > 30000) {
                warnings += "画布 ${width}x$height 超过 PSD 的 30000 限制，PSD 输出不可用"
            }
            if (data.colorSpace.isNotEmpty()) {
                warnings += "色彩空间 ${data.colorSpace} 不会嵌入 ICC，输出按 sRGB 解释"
            }

            return DraftInfo(
                input = input,
                canvasWidth = width,
                canvasHeight = height,
                ppi = data.ppi,
                colorSpace = data.colorSpace,
                bgArgb = data.bgColor,
                bgHidden = data.bgHidden,
                paintName = paintName,
                roots = roots,
                draw = data,
                folderName = archive.folderName,
                warnings = warnings,
            )
        }
    }

    private fun readLayerSize(archive: HsjArchive, range: FileRange): Pair<Int, Int>? {
        if (range.length < 15) return null
        return try {
            val header = archive.readRange(range, 0, 15)
            if (header[0] != 'h'.code.toByte() || header[1] != 's'.code.toByte() ||
                header[2] != 'j'.code.toByte() || header[3] != 0.toByte()
            ) return null
            val width = beInt(header, 7)
            val height = beInt(header, 11)
            if (width > 0 && height > 0 && width <= 100000 && height <= 100000) {
                width to height
            } else null
        } catch (_: Exception) {
            null
        }
    }
}
