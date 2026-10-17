package com.hsj.converter.core

import java.io.File
import kotlin.math.max

class ConversionEngine(
    private val zstd: ZstdBlockDecoder,
    private val listener: EngineListener = NoopEngineListener,
) {
    private val decoder = LayerDecoder(zstd)
    private val compositor = Compositor()

    fun convert(input: File, request: ConvertRequest): ConversionResult {
        val startNanos = System.nanoTime()
        val warnings = ArrayList<String>()
        var psdSink: PsdSink? = null
        var oraSink: OraSink? = null
        var archive: HsjArchive? = null
        var layerSurface: MappedRgbaSurface? = null
        var composite: MappedRgbaSurface? = null
        val clipAlphas = HashMap<Int, MappedAlphaSurface>()

        try {
            listener.onProgress(Stage.PREPARE, 0, 1, 0.01f, "读取草稿信息")
            val info = DraftInspector.inspect(input, request.workDir)
            warnings += info.warnings
            if (request.format.includesPsd && request.psdFile == null) {
                throw HsjException("未指定 PSD 输出文件")
            }
            if (request.format.includesOra && request.oraFile == null) {
                throw HsjException("未指定 ORA 输出文件")
            }
            if (request.format.includesPsd && (info.canvasWidth > 30000 || info.canvasHeight > 30000)) {
                throw HsjException("PSD 不支持 ${info.canvasWidth}x${info.canvasHeight}（上限 30000）")
            }

            val includeBg = info.includeBackground(request.includeBackground)
            val bgRgba = if (includeBg) info.backgroundRgba() else null
            val bgLayer = if (includeBg) LayerInfo(
                id = "__background__",
                name = "背景",
                opacity = 1f,
                visible = true,
                blendMode = 0,
                clipType = 0,
                clipGroup = 0,
                isGroup = false,
            ) else null
            val roots = if (bgLayer != null) listOf(bgLayer) + info.roots else info.roots
            val flat = LayerTree.flattenForPsd(roots)
            if (flat.isEmpty()) throw HsjException("草稿中没有可转换的图层")

            val required = info.canvasWidth.toLong() * info.canvasHeight * 5L + 512L * 1024 * 1024
            val usable = request.workDir.usableSpace
            if (usable > 0 && usable < required) {
                throw InsufficientStorageException(
                    "缓存空间不足：需要约 ${required / 1024 / 1024} MB，可用 ${usable / 1024 / 1024} MB")
            }

            archive = HsjArchive.open(input, request.workDir)
            layerSurface = MappedRgbaSurface(
                File(request.workDir, "layer.rgba"), info.canvasWidth, info.canvasHeight)
            composite = MappedRgbaSurface(
                File(request.workDir, "composite.rgba"), info.canvasWidth, info.canvasHeight)
            composite.clear()
            if (bgRgba != null) compositor.fillBackground(composite, bgRgba)

            if (request.format.includesPsd) {
                psdSink = PsdSink(
                    request.psdFile!!, info.canvasWidth, info.canvasHeight,
                    info.ppi, request.workDir)
            }
            if (request.format.includesOra) {
                oraSink = OraSink(
                    request.oraFile!!, info.canvasWidth, info.canvasHeight,
                    roots, request.workDir)
            }

            val baseIndexByGroup = HashMap<Int, Int>()
            val lastIndexByGroup = HashMap<Int, Int>()
            val groupHasClipped = HashSet<Int>()
            flat.forEachIndexed { index, leaf ->
                val layer = leaf.layer
                val group = layer.clipGroup
                if (group != 0) {
                    if (layer.clipType == ClipType.BOTTOM.code && !baseIndexByGroup.containsKey(group)) {
                        baseIndexByGroup[group] = index
                    }
                    if (layer.clipType == ClipType.TOP.code || layer.clipType == ClipType.MIDDLE.code) {
                        groupHasClipped += group
                        lastIndexByGroup[group] = index
                    }
                }
            }

            listener.onLog(LogLevel.INFO,
                "画布 ${info.canvasWidth}x${info.canvasHeight}，图层 ${flat.size} 个，PPI ${info.ppi}")

            val total = flat.size
            for ((index, leaf) in flat.withIndex()) {
                if (listener.isCancelled()) throw ConversionCancelledException()
                val layer = leaf.layer
                val isBackground = layer.id == "__background__"
                var rawBounds: RgbaRect? = null
                var decoded = false

                if (isBackground) {
                    rawBounds = RgbaRect(0, 0, info.canvasWidth, info.canvasHeight)
                    decoded = true
                } else {
                    val range = archive.layerRange(layer.id)
                    if (range == null) {
                        warnings += "缺少图层像素：${layer.name.ifBlank { layer.id }}"
                        listener.onLog(LogLevel.WARN, "缺少图层像素：${layer.name}")
                    } else {
                        try {
                            val result = decoder.decode(
                                archive, range, info.canvasWidth, info.canvasHeight,
                                layerSurface, listener)
                            rawBounds = result.bounds
                            decoded = true
                        } catch (e: ConversionCancelledException) {
                            throw e
                        } catch (e: Exception) {
                            warnings += "图层 ${layer.name.ifBlank { layer.id }} 解码失败：${e.message}"
                            listener.onLog(LogLevel.WARN,
                                "图层 ${layer.name.ifBlank { layer.id }} 解码失败：${e.message}")
                        }
                    }
                }

                val layerVisible = leaf.visible
                val clipping = (layer.clipType == ClipType.TOP.code ||
                    layer.clipType == ClipType.MIDDLE.code) &&
                    baseIndexByGroup[layer.clipGroup]?.let { it < index } == true

                // PSD gets the raw pixels (no clipping bake).
                if (psdSink != null) {
                    psdSink.addLayer(
                        PsdLayerSpec(
                            name = leaf.name.ifBlank { "图层 ${index + 1}" },
                            opacity = leaf.opacity,
                            visible = layerVisible,
                            blendMode = layer.blendMode,
                            clipping = clipping,
                            lockAlpha = layer.isLockAlpha,
                        ),
                        if (!isBackground && decoded) layerSurface else null,
                        rawBounds,
                        if (isBackground) bgRgba else null,
                    )
                }

                // Composite the raw layer.
                if (!isBackground && decoded && layerVisible && rawBounds != null) {
                    val clipBase = baseIndexByGroup[layer.clipGroup]
                    val clipAlpha = if (layer.clipType == ClipType.TOP.code ||
                        layer.clipType == ClipType.MIDDLE.code
                    ) clipAlphas[layer.clipGroup] else null
                    val baseVisible = clipBase?.let { flat[it].visible } ?: true
                    if (layer.clipType == ClipType.TOP.code ||
                        layer.clipType == ClipType.MIDDLE.code
                    ) {
                        if (clipBase == null) {
                            // No base; Python simply does not apply clipping.
                            compositor.blendLayer(
                                composite, layerSurface, rawBounds, leaf.opacity,
                                layer.blendMode, null, true)
                        } else if (baseVisible && clipAlpha != null) {
                            compositor.blendLayer(
                                composite, layerSurface, rawBounds, leaf.opacity,
                                layer.blendMode, clipAlpha, true)
                        }
                        // A missing/undecoded base contributes zero alpha, so skip.
                    } else {
                        compositor.blendLayer(
                            composite, layerSurface, rawBounds, leaf.opacity,
                            layer.blendMode, null, true)
                    }
                }

                // Cache the base alpha for composite clipping / ORA baking.
                if (!isBackground && decoded && layer.clipGroup != 0 &&
                    layer.clipType == ClipType.BOTTOM.code &&
                    groupHasClipped.contains(layer.clipGroup) &&
                    !clipAlphas.containsKey(layer.clipGroup)
                ) {
                    val alpha = MappedAlphaSurface(
                        File(request.workDir, "clip_${layer.clipGroup}.alpha"),
                        info.canvasWidth, info.canvasHeight)
                    layerSurface.writeAlphaTo(alpha)
                    clipAlphas[layer.clipGroup] = alpha
                }

                // ORA gets baked alpha for clipped layers; composite already used raw data.
                if (oraSink != null) {
                    var oraBounds = rawBounds
                    val clipped = layer.clipType == ClipType.TOP.code ||
                        layer.clipType == ClipType.MIDDLE.code
                    if (!isBackground && decoded && clipped) {
                        val alpha = clipAlphas[layer.clipGroup]
                        if (alpha != null) {
                            layerSurface.multiplyAlphaBy(alpha)
                            oraBounds = layerSurface.alphaBounds()
                        }
                    }
                    oraSink.addLayer(
                        layer,
                        if (!isBackground && decoded) layerSurface else null,
                        oraBounds,
                        if (isBackground) bgRgba else null,
                    )
                }

                // Release a clip base alpha after its last clipped layer.
                val group = layer.clipGroup
                if (group != 0 && lastIndexByGroup[group] == index) {
                    clipAlphas.remove(group)?.close()
                }

                val done = index + 1
                val fraction = 0.05f + 0.82f * (done.toFloat() / max(1, total))
                listener.onProgress(
                    Stage.LAYER_OUTPUT, done, total, fraction,
                    "处理图层 $done/$total")
                if (done == total || done % 8 == 0) {
                    listener.onLog(LogLevel.INFO, "已处理 $done/$total 个图层")
                }
            }

            if (listener.isCancelled()) throw ConversionCancelledException()
            listener.onProgress(Stage.MERGED, total, total, 0.9f, "写入合并预览")
            listener.onLog(LogLevel.INFO, "写入输出文件…")
            psdSink?.finish(composite)
            oraSink?.finish(composite)
            listener.onProgress(Stage.FINALIZE, total, total, 1f, "完成")

            val outputs = ArrayList<OutputFile>()
            if (psdSink != null) outputs += OutputFile(request.psdFile!!, Format.PSD)
            if (oraSink != null) outputs += OutputFile(request.oraFile!!, Format.ORA)
            return ConversionResult(
                outputs = outputs,
                warnings = warnings,
                durationMs = (System.nanoTime() - startNanos) / 1_000_000,
            )
        } catch (t: Throwable) {
            runCatching { psdSink?.abort() }
            runCatching { oraSink?.abort() }
            throw t
        } finally {
            clipAlphas.values.forEach { runCatching { it.close() } }
            runCatching { layerSurface?.close() }
            runCatching { composite?.close() }
            runCatching { archive?.close() }
        }
    }
}
