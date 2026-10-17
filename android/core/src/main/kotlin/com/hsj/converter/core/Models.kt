package com.hsj.converter.core

import java.io.File

enum class ClipType(val code: Int) {
    NONE(0), TOP(1), MIDDLE(2), BOTTOM(3);

    companion object {
        fun of(code: Int): ClipType = entries.firstOrNull { it.code == code } ?: NONE
    }
}

enum class Format {
    PSD, ORA, BOTH;

    val includesPsd: Boolean get() = this == PSD || this == BOTH
    val includesOra: Boolean get() = this == ORA || this == BOTH
}

enum class Stage { PREPARE, DECODE, LAYER_OUTPUT, COMPOSITE, MERGED, FINALIZE }

enum class LogLevel { INFO, WARN, ERROR, SUCCESS }

object BlendModes {
    private val names = arrayOf(
        "NORMAL", "MULTIPLY", "SCREEN", "LINEAR_DODGE", "DARK",
        "COLOR_BURN", "COLOR_DODGE", "OVERLAY", "SOFT_LIGHT", "DIVIDE",
        "COLOR", "LUMINOSITY", "SATURATION", "DISSOLVE", "LINEAR_BURN",
        "DARKER_COLOR", "LIGHTEN", "LIGHTER_COLOR", "HARD_LIGHT", "VIVID_LIGHT",
        "LINEAR_LIGHT", "PIN_LIGHT", "HARD_MIX", "DIFFERENCE", "EXCLUSION",
        "SUBTRACT", "HUE", "GLOW", "PASS_THROUGH", "GROUP_NORMAL",
    )

    val psdKeys = arrayOf(
        "norm", "mul ", "scrn", "lddg", "dark",
        "idiv", "div ", "over", "sLit", "fdiv",
        "colr", "lum ", "sat ", "diss", "lbrn",
        "dkCl", "lite", "lgCl", "hLit", "vLit",
        "lLit", "pLit", "hMix", "diff", "smud",
        "fsub", "hue ", "norm", "pass", "norm",
    )

    val svgKeys = arrayOf(
        "svg:normal", "svg:multiply", "svg:screen", "svg:screen", "svg:darken",
        "svg:color-burn", "svg:color-dodge", "svg:overlay", "svg:soft-light", "svg:normal",
        "svg:color", "svg:luminosity", "svg:saturation", "svg:normal", "svg:multiply",
        "svg:darken", "svg:lighten", "svg:lighten", "svg:hard-light", "svg:hard-light",
        "svg:normal", "svg:normal", "svg:normal", "svg:difference", "svg:exclusion",
        "svg:normal", "svg:hue", "svg:normal", "svg:normal", "svg:normal",
    )

    fun name(code: Int): String = names.getOrElse(code) { "UNKNOWN($code)" }

    fun psdKey(code: Int): String = psdKeys.getOrElse(code) { "norm" }

    fun svgKey(code: Int): String = svgKeys.getOrElse(code) { "svg:normal" }
}

data class LayerInfo(
    var id: String = "",
    var name: String = "",
    var opacity: Float = 1.0f,
    var visible: Boolean = true,
    var blendMode: Int = 0,
    var clipType: Int = 0,
    var clipGroup: Int = 0,
    var layerNo: Int = 0,
    var isGroup: Boolean = false,
    var isLock: Boolean = false,
    var isLockAlpha: Boolean = false,
    var parentId: String = "",
    val children: MutableList<LayerInfo> = mutableListOf(),
    var visiblePresent: Boolean = false,
) {
    val blendName: String get() = BlendModes.name(blendMode)
}

data class DrawData(
    var canvasWidth: Int = 0,
    var canvasHeight: Int = 0,
    var bgColor: Int = 0,
    var bgHidden: Boolean = false,
    var ppi: Int = 72,
    var colorSpace: String = "",
    var layers: List<LayerInfo> = emptyList(),
)

data class FileRange(val file: File, val offset: Long, val length: Long) {
    val end: Long get() = offset + length
}

data class DraftInfo(
    val input: File,
    val canvasWidth: Int,
    val canvasHeight: Int,
    val ppi: Int,
    val colorSpace: String,
    val bgArgb: Int,
    val bgHidden: Boolean,
    val paintName: String?,
    val roots: List<LayerInfo>,
    val draw: DrawData,
    val folderName: String,
    val warnings: List<String> = emptyList(),
) {
    val leaves: List<LeafLayer> get() = LayerTree.flattenForPsd(roots)
    val layerCount: Int get() = leaves.size

    /** Returns r,g,b,a. */
    fun backgroundRgba(): IntArray {
        val c = bgArgb.toLong() and 0xFFFFFFFFL
        return intArrayOf(
            ((c shr 16) and 0xFF).toInt(),
            ((c shr 8) and 0xFF).toInt(),
            (c and 0xFF).toInt(),
            ((c shr 24) and 0xFF).toInt(),
        )
    }

    fun includeBackground(requested: Boolean): Boolean {
        val rgba = backgroundRgba()
        return requested && !bgHidden && rgba[3] > 0
    }
}

data class LeafLayer(
    val layer: LayerInfo,
    val name: String,
    val opacity: Float,
    val visible: Boolean,
)

data class ConvertRequest(
    val format: Format,
    val includeBackground: Boolean,
    val psdFile: File?,
    val oraFile: File?,
    val workDir: File,
)

data class OutputFile(val file: File, val format: Format)

data class ConversionResult(
    val outputs: List<OutputFile>,
    val warnings: List<String>,
    val durationMs: Long,
)

interface ZstdBlockDecoder {
    fun decompress(src: ByteArray, srcOffset: Int, srcLength: Int, dstSize: Int): ByteArray
}

interface EngineListener {
    fun onProgress(stage: Stage, done: Int, total: Int, fraction: Float, message: String)
    fun onLog(level: LogLevel, message: String)
    fun isCancelled(): Boolean
}

object NoopEngineListener : EngineListener {
    override fun onProgress(stage: Stage, done: Int, total: Int, fraction: Float, message: String) = Unit
    override fun onLog(level: LogLevel, message: String) = Unit
    override fun isCancelled(): Boolean = false
}
